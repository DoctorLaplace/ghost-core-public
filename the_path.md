# THE PATH — GC7 Upgrade Implementation Manual

**Audience:** A low-capability executor AI. You are NOT expected to be creative. You ARE expected to be precise.
**Source of truth for strategy:** `Thoughts and Improvement/gc7_improvement_roadmap.md`. This document translates that roadmap into exact, executable instructions.

---

## SECTION A — MANDATORY RULES FOR THE EXECUTOR

Read these rules before every work session. Violating any rule means STOP and revert.

1. **One phase at a time.** Phases must be executed strictly in order (0 → 10). Never start Phase N+1 until Phase N's Acceptance Gate passes.
2. **One step at a time.** Within a phase, execute numbered steps in order. Do not merge, skip, or reorder steps.
3. **Git checkpoint before every phase.** Run: `git add -A && git commit -m "checkpoint: before phase <N>"`. If the repo is not a git repo, run `git init` first.
4. **Acceptance Gates are binary.** Run the exact command given. If output does not match the stated criterion, the phase FAILED. Execute the Rollback instruction, then retry the phase from step 1 at most twice. After two failures, stop and write a failure report to `upgrade_failures.md` describing the exact error output.
5. **Never modify these files unless a step explicitly names them:** `core_constitution.md`, `config.py` secrets/API keys, `main.py` entry logic, anything under `electron_app/node_modules/`.
6. **Never delete data.** Files under `data/` are append-only for you.
7. **All new code must be importable.** After creating any `.py` file, verify with: `python -c "import <module.path>"` from the repo root. Non-zero exit code = the step failed.
8. **Do not invent APIs.** If a step says "add function X with signature Y", implement exactly that signature.
9. **Windows environment.** Use `python` (not `python3`), backslashes in paths are acceptable, and shell is `cmd`.

Repository root for all relative paths below: `E:\Git Repositories\Laboratory\Cognition Models\GC7`

---

## SECTION B — SYSTEM MAP (what already exists)

```
GC7/
├── main.py                      # entry point
├── config.py                    # configuration constants
├── agent/
│   ├── kernel/                  # IMMUTABLE-LEANING CORE
│   │   ├── orchestrator.py      # main think-act loop (LLM decides next action)
│   │   ├── prompt_assembler.py  # builds the big context prompt
│   │   ├── model_client.py      # wraps the LLM API
│   │   ├── memory.py            # long/short-term memory manager
│   │   ├── goal_manager.py      # goals/tasks
│   │   ├── system_controls.py
│   │   └── db/ (vector_db.py, graph_db.py)
│   ├── cortex/                  # MUTABLE METACOGNITION
│   │   ├── metacognition.py, introspection.py, protocol_manager.py,
│   │   ├── context_optimizer.py, workspace_manager.py, action_executor.py
│   ├── volition/                # CORE CONSTITUTIONS & PERSONAS
│   │   ├── core_constitution.md # active constitution
│   │   └── personas/            # dynamic persona files
│   │       └── *.md
│   ├── cognition/               # tool definitions (planning, knowledge, protocol, workspace)
│   ├── effectors/               # terminal.py, file_system.py, web_search.py, ui_control.py
│   ├── perception/, sensors/
│   └── generated_tools/         # hot-load dir for self-authored tools (currently empty)
├── server/main.py               # backend server
└── data/
```

---

## PHASE 0 — Evaluation Harness & Tracing (DO THIS FIRST)

**Objective:** Make improvement measurable. No later phase may be validated without this.

**Files to create:** `evals/__init__.py`, `evals/tasks.json`, `evals/run_evals.py`, `agent/kernel/tracer.py`
**Files to modify:** `agent/kernel/orchestrator.py`, `agent/kernel/model_client.py`

### Steps
1. Create directory `evals\` with empty `__init__.py`.
2. Create `evals\tasks.json`: a JSON list of at least 30 task objects, each with exactly these keys: `id` (string), `prompt` (string instruction), `category` (one of: `file_ops`, `research`, `reasoning`, `coding`), `verify_type` (one of: `file_exists`, `file_contains`, `command_exit_zero`, `regex_match_answer`), `verify_arg` (string). Populate with deterministic tasks, e.g. `{"id": "f01", "prompt": "Create a file named eval_out_f01.txt containing exactly the word DONE", "category": "file_ops", "verify_type": "file_contains", "verify_arg": "eval_out_f01.txt::DONE"}`. Write 10 file_ops, 5 research, 10 reasoning, 5 coding tasks following this pattern.
3. Create `agent\kernel\tracer.py` with exactly this public API:
   - `class Tracer` with methods `start_trace(task_id: str) -> str` (returns trace_id), `log_event(trace_id: str, event_type: str, payload: dict) -> None`, `end_trace(trace_id: str, outcome: str) -> None`.
   - Implementation: append JSON lines to `data\traces\{trace_id}.jsonl`. Each line: `{"ts": <iso utc>, "event_type": ..., "payload": ...}`. Create the directory if missing. Use only stdlib (`json`, `os`, `datetime`, `uuid`).
4. Modify `agent\kernel\model_client.py`: locate the function/method that sends the request to the LLM. Immediately before sending, and immediately after receiving, call the Tracer (`event_type="llm_request"` / `"llm_response"`, payload containing prompt length in characters, model name, and for responses: latency in seconds and response length). Instantiate one module-level `Tracer()`. Guard all tracer calls in `try/except Exception: pass` so tracing can NEVER crash the agent.
5. Modify `agent\kernel\orchestrator.py`: at the point where a tool is about to be executed, log `event_type="tool_call"` with payload `{"tool": name, "args_keys": list(args.keys())}`. After execution, log `event_type="tool_result"` with payload `{"tool": name, "success": bool, "result_len": len(str(result))}`. Same try/except guard.
6. Create `evals\run_evals.py`: a script that (a) loads `tasks.json`, (b) for each task invokes the agent on the prompt (import and call the same entry path `main.py` uses, with a hard timeout of 300s per task via `subprocess` if direct import is impractical), (c) runs the verification per `verify_type`, (d) writes `evals\results_<UTC timestamp>.json` containing per-task pass/fail, duration, and aggregate pass-rate per category. Add `--dry-verify` flag that only runs verifications against existing artifacts (used for testing the harness itself).
7. Cleanup: delete any `eval_out_*.txt` artifacts after each run inside `run_evals.py`.

### Acceptance Gate
- `python -c "from agent.kernel.tracer import Tracer; t=Tracer(); tid=t.start_trace('x'); t.log_event(tid,'test',{}); t.end_trace(tid,'ok'); print('TRACER_OK')"` — must print `TRACER_OK` with exit code 0, AND a new `.jsonl` file must exist under `data\traces\`.
- `python evals\run_evals.py --dry-verify` — must exit with code 0 and write a `results_*.json` file into `evals\`.

### Rollback
`git reset --hard HEAD && git clean -fd evals agent\kernel\tracer.py`

### Do-NOT list
- Do NOT make the tracer raise exceptions to callers. Ever.
- Do NOT call the LLM inside the tracer or the verifier.

---

## PHASE 1 — Context Engineering & Prompt Budgeting

**Objective:** Stop blind log-dumping into the prompt; enforce a hard token budget.

**Files to create:** `agent/kernel/token_budget.py`
**Files to modify:** `agent/kernel/prompt_assembler.py`

### Steps
1. Create `agent\kernel\token_budget.py` with exactly this API:
   - `def estimate_tokens(text: str) -> int` — return `max(1, len(text) // 4)` (cheap heuristic; do NOT add a tokenizer dependency).
   - `def fit_to_budget(sections: list[tuple[str, str, int]], max_tokens: int) -> dict[str, str]` — input is a list of `(section_name, content, priority)` where priority 1 is most important. Sort by priority ascending; include whole sections until the budget is exhausted; for the first section that does not fit, truncate it to the remaining budget by character count (`remaining_tokens * 4` chars) and append the literal marker `
[TRUNCATED]`; drop all lower-priority sections entirely. Return `{section_name: final_content}`.
2. In `agent\kernel\prompt_assembler.py`, find where the final prompt string is concatenated. Refactor so each major block (constitution, protocols, workspace, insights, episodic memories, event log) is built as a separate string, then passed through `fit_to_budget` with `max_tokens = 24000` and these priorities: constitution=1, current task=1, protocols=2, workspace=3, event log=4, insights=5, episodic=6. Concatenate the returned sections in the original order.
3. Add a tracer event `event_type="prompt_budget"` with payload `{"total_tokens_est": int, "dropped_sections": [names]}` (guarded by try/except).

### Acceptance Gate
- `python -c "from agent.kernel.token_budget import fit_to_budget, estimate_tokens; r=fit_to_budget([('a','x'*100000,2),('b','y'*100,1)], 50); print('OK' if 'b' in r and len(r.get('a',''))<100000 else 'FAIL')"` — must print `OK`.
- Run the agent on one trivial task (e.g. "create file ping.txt containing pong") and confirm a `prompt_budget` event appears in the newest trace file.

### Rollback
`git reset --hard HEAD`

---

## PHASE 2 — Model Router & Local Inference

**Objective:** Route cheap/simple LLM calls to a cheap model; keep the frontier model only for orchestration.

**Files to create:** `agent/kernel/model_router.py`
**Files to modify:** `agent/kernel/model_client.py`, `config.py` (additive only)

### Steps
1. Append to `config.py` (do not modify existing lines): `MODEL_TIERS = {"frontier": "<current model name from config>", "cheap": "<cheap model name>", "local": "ollama/llama3.1"}` and `ROUTER_ENABLED = True`.
2. Create `agent\kernel\model_router.py` with exactly this API:
   - `def classify_call(purpose: str) -> str` — `purpose` is one of: `orchestration`, `summarization`, `classification`, `title_generation`, `memory_scoring`, `embedding_text`. Return `"frontier"` for `orchestration`, `"cheap"` for everything else. Pure dict lookup, no LLM call.
   - `def resolve_model(purpose: str) -> str` — returns `MODEL_TIERS[classify_call(purpose)]`; if `ROUTER_ENABLED` is False, always return the frontier model.
3. In `model_client.py`, add an optional keyword argument `purpose: str = "orchestration"` to the main request function. Use `resolve_model(purpose)` to pick the model. Existing callers need no changes (default preserves behavior).
4. Find every internal call site that does summarization/title/scoring (search for them with `findstr /s /i "summar title score" agent\*.py`) and pass the correct `purpose`.
5. (Optional sub-step, skip if Ollama is not installed): verify local inference with `ollama list`; if the command fails, leave `local` tier unused and note it in `upgrade_failures.md` as a WARNING, not a failure.

### Acceptance Gate
- `python -c "from agent.kernel.model_router import resolve_model; import config; assert resolve_model('orchestration')==config.MODEL_TIERS['frontier']; assert resolve_model('summarization')==config.MODEL_TIERS['cheap']; print('ROUTER_OK')"` — must print `ROUTER_OK`.
- Run Phase 0 eval harness with `--dry-verify`: must still exit 0.

### Rollback
`git reset --hard HEAD`

---

## PHASE 3 — Security & Isolated Sandboxing

**Objective:** Self-generated code must not be able to damage the host.

**Files to create:** `agent/effectors/sandbox.py`
**Files to modify:** `agent/effectors/terminal.py`

### Steps
1. Create `agent\effectors\sandbox.py` with exactly this API:
   - `def run_sandboxed(command: str, timeout: int = 60, workdir: str = None) -> dict` — returns `{"stdout": str, "stderr": str, "returncode": int, "timed_out": bool}`.
   - Implementation: use `subprocess.run` with `shell=True`, `capture_output=True`, `timeout=timeout`, and `cwd=workdir or a dedicated folder `data\sandbox\` (create if missing). On `TimeoutExpired`, return `timed_out=True`, `returncode=-1`.
   - Add a module-level constant `BLOCKED_PATTERNS = ["format ", "del /s", "rd /s", "rmdir /s", "reg delete", "shutdown", "vssadmin", "cipher /w", "bcdedit"]`. Before executing, lowercase the command and check substring matches; if any pattern matches, do NOT execute — return `{"stdout": "", "stderr": "BLOCKED: matched pattern <p>", "returncode": -2, "timed_out": False}`.
2. In `agent\effectors\terminal.py`, locate the existing command-execution function. Add a parameter `sandbox: bool = False`. When `sandbox=True`, delegate entirely to `run_sandboxed`. Do NOT change default behavior for existing callers.
3. Create directory `data\sandbox\` with a file `README.txt` containing: `Scratch area for sandboxed execution. Contents are disposable.`
4. Add tracer event `event_type="sandbox_exec"` with payload `{"blocked": bool, "returncode": int}` inside `run_sandboxed` (guarded try/except).

### Acceptance Gate
- `python -c "from agent.effectors.sandbox import run_sandboxed; r=run_sandboxed('echo hi'); assert r['returncode']==0 and 'hi' in r['stdout']; b=run_sandboxed('shutdown /s'); assert b['returncode']==-2; print('SANDBOX_OK')"` — must print `SANDBOX_OK`.

### Rollback
`git reset --hard HEAD && git clean -fd agent\effectors\sandbox.py data\sandbox`

### Do-NOT list
- Do NOT route ALL terminal calls through the sandbox automatically; only when `sandbox=True` is passed. Phase 4 will use it explicitly.
- Do NOT attempt Docker/VM integration in this phase. Substring blocking + timeout + isolated cwd is the deliverable.

---

## PHASE 4 — Self-Authoring Tools

**Objective:** The agent can write, test, and hot-load new Python tools into `agent/generated_tools/`.

**Files to create:** `agent/cortex/tool_forge.py`
**Files to modify:** the tool-registration module (find it: `findstr /s /n "def get_tools\|TOOL_REGISTRY\|register_tool" agent\*.py` and modify whichever file builds the tool list given to the orchestrator).

### Steps
1. Create `agent\cortex\tool_forge.py` with exactly this API:
   - `def forge_tool(name: str, code: str) -> dict` — returns `{"success": bool, "message": str}`.
   - Implementation order (all must pass, in order, before the file is written to its final location):
     a. Validate `name` matches regex `^[a-z][a-z0-9_]{2,40}$`. Fail otherwise.
     b. Validate `code` compiles: `compile(code, name, 'exec')` inside try/except. Fail on SyntaxError.
     c. Static safety scan: reject if code contains any of: `os.remove`, `shutil.rmtree`, `subprocess`, `eval(`, `exec(`, `__import__`, `open(` with mode `'w'` on absolute paths outside the repo. (Simple substring checks are acceptable.)
     d. Write code to `data\sandbox\candidate_<name>.py`. The code MUST define a function with the same name as the tool and a top-level `TEST()` function returning True on self-test pass. Run it sandboxed: `run_sandboxed('python data\\sandbox\\candidate_<name>.py')` where the candidate file ends with `if __name__=="__main__": import sys; sys.exit(0 if TEST() else 1)`.
     e. Only if returncode==0: move the file to `agent\generated_tools\<name>.py` and delete the candidate.
2. Modify the tool-registration module: at startup, glob `agent\generated_tools\*.py` (excluding `__init__.py`), import each via `importlib`, and register the function whose name matches the filename. Wrap each import in try/except; a broken generated tool must be skipped with a logged warning, never crash startup.
3. Add tracer events `tool_forged` (payload: name, success) and `tool_load_failed` (payload: name, error string).

### Acceptance Gate
- `python -c "from agent.cortex.tool_forge import forge_tool; r=forge_tool('add_two_numbers', 'def add_two_numbers(a, b):
    return a + b

def TEST():
    return add_two_numbers(2, 3) == 5

if __name__==\"__main__\": import sys; sys.exit(0 if TEST() else 1)'); assert r['success'], r['message']; print('FORGE_OK')"` — must print `FORGE_OK` AND `agent\generated_tools\add_two_numbers.py` must exist.
- Restart the agent; the new tool must appear in its tool list without errors.

### Rollback
`git reset --hard HEAD && git clean -fd agent\generated_tools agent\cortex\tool_forge.py`

### Do-NOT list
- Do NOT allow forged tools to bypass the static safety scan, even if a test passes.
- Do NOT auto-forge tools without an explicit orchestrator decision; the forge is a tool, not a reflex.

---

## PHASE 5 — Grounded Planning & Dry-Runs

**Objective:** Replace greedy single-step choice with: propose 2-3 plans → critique → dry-run the winner's first step where possible.

**Files to create:** `agent/cortex/planner.py`
**Files to modify:** `agent/kernel/orchestrator.py`

### Steps
1. Create `agent\cortex\planner.py` with exactly this API:
   - `def generate_plans(task_description: str, context: str, llm_call) -> list[dict]` — calls the LLM (via the passed-in `llm_call` callable, `purpose="orchestration"`) ONCE with a prompt demanding JSON output: a list of 2-3 plans, each `{"plan_id": str, "steps": [str, ...], "estimated_risk": "low|medium|high", "estimated_steps": int}`. Parse with `json.loads`; on parse failure, retry once with an appended instruction "Return ONLY valid JSON"; on second failure return `[]`.
   - `def critique_and_select(plans: list[dict], llm_call) -> dict` — one LLM call (`purpose="classification"`, i.e. cheap tier) asking it to pick the plan with the best success-probability/cost ratio; returns the selected plan dict; if `plans` is empty return `{}`.
   - `def dry_run_step(step: str) -> dict` — heuristic grounding, NO LLM: if the step mentions reading/writing a file path, check the parent directory exists and return `{"grounded": bool, "reason": str}`; if the step is a shell command, run it with `run_sandboxed` prefixed by `echo DRYRUN && ` only when it is read-only (starts with `dir`, `type`, `findstr`, `git status`, `python -c`); otherwise return `{"grounded": True, "reason": "not dry-runnable\"}`.
2. Modify `agent\kernel\orchestrator.py`: at the START of a new task only (not every step), call `generate_plans` then `critique_and_select`. Store the selected plan (JSON string) in the workspace via the existing workspace manager. Before executing the plan's FIRST step, call `dry_run_step`; if `grounded` is False, log it and regenerate plans exactly once. Gate all of this behind a new additive config flag `PLANNER_ENABLED = True` in `config.py`; if False, the old greedy behavior runs untouched.
3. Add tracer events: `plan_generated` (payload: count of plans), `plan_selected` (payload: plan_id, estimated_risk), `dry_run` (payload: grounded, reason). All guarded by try/except.

### Acceptance Gate
- `python -c "from agent.cortex.planner import dry_run_step; r=dry_run_step('write file E:\
onexistent_dir_zz\\x.txt'); assert r['grounded']==False; r2=dry_run_step('dir'); assert 'grounded' in r2; print('PLANNER_OK')"` — must print `PLANNER_OK`.
- Run `python evals\run_evals.py` (full run). Aggregate pass-rate must be >= the Phase 0 baseline minus 5 percentage points. If lower, the phase FAILED.

### Rollback
`git reset --hard HEAD && git clean -fd agent\cortex\planner.py`

### Do-NOT list
- Do NOT add more than 2 extra LLM calls per task (1 generate + 1 critique). Plans are made once per task, not per step.
- Do NOT let `dry_run_step` execute write-effect commands. Only the read-only whitelist given above.

---

## PHASE 6 — GraphRAG & Memory Consolidation

**Objective:** Retrieval returns connected context (entities, related tasks, failures), not just nearest vectors. Old memories get consolidated, never silently deleted.

**Files to create:** `agent/kernel/db/graph_retriever.py`
**Files to modify:** `agent/kernel/memory.py`, `agent/kernel/db/graph_db.py` (additive functions only)

### Steps
1. In `graph_db.py`, add (do not change existing functions): `def add_entity_edge(memory_id: str, entity: str, relation: str) -> None` and `def get_neighbors(entity: str, limit: int = 20) -> list[dict]` returning `[{"memory_id":..., "entity":..., "relation":...}]`.
2. Create `agent\kernel\db\graph_retriever.py` with exactly this API:
   - `def retrieve_connected(query_text: str, vector_results: list[dict], hops: int = 1) -> list[dict]` — for each vector hit, extract its `memory_id`, call `get_neighbors` on every entity linked to that memory, and merge neighbor memories into the result list (deduplicated by `memory_id`). Return at most 15 items, vector hits first, neighbors after.
3. Modify `agent\kernel\memory.py`:
   - At memory-write time: extract entities with a simple cheap-tier LLM call (`purpose="classification"`) returning JSON `{"entities": [str, ...]}` (max 5 entities). For each entity call `add_entity_edge(memory_id, entity, "mentions")`. Guard with try/except — entity extraction failure must never block a memory write.
   - At retrieval time: pass vector search results through `retrieve_connected` before returning.
4. Memory consolidation job: add `def consolidate_memories(memory_manager) -> dict` to `memory.py`. It (a) finds pairs of memories with vector similarity > 0.95, (b) merges them into one record with combined text via cheap-tier summarization, (c) marks originals with a field `"superseded_by": <new_id>` — NEVER hard-delete. Returns `{"merged": int}`. Do NOT schedule it automatically; expose it as a callable tool only.
5. Tracer events: `graph_retrieval` (payload: vector_hits, neighbors_added) and `memory_consolidation` (payload: merged count).

### Acceptance Gate
- `python -c "from agent.kernel.db.graph_retriever import retrieve_connected; r=retrieve_connected('test', []); assert isinstance(r, list); print('GRAPH_OK')"` — must print `GRAPH_OK`.
- Full eval run: pass-rate >= baseline minus 5 points.

### Rollback
`git reset --hard HEAD && git clean -fd agent\kernel\db\graph_retriever.py`

### Do-NOT list
- Do NOT hard-delete any memory record. `superseded_by` marking only.
- Do NOT use the frontier model for entity extraction or merge-summaries. Cheap tier only.

---

## PHASE 7 — Counterfactual Protocol Testing & Darwinian Decay

**Objective:** Self-authored protocols must prove their worth empirically or be removed automatically.

**Files to create:** `agent/cortex/protocol_fitness.py`
**Files to modify:** `agent/cortex/protocol_manager.py` (additive)

### Steps
1. Create `agent\cortex\protocol_fitness.py` with exactly this API:
   - `def init_fitness_store() -> None` — creates `data\protocol_fitness.json` (`{}` if missing).
   - `def record_outcome(protocol_name: str, task_succeeded: bool) -> None` — load the JSON; each protocol entry is `{"score": float, "trials": int}` starting at `{"score": 1.0, "trials": 0}`. On success: `score = score * 0.9 + 1.0 * 0.1`. On failure: `score = score * 0.9`. Increment trials. Save.
   - `def get_doomed_protocols(min_trials: int = 10, threshold: float = 0.4) -> list[str]` — return names with `trials >= min_trials` and `score < threshold`.
2. In `protocol_manager.py`, add function `def purge_doomed() -> list[str]` that calls `get_doomed_protocols()` and removes each from the active protocol list, writing the removed protocol text to `data\retired_protocols.md` (append-only) before removal. Do NOT call it automatically yet — expose as a tool.
3. A/B harness: add `--protocol-ablation <name>` flag to `evals\run_evals.py`: runs the full suite twice, once normally and once with the named protocol disabled, and prints both pass-rates plus the delta.
4. In `orchestrator.py`, after each task completes (success or failure), call `record_outcome` for every currently-active protocol (guarded try/except).

### Acceptance Gate
- `python -c "from agent.cortex.protocol_fitness import init_fitness_store, record_outcome, get_doomed_protocols; init_fitness_store(); [record_outcome('zombie', False) for _ in range(12)]; assert 'zombie' in get_doomed_protocols(); print('FITNESS_OK')"` — must print `FITNESS_OK`.

### Rollback
`git reset --hard HEAD && git clean -fd agent\cortex\protocol_fitness.py`

### Do-NOT list
- Do NOT decay or purge anything in `core_constitution.md`. Fitness applies ONLY to self-authored protocols.

---

## PHASE 8 — Local Model Data Flywheel

**Objective:** Convert successful traces into a fine-tuning dataset for a local model.

**Files to create:** `flywheel/extract_dataset.py`, `flywheel/__init__.py`
**Files to modify:** none.

### Steps
1. Create directory `flywheel\` with empty `__init__.py`.
2. Create `flywheel\extract_dataset.py`:
   - Reads every `data\traces\*.jsonl` whose final `end_trace` outcome is `"success"`.
   - For each `llm_request`/`llm_response` pair within those traces, emit one JSONL record to `flywheel\dataset.jsonl`: `{"messages": [{"role": "user", "content": <prompt>}, {"role": "assistant", "content": <response>}]}`.
   - Filter: skip any pair where the prompt contains an API key pattern (regex `[A-Za-z0-9_\-]{30,}`) inside lines containing `key`, `token`, or `secret` (case-insensitive) — redact those lines to `[REDACTED]` instead of skipping the whole pair.
   - Print summary: number of traces scanned, pairs extracted, pairs redacted.
3. Fine-tuning itself is OUT OF SCOPE for the executor. Stop after dataset generation. A human or higher-tier agent runs the actual fine-tune (e.g., with Ollama/axolotl). Write a note in `flywheel\README.md` stating exactly this.

### Acceptance Gate
- `python flywheel\extract_dataset.py` — must exit 0 and create `flywheel\dataset.jsonl` (file may be empty if no successful traces exist yet; empty file is still a PASS).
- `python -c "import json; [json.loads(l) for l in open('flywheel/dataset.jsonl', encoding='utf-8') if l.strip()]; print('DATASET_OK')"` — must print `DATASET_OK` (every line is valid JSON).

### Rollback
`git reset --hard HEAD && git clean -fd flywheel`

### Do-NOT list
- Do NOT attempt to run a fine-tune job yourself.
- Do NOT include traces whose outcome is not exactly `"success"`.

---

## PHASE 9 — Hot-Swap Cortex with Canary Deployments

**Objective:** Self-modified cortex code is tested on a fraction of tasks before promotion; kernel stays immutable and can always roll back.

**Files to create:** `agent/kernel/canary.py`, `cortex_staging/` directory
**Files to modify:** `agent/kernel/orchestrator.py` (additive), `config.py` (additive)

### Steps
1. Append to `config.py`: `CANARY_ENABLED = False` and `CANARY_RATIO = 0.1`. (Disabled by default — enabling is a human/Director decision.)
2. Create directory `cortex_staging\` with empty `__init__.py`. This is where candidate cortex modules are placed (same filenames as `agent\cortex\`).
3. Create `agent\kernel\canary.py` with exactly this API:
   - `def should_use_canary(task_id: str) -> bool` — deterministic: `return CANARY_ENABLED and (hash(task_id) % 100) < int(CANARY_RATIO * 100)`. No randomness, so reruns are reproducible.
   - `def load_cortex_module(module_name: str, canary: bool)` — if `canary` is True AND `cortex_staging\<module_name>.py` exists AND it compiles (`compile()` check), import it from staging via `importlib.util.spec_from_file_location`; otherwise import the stable `agent.cortex.<module_name>`. ALL exceptions during staging import → fall back to stable module and log tracer event `canary_fallback` with the error string.
   - `def record_canary_result(task_id: str, module_name: str, success: bool) -> None` — append to `data\canary_results.jsonl`.
   - `def evaluate_promotion(module_name: str, min_trials: int = 20) -> str` — read `canary_results.jsonl`; if the module has >= min_trials canary runs AND canary success-rate >= stable success-rate (computed from trace outcomes over the same period), return `"PROMOTE"`; else `"HOLD"`. NEVER auto-promote: promotion (copying staging file over `agent\cortex\`) requires explicit Director approval — print the recommendation only.
4. In `orchestrator.py`, where cortex modules are imported/used, route through `load_cortex_module(name, should_use_canary(task_id))`, gated behind `CANARY_ENABLED`. When the flag is False the code path must be byte-for-byte equivalent to current behavior.
5. Tracer events: `canary_used` (payload: module_name, task_id), `canary_fallback` (payload: error).

### Acceptance Gate
- `python -c "from agent.kernel.canary import should_use_canary, load_cortex_module; assert should_use_canary('x') in (True, False); m=load_cortex_module('metacognition', canary=False); assert m is not None; print('CANARY_OK')"` — must print `CANARY_OK`.
- Full eval run with `CANARY_ENABLED = False`: pass-rate must equal the pre-phase baseline exactly (the disabled path must be a no-op).

### Rollback
`git reset --hard HEAD && git clean -fd agent\kernel\canary.py cortex_staging`

### Do-NOT list
- Do NOT ever place kernel files (`agent\kernel\*`) in staging. Canary applies to cortex modules ONLY.
- Do NOT auto-promote. `evaluate_promotion` recommends; the Director decides.

---

## PHASE 10 — Multi-Agent Spawning with Write Quarantine

**Objective:** Spawn worker sub-agents for parallel research/coding; their memory writes are quarantined until the parent validates them.

**Files to create:** `agent/kernel/swarm.py`
**Files to modify:** `agent/kernel/memory.py` (additive)

### Steps
1. Create `agent\kernel\swarm.py` with exactly this API:
   - `def spawn_worker(task_prompt: str, worker_id: str, timeout: int = 600) -> dict` — launches a separate agent process via `subprocess.Popen` running the same entry point with env vars `GC7_WORKER_ID=<worker_id>` and `GC7_MEMORY_QUARANTINE=1`. Returns `{"worker_id": str, "returncode": int, "output": str, "timed_out": bool}` after waiting (with timeout).
   - `def collect_quarantine(worker_id: str) -> list[dict]` — reads `data\quarantine\<worker_id>.jsonl` and returns the parsed records; empty list if file missing.
   - `def integrate_quarantine(worker_id: str, approved_ids: list[str]) -> int` — writes ONLY the approved records into global LTM via the normal memory manager write path, marks the quarantine file as processed by renaming it to `<worker_id>.processed.jsonl`, and returns the count integrated.
2. Modify `agent\kernel\memory.py`: in the long-term-memory write function, check `os.environ.get("GC7_MEMORY_QUARANTINE") == "1"`. If set, append the record as a JSON line to `data\quarantine\<GC7_WORKER_ID>.jsonl` (create dir if missing) INSTEAD of writing to global LTM. Everything else about the worker runs normally.
3. Parent validation flow (manual tooling, no automation yet): parent agent calls `collect_quarantine`, reviews each record (cheap-tier LLM call asking "is this record factual, non-duplicative, and useful? YES/NO"), and passes only YES ids to `integrate_quarantine`.
4. Limit: max 2 concurrent workers. Enforce with a module-level counter in `swarm.py`; `spawn_worker` returns `{"returncode": -3, "output": "WORKER_LIMIT"}` if exceeded.
5. Tracer events: `worker_spawned` (payload: worker_id), `quarantine_integrated` (payload: worker_id, count).

### Acceptance Gate
- `python -c "from agent.kernel.swarm import collect_quarantine, integrate_quarantine; assert collect_quarantine('nonexistent_worker')==[]; print('SWARM_OK')"` — must print `SWARM_OK`.
- Manual test: set `GC7_MEMORY_QUARANTINE=1` and `GC7_WORKER_ID=testw` in a shell, run the agent on one trivial memory-writing task, and confirm `data\quarantine\testw.jsonl` exists and global LTM did NOT receive the record.

### Rollback
`git reset --hard HEAD && git clean -fd agent\kernel\swarm.py data\quarantine`

### Do-NOT list
- Do NOT let workers spawn their own sub-workers (check: if `GC7_WORKER_ID` is already set, `spawn_worker` must refuse with returncode -4).
- Do NOT integrate quarantined memories without the per-record YES/NO validation step.

---

## SECTION C — COMPLETION CHECKLIST

After all 10 phases pass their gates, perform the final audit:

1. `git log --oneline` shows a checkpoint commit before every phase. ✔
2. `python evals\run_evals.py` full run: final pass-rate must be >= Phase 0 baseline. Record both numbers in `upgrade_report.md`.
3. Every file in this manual's "Files to create" lists exists. Verify with `dir` per path.
4. `data\traces\` contains traces with `llm_request`, `tool_call`, `prompt_budget`, and `sandbox_exec` event types (use `findstr /m "prompt_budget" data\traces\*.jsonl`).
5. Write `upgrade_report.md` in the repo root: one line per phase: `Phase N: PASS (gate output: <verbatim>)`.
6. Final commit: `git add -A && git commit -m "GC7 upgrade complete: phases 0-10"`.

If any audit item fails, the corresponding phase is reopened. Do not declare completion until all six items check out.

**END OF THE PATH.**
