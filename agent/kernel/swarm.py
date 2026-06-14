import os
import sys
import json
import subprocess
from pathlib import Path
import config

active_workers = 0

def spawn_worker(task_prompt: str, worker_id: str, timeout: int = 600) -> dict:
    """
    Spawns a worker sub-agent process with quarantine flags in environment.
    Enforces maximum 2 concurrent workers and prevents recursive worker spawning.
    """
    global active_workers
    
    # Do not allow workers to spawn their own sub-workers
    if os.environ.get("GC7_WORKER_ID"):
        return {
            "worker_id": worker_id,
            "returncode": -4,
            "output": "SUB_WORKERS_PROHIBITED",
            "timed_out": False
        }
        
    # Enforce limit of max 2 concurrent workers
    if active_workers >= 2:
        return {
            "worker_id": worker_id,
            "returncode": -3,
            "output": "WORKER_LIMIT",
            "timed_out": False
        }
        
    active_workers += 1
    try:
        # Prepare environment copy with worker context
        env = os.environ.copy()
        env["GC7_WORKER_ID"] = worker_id
        env["GC7_MEMORY_QUARANTINE"] = "1"
        
        main_path = os.path.join(config.BASE_DIR, "main.py")
        cmd = [sys.executable, main_path, "--prompt", task_prompt]
        
        # Log tracer event
        try:
            from agent.kernel.tracer import active_trace_storage, Tracer
            trace_id = getattr(active_trace_storage, "trace_id", None)
            if trace_id:
                Tracer().log_event(trace_id, "worker_spawned", {"worker_id": worker_id})
        except Exception:
            pass
            
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            timed_out = False
            returncode = proc.returncode
            output = stdout + "\n" + stderr
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True
            returncode = -1
            output = stdout + "\n" + stderr + "\n[TIMED OUT]"
            
        return {
            "worker_id": worker_id,
            "returncode": returncode,
            "output": output,
            "timed_out": timed_out
        }
    finally:
        active_workers -= 1

def collect_quarantine(worker_id: str) -> list[dict]:
    """Reads quarantined memory logs for the specified worker ID."""
    quarantine_file = Path(config.DATA_DIR) / "quarantine" / f"{worker_id}.jsonl"
    if not quarantine_file.exists():
        return []
    records = []
    try:
        with open(quarantine_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except Exception:
        pass
    return records

def integrate_quarantine(worker_id: str, approved_ids: list[str]) -> int:
    """Integrates approved records into global VectorDB and marks logs processed."""
    quarantine_file = Path(config.DATA_DIR) / "quarantine" / f"{worker_id}.jsonl"
    if not quarantine_file.exists():
        return 0
        
    records = collect_quarantine(worker_id)
    if not records:
        return 0
        
    approved_set = set(approved_ids)
    integrated_count = 0
    
    from agent.kernel.db.vector_db import VectorDB
    from agent.kernel.db.graph_db import GraphDB
    
    try:
        vdb = VectorDB()
        gdb = GraphDB()
    except Exception:
        return 0
        
    for record in records:
        rec_id = record.get("id")
        if rec_id and rec_id in approved_set:
            text = record.get("text", "")
            try:
                # Add to VectorDB
                vdb.add_memory(text, record)
                # Add relationship to GraphDB
                gdb.add_entity_edge(rec_id, worker_id, "integrated_from")
                integrated_count += 1
            except Exception:
                pass
                
    # Mark quarantine file as processed
    try:
        processed_file = Path(config.DATA_DIR) / "quarantine" / f"{worker_id}.processed.jsonl"
        if processed_file.exists():
            os.remove(processed_file)
        os.rename(quarantine_file, processed_file)
    except Exception:
        pass
        
    # Log tracer event
    try:
        from agent.kernel.tracer import active_trace_storage, Tracer
        trace_id = getattr(active_trace_storage, "trace_id", None)
        if trace_id:
            Tracer().log_event(trace_id, "quarantine_integrated", {
                "worker_id": worker_id,
                "count": integrated_count
            })
    except Exception:
        pass
        
    return integrated_count

def validate_and_integrate_quarantine(worker_id: str, gemini_client, model_name: str) -> int:
    """Validates and filters quarantined logs using the cheap LLM tier."""
    records = collect_quarantine(worker_id)
    if not records:
        return 0
        
    approved_ids = []
    for record in records:
        text = record.get("text", "")
        prompt = f"""Review the following memory record. Is it factual, non-duplicative, and useful? Respond with YES or NO.
Record: {text}
Response:"""
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                purpose="classification"
            )
            ans = response.text.strip().upper()
            if "YES" in ans:
                approved_ids.append(record.get("id"))
        except Exception:
            # Fallback to approve on failure
            approved_ids.append(record.get("id"))
            
    return integrate_quarantine(worker_id, approved_ids)
