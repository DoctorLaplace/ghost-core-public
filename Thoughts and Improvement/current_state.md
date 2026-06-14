# Ghost Core 7 Upgrade: Current State

This document describes the current architectural status, completed capabilities, and active configuration settings of Ghost Core 7 as of June 11, 2026.

---

## 1. Upgrade Phase Progress

All 11 sequential development phases specified in `the_path.md` have been implemented and successfully verified through their respective acceptance gates.

### Completed Implementations

*   **Phase 0: Evaluation Harness & Tracing**
    *   Trace logging system writing thread-safe event files to `data/traces/*.jsonl`.
    *   Subprocess-based evaluation runner (`evals/run_evals.py`) configured with A/B ablation tests.
*   **Phase 1: Context Engineering & Prompt Budgeting**
    *   Strict prompt budgeting using priority-based allocation (budget cap: 24,000 tokens) with heuristic estimations.
*   **Phase 2: Model Router & Local Inference**
    *   Dynamic purpose routing allocating frontier models for task decisions, and cheap-tier models for auxiliary tasks.
*   **Phase 3: Security & Isolated Sandboxing**
    *   Subprocess terminal runner with character timeout rules and standard subprocess execution blocklist protection.
*   **Phase 4: Self-Authoring Tools**
    *   The `tool_forge` compilation engine safety-checking and sandboxing custom code inside `agent/generated_tools/`.
*   **Phase 5: Grounded Planning & Dry-Runs**
    *   Multi-plan generation and selection with safe read-only command dry-runs.
*   **Phase 6: GraphRAG & Memory Consolidation**
    *   Hybrid retrieval blending vector database and Neo4j graph lookup with similarity-based memory merging.
*   **Phase 7: Counterfactual Protocol Testing & Darwinian Decay**
    *   EMA score tracking for behavior protocols, with automated purging of low-scoring scripts.
*   **Phase 8: Local Model Data Flywheel**
    *   Dataset extraction pipeline compiling successful trace logs into instruction tuning format, with automatic API key redaction.
*   **Phase 9: Hot-Swap Cortex with Canary Deployments**
    *   Dynamic loading support for staging candidate modules inside `cortex_staging/` on a deterministic ratio of tasks.
*   **Phase 10: Swarm Spawning & Memory Quarantine**
    *   Multi-agent execution support where worker memory writes are routed to quarantined JSONL logs until parent validation.

---

## 2. Configuration Settings

The current active settings in `config.py` are:

*   **Frontier Model**: `GEMINI_MODEL_NAME` (Default: `gemini-3.5-flash`)
*   **Cheap Model**: `LIGHT_DUTY_MODEL_NAME` (Default: `gemini-3.1-flash-lite`)
*   **Local Model**: `ollama/llama3.1`
*   **Model Router**: `ROUTER_ENABLED = True` (Active)
*   **Grounded Planner**: `PLANNER_ENABLED = True` (Active)
*   **Canary Deployments**: `CANARY_ENABLED = False` (Ready to be enabled; ratio set to `0.1`)

---

## 3. Metacognition Proposal Status

Based on the proposals in `gc7_metacognition_proposals.md`:

1.  **Immutable/Mutable Partitioning**: Fully implemented. Core loop is isolated in `agent/kernel/` while behavior is mutable in `agent/cortex/`.
2.  **Darwinian Protocol Decay**: Fully implemented. Efficacy is mathematically tracked, and failed rules are retired.
3.  **Canary Deployments**: Fully implemented. Staging code is tested dynamically on target task ratios.
4.  **Dream State / Trace Replays**: Heuristic plan dry-running is implemented. Replaying failure traces inside a sandboxed simulation environment is pending.
5.  **Critic / Watchdog Model**: Real-time auditing of orchestrator reasoning by a watchdog model is pending.
