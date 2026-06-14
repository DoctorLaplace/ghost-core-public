# agent/cortex/planner.py
import re
import os
import json
import logging
from pathlib import Path
from agent.effectors.sandbox import run_sandboxed

logger = logging.getLogger(__name__)

def generate_plans(task_description: str, context: str, llm_call) -> list[dict]:
    """
    Calls the LLM once to generate 2-3 alternative plans.
    On JSON parse failure, retries once. Returns a list of plan dicts.
    """
    prompt = f"""You are a planning assistant. Generate 2 to 3 plans for this task:
Task: {task_description}

Context:
{context}

Response must be ONLY a valid JSON array of objects, where each object has:
- "plan_id": string identifier
- "steps": list of strings (step descriptions)
- "estimated_risk": "low" | "medium" | "high"
- "estimated_steps": integer count of steps

Do not include any Markdown wrappers like ```json or anything else. Just the raw JSON.
"""
    try:
        resp = llm_call(prompt, purpose="orchestration")
        text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            cleaned = text.strip().replace("```json", "").replace("```", "").strip()
            res = json.loads(cleaned)
            if isinstance(res, list):
                return res
        except json.JSONDecodeError:
            pass
            
        # Retry once
        retry_prompt = prompt + "\n\nReturn ONLY valid JSON. Your previous response failed to parse. Do not include markdown block formatting."
        resp = llm_call(retry_prompt, purpose="orchestration")
        text = resp.text if hasattr(resp, "text") else str(resp)
        cleaned = text.strip().replace("```json", "").replace("```", "").strip()
        res = json.loads(cleaned)
        if isinstance(res, list):
            return res
        return []
    except Exception as e:
        logger.error(f"Failed to generate plans: {e}")
        return []

def critique_and_select(plans: list[dict], llm_call) -> dict:
    """
    Critiques candidate plans and returns the selected one.
    Uses cheap model tier.
    """
    if not plans:
        return {}
        
    prompt = f"""Review the following candidate plans and select the one with the best success-probability/cost ratio.
Candidate Plans:
{json.dumps(plans, indent=2)}

You MUST select exactly one plan. Respond with ONLY a valid JSON object matching the chosen plan exactly from the list.
Do not include any Markdown wrapper. Just the raw JSON.
"""
    try:
        resp = llm_call(prompt, purpose="classification")
        text = resp.text if hasattr(resp, "text") else str(resp)
        cleaned = text.strip().replace("```json", "").replace("```", "").strip()
        selected = json.loads(cleaned)
        
        # Verify it's one of the plans or matches plan_id
        selected_id = selected.get("plan_id")
        for plan in plans:
            if plan.get("plan_id") == selected_id:
                return plan
        return selected
    except Exception as e:
        logger.error(f"Failed to critique and select plan: {e}")
        return plans[0]

def dry_run_step(step: str) -> dict:
    """
    Performs heuristic dry-run grounding for a plan step.
    Returns {"grounded": bool, "reason": str}.
    """
    # 1. Check if step mentions a file path
    # Look for drive letter pattern, e.g. E:\... or C:\...
    match = re.search(r'([a-zA-Z]:\\[^\s]*)', step)
    if match:
        path_str = match.group(1).rstrip('."\'')
        parent_dir = os.path.dirname(path_str)
        if parent_dir:
            exists = os.path.exists(parent_dir)
            return {
                "grounded": exists,
                "reason": f"Parent directory '{parent_dir}' exists: {exists}"
            }
            
    # 2. Check if step is a read-only shell command
    cmd_clean = step.strip().lower()
    read_only_prefixes = ["dir", "type", "findstr", "git status", "python -c"]
    is_read_only = any(cmd_clean.startswith(prefix) for prefix in read_only_prefixes)
    
    if is_read_only:
        # Run it sandboxed with 'echo DRYRUN && ' prefixed
        res = run_sandboxed(f"echo DRYRUN && {step}", timeout=10)
        return {
            "grounded": True,
            "reason": f"Read-only shell command dry-run output: {res['stdout'].strip()}"
        }
        
    return {
        "grounded": True,
        "reason": "not dry-runnable"
    }
