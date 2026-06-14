# evals/run_evals.py
import os
import sys
import json
import re
import time
import subprocess
import glob
from datetime import datetime

TASKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")

def cleanup_eval_artifacts():
    """Deletes any eval_out_* files in the root repository folder."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    patterns = ["eval_out_*.*", "eval_out_*"]
    deleted_count = 0
    for pattern in patterns:
        for filepath in glob.glob(os.path.join(root_dir, pattern)):
            try:
                os.remove(filepath)
                deleted_count += 1
            except Exception as e:
                print(f"Warning: Failed to delete {filepath}: {e}")
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} evaluation output files.")

def verify_task(verify_type, verify_arg, stdout_content=""):
    """
    Verifies if a task succeeded based on verify_type and verify_arg.
    Returns (success: bool, error_message: str)
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    if verify_type == "file_exists":
        filepath = os.path.join(root_dir, verify_arg)
        if os.path.exists(filepath):
            return True, ""
        return False, f"Expected file {verify_arg} does not exist."
        
    elif verify_type == "file_contains":
        if "::" not in verify_arg:
            return False, f"Invalid verify_arg format for file_contains: {verify_arg}. Must be filename::expected_substring"
        filename, expected = verify_arg.split("::", 1)
        filepath = os.path.join(root_dir, filename)
        if not os.path.exists(filepath):
            return False, f"File {filename} does not exist."
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if expected in content:
                return True, ""
            return False, f"File {filename} did not contain expected text '{expected}'."
        except Exception as e:
            return False, f"Error reading file {filename}: {e}"
            
    elif verify_type == "command_exit_zero":
        try:
            # Run command in repo root
            res = subprocess.run(verify_arg, shell=True, cwd=root_dir, capture_output=True, text=True)
            if res.returncode == 0:
                return True, ""
            return False, f"Command exited with non-zero code {res.returncode}. Stderr: {res.stderr}"
        except Exception as e:
            return False, f"Failed to execute verification command: {e}"
            
    elif verify_type == "regex_match_answer":
        if "::" in verify_arg:
            filename, pattern = verify_arg.split("::", 1)
            filepath = os.path.join(root_dir, filename)
            if not os.path.exists(filepath):
                return False, f"File {filename} does not exist for regex verification."
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if re.search(pattern, content):
                    return True, ""
                return False, f"File {filename} content did not match regex pattern '{pattern}'."
            except Exception as e:
                return False, f"Error reading file {filename} for regex: {e}"
        else:
            if re.search(verify_arg, stdout_content):
                return True, ""
            return False, f"Subprocess output did not match regex pattern '{verify_arg}'."
            
    return False, f"Unknown verify_type: {verify_type}"

def run_suite(tasks, dry_verify, ablation_protocol=None):
    if ablation_protocol:
        os.environ["GC7_PROTOCOL_ABLATION"] = ablation_protocol
        print(f"\nRunning evaluation with protocol '{ablation_protocol}' ablated...")
    else:
        os.environ.pop("GC7_PROTOCOL_ABLATION", None)
        print("\nRunning normal evaluation...")

    # Clean up before run
    if not dry_verify:
        cleanup_eval_artifacts()
        
    results = []
    category_counts = {}
    category_passes = {}
    
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    for i, task in enumerate(tasks):
        task_id = task["id"]
        prompt = task["prompt"]
        category = task["category"]
        verify_type = task["verify_type"]
        verify_arg = task["verify_arg"]
        
        category_counts[category] = category_counts.get(category, 0) + 1
        
        start_time = time.time()
        success = False
        err_msg = ""
        stdout_output = ""
        
        if dry_verify:
            # Only run verification against existing files
            success, err_msg = verify_task(verify_type, verify_arg)
            duration = 0.0
        else:
            # Run agent as a subprocess
            cmd = f"python main.py --prompt \"{prompt}\""
            try:
                # 300s hard timeout
                proc = subprocess.run(
                    cmd, 
                    shell=True, 
                    cwd=root_dir, 
                    capture_output=True, 
                    text=True, 
                    timeout=300,
                    encoding="utf-8",
                    errors="ignore"
                )
                stdout_output = proc.stdout
                duration = time.time() - start_time
                
                # Check outcome verification
                success, err_msg = verify_task(verify_type, verify_arg, stdout_output)
            except subprocess.TimeoutExpired:
                err_msg = "Task timed out after 300 seconds."
                duration = 300.0
            except Exception as e:
                err_msg = f"Unexpected execution error: {e}"
                duration = time.time() - start_time
                
        status_str = "PASS" if success else "FAIL"
        
        if success:
            category_passes[category] = category_passes.get(category, 0) + 1
            
        results.append({
            "id": task_id,
            "prompt": prompt,
            "category": category,
            "status": status_str.lower(),
            "duration_sec": round(duration, 2),
            "error": err_msg if not success else ""
        })
        
    # Calculate statistics
    total_runs = len(results)
    total_passes = sum(1 for r in results if r["status"] == "pass")
    agg_pass_rate = total_passes / total_runs if total_runs > 0 else 0.0
    
    category_rates = {}
    for cat, total in category_counts.items():
        passes = category_passes.get(cat, 0)
        category_rates[cat] = round(passes / total, 2)
        
    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "aggregate_pass_rate": round(agg_pass_rate, 2),
        "category_pass_rates": category_rates,
        "ablation_protocol": ablation_protocol,
        "results": results
    }
    
    # Save results
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = f"_ablation_{ablation_protocol}" if ablation_protocol else ""
    results_filename = f"results_{timestamp_str}{suffix}.json"
    results_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), results_filename)
    
    with open(results_filepath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    print(f"Evaluation complete. Aggregate pass rate: {agg_pass_rate*100:.1f}%")
    for cat, rate in category_rates.items():
        print(f"  Category '{cat}': {rate*100:.1f}%")
    print(f"Saved results to {results_filepath}")
    
    # Clean up at the end
    if not dry_verify:
        cleanup_eval_artifacts()
        
    return agg_pass_rate

def main():
    dry_verify = "--dry-verify" in sys.argv
    
    protocol_ablation = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--protocol-ablation" and idx + 1 < len(sys.argv):
            protocol_ablation = sys.argv[idx + 1]
            break
            
    if not os.path.exists(TASKS_FILE):
        print(f"Error: Tasks file not found at {TASKS_FILE}")
        sys.exit(1)
        
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)
        
    print(f"Loaded {len(tasks)} tasks for evaluation.")
    
    if protocol_ablation:
        print(f"Starting protocol ablation test for protocol: {protocol_ablation}")
        rate_normal = run_suite(tasks, dry_verify, ablation_protocol=None)
        rate_ablated = run_suite(tasks, dry_verify, ablation_protocol=protocol_ablation)
        delta = rate_normal - rate_ablated
        print("\n=== A/B Ablation Summary ===")
        print(f"Normal Pass-rate:   {rate_normal*100:.1f}%")
        print(f"Ablated Pass-rate:  {rate_ablated*100:.1f}%")
        print(f"Delta (Normal - Ablated): {delta*100:.1f}%")
    else:
        run_suite(tasks, dry_verify)
        
    sys.exit(0)

if __name__ == "__main__":
    main()
