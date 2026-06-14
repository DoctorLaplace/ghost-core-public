# agent/effectors/sandbox.py
import subprocess
import os
import logging
from pathlib import Path
import config

logger = logging.getLogger(__name__)

BLOCKED_PATTERNS = [
    "format ",
    "del /s",
    "rd /s",
    "rmdir /s",
    "reg delete",
    "shutdown",
    "vssadmin",
    "cipher /w",
    "bcdedit"
]

def run_sandboxed(command: str, timeout: int = 60, workdir: str = None) -> dict:
    """
    Executes a shell command in a sandboxed directory (data/sandbox/) by default.
    Checks command against a blocklist before executing.
    """
    # 1. Blocklist check
    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            result = {
                "stdout": "",
                "stderr": f"BLOCKED: matched pattern {pattern}",
                "returncode": -2,
                "timed_out": False
            }
            # Log tracer event
            _log_sandbox_event(blocked=True, returncode=-2)
            return result

    # 2. Setup directory
    if workdir:
        sandbox_dir = Path(workdir)
    else:
        sandbox_dir = Path("data/sandbox")
    
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # 3. Execute subprocess
    try:
        # Run the command in the sandbox directory
        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(sandbox_dir)
        )
        
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        returncode = res.returncode
        timed_out = False
        
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or "")
        returncode = -1
        timed_out = True
        
    except Exception as e:
        stdout = ""
        stderr = str(e)
        returncode = -1
        timed_out = False

    # 4. Log tracer event
    _log_sandbox_event(blocked=False, returncode=returncode)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "timed_out": timed_out
    }

def _log_sandbox_event(blocked: bool, returncode: int):
    """Safely logs a sandbox_exec tracer event."""
    try:
        from agent.kernel.tracer import active_trace_storage, Tracer
        trace_id = getattr(active_trace_storage, "trace_id", None)
        if trace_id:
            tracer_inst = Tracer()
            tracer_inst.log_event(trace_id, "sandbox_exec", {
                "blocked": blocked,
                "returncode": returncode
            })
    except Exception:
        pass
