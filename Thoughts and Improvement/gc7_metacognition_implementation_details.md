# Technical Implementation Details: GC7 Metacognition Framework

This document outlines the concrete technical architecture required to implement the advanced metacognition and robustness proposals for Ghost Core 7.

## 1. The Immutable Kernel & Mutable Cortex Bifurcation

**Implementation Approach:**
The system must be restructured at the file-system and process execution level.

*   **Directory Structure:**
    *   `/gc7/kernel/`: Contains `main.py`, `database.py`, `rollback_manager.py`, and `security_enforcer.py`. These files are strictly read-only to the agent process (enforced via OS-level file permissions where possible, and strict filtering in the `edit_cortex_code` tool).
    *   `/gc7/cortex/`: Contains `action_executor.py`, `context_builder.py`, `prompt_templates/`, and all dynamically loadable tool modules.
*   **Execution Model:**
    The `main.py` (Kernel) process spawns the AI loop. It dynamically imports modules from `/gc7/cortex/`. If a module in the Cortex fails to load or throws an unhandled exception during the main loop, the Kernel isolates the fault, logs the stack trace to the "Shadow Directory" for analysis, and triggers a rollback.

## 2. Quantitative Protocol Fitness and Darwinian Decay

**Implementation Approach:**
Shift `protocols.json` from a list of strings to a structured database (Neo4j or a dedicated SQLite table) to track metrics over time.

*   **Database Schema (Protocol Node):**
    *   `id`: UUID
    *   `name`: str
    *   `instruction`: str
    *   `fitness_score`: float (Initialized at 50.0)
    *   `invocation_count`: int
    *   `last_used`: timestamp
*   **Fitness Tracking Lifecycle:**
    1.  When `ContextBuilder` injects a protocol into the prompt, it registers the `protocol_id` with the current `task_id`.
    2.  When `GoalManager` marks `task_id` as `STATUS_COMPLETED`, the Kernel retrieves the linked `protocol_id`s and applies a positive delta (e.g., `+1.5`) to their `fitness_score`.
    3.  When `GoalManager` marks `task_id` as `STATUS_FAILED`, the Kernel applies a severe negative penalty (e.g., `-5.0`).
*   **Decay Mechanism:**
    A background `asyncio` worker (`protocol_janitor.py`) runs periodically. Any protocol where `fitness_score < 10.0` or `(current_date - last_used) > 30_days` is archived (removed from active context injection but kept for historical record).

## 3. The Simulation Matrix (Sandboxed "Dream State")

**Implementation Approach:**
Require isolated environment execution for proposed changes to prevent live-system corruption.

*   **Subprocess Sandboxing:**
    When the Metacognition engine proposes a new rule or tool, it does not write to the live `protocols.json` or live `/tools/` directory. It writes to a `/gc7/sandbox/` environment.
*   **Trace Replay Engine:**
    *   The `MemoryModule` must serialize full exact copies of the `stm` deque at the moment of task failure (the "Trace Snapshot").
    *   The Kernel spawns a detached Python `subprocess.run(["python", "sandbox_runner.py", trace_snapshot_path])`.
    *   The `sandbox_runner.py` initializes a mocked versions of the `ActionExecutor` (which prevents actual OS changes or API calls) and the `GoalManager`.
    *   It injects the proposed rule into the mock `ContextBuilder` and runs the Orchestrator loop against the trace snapshot.
*   **Verification Gate:**
    The Kernel monitors the subprocess. If the subprocess exits with code `0` (Success) within a timeout (e.g., 60 seconds), the proposed rule is promoted to the live repository. If it hangs (timeout) or exits with >`0`, the proposal is rejected.

## 4. Safe Self-Modification API (The Ouroboros Protocol)

**Implementation Approach:**
Implement a strict CI/CD pipeline purely orchestrated by the agent's internal Kernel.

*   **The `edit_cortex_code(file_path, diff_content)` Tool:**
    *   This tool writes changes *only* to a staging branch/directory (`/gc7/shadow_cortex/`).
*   **Automated Testing Suite (Pytest Integration):**
    *   The Kernel maintains a suite of unittests (`/gc7/tests/`) covering core functionalities (JSON parsing, basic tool loading, goal tree integrity).
    *   Upon detecting a change in `/shadow_cortex/`, the Kernel runs `pytest /gc7/tests/ --rootdir=/gc7/shadow_cortex/`.
*   **The Rollback Failsafe:**
    *   If tests pass, the Kernel stops the Orchestrator, utilizes `shutil` to hot-swap `/shadow_cortex/` into `/cortex/`, and restarts the Orchestrator.
    *   **The Canary Counter:** The Kernel initializes a `canary_counter = 10`. For the next 10 execution loops, if any unhandled crash occurs in the Cortex, the Kernel instantly restores the previous directory state from a `.bak` zip archive created right before the hot-swap.

## 5. Epistemic Confidence Auditing (The "Critic" Model)

**Implementation Approach:**
Run dynamic, parallel LLM analysis on the primary agent's outputs to serve as an active sanity check.

*   **The Intercept Pipeline:**
    In `orchestrator.py`, after the primary model generates its JSON response (containing `"thought"` and `"action"`), execution pauses.
*   **Critic Model Invocation (Lightweight & Fast):**
    The `"thought"` string is dispatched asynchronously to a fast, cheap model (e.g., `gemini-3-flash-8b` or similar light architecture).
    *   **Critic Prompt:** "Analyze the following AI agent thought process. Does it contain circular logic, assume facts not present in the stated memory, or exhibit dangerous overconfidence lacking verification? Output ONLY 'PASS' or 'FAIL: [Reason]'."
*   **Resolution:**
    *   If `PASS`, the `action` is executed normally.
    *   If `FAIL`, the `ActionExecutor` call is bypassed. Instead, the `ContextBuilder` appends a high-priority system inject: `[CRITIC OVERRIDE]: Your previous thought was flagged for epistemic failure: '{critic_reason}'. You must pause and use an information-gathering tool (search, inspect) to verify your assumptions before proceeding.`
