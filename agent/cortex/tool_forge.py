# agent/cortex/tool_forge.py
import re
import os
import ast
import shutil
import logging
from pathlib import Path
import config
from agent.effectors.sandbox import run_sandboxed
from agent.kernel.tracer import active_trace_storage, Tracer

logger = logging.getLogger(__name__)

def forge_tool(name: str, code: str) -> dict:
    """
    Validates, tests, and saves a self-authored tool.
    Returns {"success": bool, "message": str}.
    """
    # a. Validate name matches regex
    if not re.match(r"^[a-z][a-z0-9_]{2,40}$", name):
        msg = f"Invalid tool name: '{name}'. Must match ^[a-z][a-z0-9_]{2,40}$"
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    # b. Validate code compiles
    try:
        compile(code, name, 'exec')
    except SyntaxError as e:
        msg = f"Syntax error in tool code: {e}"
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    # c. Static safety scan
    # Check for forbidden strings
    forbidden_substrings = ["os.remove", "shutil.rmtree", "subprocess", "eval(", "exec(", "__import__"]
    for sub in forbidden_substrings:
        if sub in code:
            msg = f"Security scan rejected code. Forbidden substring detected: '{sub}'"
            _log_forge_event(name, False)
            return {"success": False, "message": msg}

    # AST check for open('w') on absolute paths outside repo
    try:
        tree = ast.parse(code)
        repo_root = os.path.normpath(str(config.BASE_DIR))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = 'r'
                if len(node.args) >= 2:
                    if isinstance(node.args[1], ast.Constant):
                        mode = node.args[1].value
                    elif isinstance(node.args[1], ast.Str):
                        mode = node.args[1].s
                for kw in node.keywords:
                    if kw.arg == 'mode':
                        if isinstance(kw.value, ast.Constant):
                            mode = kw.value.value
                        elif isinstance(kw.value, ast.Str):
                            mode = kw.value.s
                            
                if any(m in mode for m in ['w', 'a', 'x']):
                    # Get path argument
                    path_val = None
                    if len(node.args) >= 1:
                        path_arg = node.args[0]
                        if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                            path_val = path_arg.value
                        elif isinstance(path_arg, ast.Str):
                            path_val = path_arg.s
                    
                    if path_val and os.path.isabs(path_val):
                        norm_path = os.path.normpath(path_val)
                        if not norm_path.startswith(repo_root):
                            msg = f"Security scan rejected code. Forbidden write/append to absolute path outside repository: '{path_val}'"
                            _log_forge_event(name, False)
                            return {"success": False, "message": msg}
    except Exception as e:
        msg = f"Error during safety AST scan: {e}"
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    # d. Write code to candidate file in sandbox
    sandbox_dir = Path("data/sandbox")
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = sandbox_dir / f"candidate_{name}.py"
    
    # Append the main/test test runner block
    candidate_code = code + '\n\nif __name__ == "__main__":\n    import sys\n    try:\n        sys.exit(0 if TEST() else 1)\n    except Exception as e:\n        sys.stderr.write(str(e))\n        sys.exit(1)\n'
    
    try:
        candidate_path.write_text(candidate_code, encoding='utf-8')
    except Exception as e:
        msg = f"Failed to write candidate tool to sandbox: {e}"
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    # Run it sandboxed
    run_cmd = f"python data/sandbox/candidate_{name}.py"
    # Wait, sandbox cwd is data/sandbox, so we should run it relative to that or run_sandboxed handles it.
    # Wait, run_sandboxed sets cwd to workdir or data/sandbox. If cwd is data/sandbox, we run it as python candidate_{name}.py!
    # Let's run it relative to repo root by specifying workdir=config.BASE_DIR
    res = run_sandboxed(f"python data/sandbox/candidate_{name}.py", timeout=30, workdir=str(config.BASE_DIR))
    
    if res["returncode"] != 0:
        msg = f"Tool test execution failed (return code {res['returncode']}).\nSTDOUT: {res['stdout']}\nSTDERR: {res['stderr']}"
        # Clean up candidate
        if candidate_path.exists():
            candidate_path.unlink()
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    # e. Move file to agent/generated_tools/
    dest_dir = Path(config.GENERATED_TOOLS_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{name}.py"
    
    try:
        # Move verified tool (we write the clean original code without the test runner main block, or move it directly)
        # Moving the candidate is requested: "move the file to agent\generated_tools\<name>.py and delete the candidate"
        # Let's copy it or move it.
        shutil.move(str(candidate_path), str(dest_path))
    except Exception as e:
        msg = f"Failed to save tool to generated tools directory: {e}"
        _log_forge_event(name, False)
        return {"success": False, "message": msg}

    _log_forge_event(name, True)
    return {"success": True, "message": f"Tool '{name}' forged successfully."}

def _log_forge_event(name: str, success: bool):
    """Safely logs a tool_forged tracer event."""
    try:
        trace_id = getattr(active_trace_storage, "trace_id", None)
        if trace_id:
            tracer_inst = Tracer()
            tracer_inst.log_event(trace_id, "tool_forged", {
                "name": name,
                "success": success
            })
    except Exception:
        pass
