import sys
import importlib.util
import json
import os
import glob
from pathlib import Path
from datetime import datetime, timezone
import config

def should_use_canary(task_id: str) -> bool:
    """
    Deterministic function deciding if canary should be active.
    Uses MD5 of task_id to ensure reproducibility without process-level randomization.
    """
    if not getattr(config, "CANARY_ENABLED", False):
        return False
    import hashlib
    h = int(hashlib.md5(task_id.encode('utf-8')).hexdigest(), 16)
    ratio = getattr(config, "CANARY_RATIO", 0.1)
    return (h % 100) < int(ratio * 100)

def load_cortex_module(module_name: str, canary: bool):
    """
    Loads cortex module from staging if canary is True, the staging candidate exists,
    and compiling succeeds. Otherwise loads the stable agent.cortex version.
    """
    staging_file = Path(config.BASE_DIR) / "cortex_staging" / f"{module_name}.py"
    
    if canary and staging_file.exists():
        try:
            # compile check
            code = staging_file.read_text(encoding="utf-8")
            compile(code, str(staging_file), "exec")
            
            # Load dynamic staging module
            spec = importlib.util.spec_from_file_location(f"cortex_staging.{module_name}", str(staging_file))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"cortex_staging.{module_name}"] = module
                spec.loader.exec_module(module)
                
                # Log success event
                try:
                    from agent.kernel.tracer import active_trace_storage, Tracer
                    trace_id = getattr(active_trace_storage, "trace_id", None)
                    if trace_id:
                        t = Tracer()
                        t.log_event(trace_id, "canary_used", {
                            "module_name": module_name,
                            "task_id": trace_id.split("_")[0]
                        })
                except Exception:
                    pass
                    
                return module
        except Exception as e:
            # Log fallback event and load stable version
            try:
                from agent.kernel.tracer import active_trace_storage, Tracer
                trace_id = getattr(active_trace_storage, "trace_id", None)
                if trace_id:
                    t = Tracer()
                    t.log_event(trace_id, "canary_fallback", {
                        "module_name": module_name,
                        "error": str(e)
                    })
            except Exception:
                pass
                
    # Fallback to stable import
    return importlib.import_module(f"agent.cortex.{module_name}")

def record_canary_result(task_id: str, module_name: str, success: bool) -> None:
    """Appends a result record to data/canary_results.jsonl."""
    results_file = Path(config.DATA_DIR) / "canary_results.jsonl"
    os.makedirs(results_file.parent, exist_ok=True)
    try:
        with open(results_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "task_id": task_id,
                "module_name": module_name,
                "success": success,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }) + "\n")
    except Exception:
        pass

def evaluate_promotion(module_name: str, min_trials: int = 20) -> str:
    """
    Compares success rate of canary vs stable runs over the same timeframe.
    Returns 'PROMOTE' or 'HOLD'.
    """
    results_file = Path(config.DATA_DIR) / "canary_results.jsonl"
    if not results_file.exists():
        return "HOLD"
        
    canary_runs = []
    try:
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    run = json.loads(line)
                    if run.get("module_name") == module_name:
                        canary_runs.append(run)
    except Exception:
        return "HOLD"
        
    if len(canary_runs) < min_trials:
        return "HOLD"
        
    canary_successes = sum(1 for r in canary_runs if r.get("success"))
    canary_rate = canary_successes / len(canary_runs)
    
    # Extract timestamps to establish identical timeframe
    timestamps = []
    for r in canary_runs:
        try:
            ts_str = r.get("timestamp", "").replace("Z", "")
            timestamps.append(datetime.fromisoformat(ts_str))
        except Exception:
            pass
            
    if not timestamps:
        return "HOLD"
        
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    
    traces_dir = Path(config.BASE_DIR) / "data" / "traces"
    trace_files = glob.glob(os.path.join(traces_dir, "*.jsonl"))
    
    stable_trials = 0
    stable_successes = 0
    
    for filepath in trace_files:
        try:
            file_events = []
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        file_events.append(json.loads(line))
            if not file_events:
                continue
                
            is_canary_trace = any(
                e.get("event_type") == "canary_used" and e.get("payload", {}).get("module_name") == module_name
                for e in file_events
            )
            
            start_event = file_events[0]
            ts_str = start_event.get("ts", "").replace("Z", "")
            trace_ts = datetime.fromisoformat(ts_str)
            
            if min_ts <= trace_ts <= max_ts and not is_canary_trace:
                for e in file_events:
                    if e.get("event_type") == "trace_ended":
                        outcome = e.get("payload", {}).get("outcome")
                        stable_trials += 1
                        if outcome == "success":
                            stable_successes += 1
        except Exception:
            pass
            
    stable_rate = 0.0
    if stable_trials > 0:
        stable_rate = stable_successes / stable_trials
        
    if canary_rate >= stable_rate:
        return "PROMOTE"
    return "HOLD"
