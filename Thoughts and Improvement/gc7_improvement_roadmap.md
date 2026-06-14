# Ghost Core 7 -- Path to Qualitative Intelligence Leap

This document establishes the architectural roadmap for GC7. It moves the system from a greedy, single-step execution agent to an empirically measured, secure, and recursively self-improving super-system. Progress is gated by strict metrics, ensuring that every evolutionary leap is validated rather than assumed.

---

## The Strategic Paradigm

1. **Instruments Before Experiments**: A system without a measurement system cannot improve. We prioritize the evaluation harness as Priority 0.
2. **Grounded Over Hallucinated Simulation**: We reject pure LLM-based imagination for planning. All search branches must be grounded in cheap physical dry-runs, sandboxed tests, and real-world system feedback.
3. **Defensive Self-Modification**: Code or protocol synthesis without a security framework and containment model is self-sabotage. Robust sandboxing and immutability must precede self-authoring.
4. **Prompt Economics**: Compute and token constraints are physical boundaries. Dynamic prompt budgeting and context engineering must optimize our footprint before scale is attempted.

---

## Priority-Ordered Execution Milestones

```
+--------------------------------------------------------+
|         MILESTONE 0: EMPIRICAL HARNESS & TRACING       |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 1: CONTEXT & PROMPT ECONOMICS        |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 2: MODEL ROUTER & LOCAL INFERENCE    |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 3: SECURITY & ISOLATED SANDBOXING    |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 4: SELF-AUTHORING TOOLS              |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 5: GROUNDED PLANNING & DRY-RUNS      |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 6: GRAPHRAG & RETRIEVAL EVALUATION   |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 7: COUNTERFACTUAL METAGCOGNITION     |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 8: LOCAL MODEL FLYWHEEL & DISTILL    |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 9: CORTEX HOT-SWAP WITH CANARIES     |
+---------------------------+----------------------------+
                            |
                            v
+--------------------------------------------------------+
|         MILESTONE 10: MULTI-AGENT WRITE QUARANTINE     |
+--------------------------------------------------------+
```

### Milestone 0: Empirical Foundation & Tracing (Immediate Priority)
Before modifying cognitive parameters, we must be able to prove whether an alteration is an improvement.
- **0.1 Frozen Evaluation Suite**: Build a collection of 50-100 representative deterministic tasks spanning file operations, research, reasoning, and coding with automated verification rules.
- **0.2 Complete Execution Tracing**: Instrument every prompt, response, tool call, execution latency, and token cost into a persistent trace log.
- **0.3 Failure Taxonomy Engine**: Parse failures into structured classes (e.g., Tool Selection Error, Context Overflow, Hallucinated Path) to direct self-correction logic.

### Milestone 1: Context Engineering & Prompt Budgeting
Reduce token waste and prevent context decay from degrading model attention.
- **1.1 Dynamic Token Budgeting**: Calculate exact context utilization pre-flight and dynamically truncate or summarize historical trajectories.
- **1.2 Relevance-Ranked Assembly**: Move from blind log dumping to an importance-weighted inclusion mechanism for memories and logs.

### Milestone 2: Multi-Model Router & Local Support
Maximize computational cost-efficiency and secure offline redundancy.
- **2.1 ModelRouter**: Implement a classification routing layer that directs low-complexity steps (like goal renaming or classification) to lightweight models, keeping commercial frontier models for orchestration.
- **2.2 Local Inference Integration**: Configure Ollama or vLLM backends to run open-weight models on local hardware for routine evaluations.

### Milestone 3: Defensive Security & Sandboxing Model
Protect the system host from self-generated errors and external injections.
- **3.1 Containerized Execution**: Move all bash execution, file writes, and dynamic script runs into an isolated environment or lightweight VM.
- **3.2 Injection Safeguards**: Enforce hard boundaries between read data payloads and instructions to prevent hijacking during web scans or document parsing.

### Milestone 4: Self-Authoring Tools
Empower GC7 to break past the static 29-tool threshold.
- **4.1 Dynamic Tool Synthesis**: Establish an automated generation loop that writes, compiles, and loads local Python utilities when existing tools cannot satisfy goals.
- **4.2 Tool Registry with Automated Lifecycle**: Deprecate low-use tools, quarantine new scripts under strict unit tests, and index tools dynamically to prevent Orchestrator prompt bloat.

### Milestone 5: Grounded Planning & Value Verification
Transition the Orchestrator from greedy choices to strategic foresight.
- **5.1 Plan Generation & Critic**: Propose 2-3 structured steps paths, criticize their resource-feasibility, and rank them using the LLM and historical rules.
- **5.2 Physical Dry-Run Simulator**: Ground the plan's evaluation by trying actions on sandbox state/filesystem snapshots rather than relying on hallucinated model predictions.

### Milestone 6: Associative Memory (GraphRAG)
Evolve vector search into relational mapping.
- **6.1 Graph-Augmented Retrieval**: Couple semantic search with a structural knowledge graph, retrieving connected context (entities, tasks, failures) dynamically.
- **6.2 Memory Consolidation**: Periodically review stored memories to merge duplicates and prune dead records based on importance-weighted recall frequency.

### Milestone 7: Counterfactual Protocols
Validate metacognitive optimization.
- **7.1 A/B Protocol Testing**: Run the evaluation harness with and without specific synthesized instructions to test real performance differences.
- **7.2 Darwinian Decay**: Assign fitness values to custom prompt rules; successful runs boost scores, while failures decay and eventually delete them.

### Milestone 8: Local Model Data Flywheel
Build a specialized, autonomous brain to run GC7's inner layers.
- **8.1 Trajectory Distillation**: Collect high-performing tracing logs, clean them into instruction-tuning pairs, and fine-tune a local model to execute core routing/orchestration tasks without API overhead.

### Milestone 9: Hot-Swap Cortex with Canary Deployments
Complete cognitive self-modification safely.
- **9.1 Immutable Kernel Core**: Set strict kernel rules that are inaccessible to the modifying Cortex, enabling immediate rollback upon crash.
- **9.2 Canary Deployment Engine**: Test self-written orchestrator code by routing 10% of tasks to it first, verifying stability before promotion.

### Milestone 10: Multi-Agent Spawning with Write Quarantine
Unlock concurrent task solving.
- **10.1 Worker Spawning**: Launch specialized sub-agents for heavy research or coding runs.
- **10.2 Memory Write-Quarantine**: Isolate sub-agent long-term memories to sandboxed caches, requiring consensus or validation by the parent agent before integration into global LTM.

---

## Implementation & Impact Matrix

| Priority | System Change | Complexity | Strategic Leverage |
|---|---|---|---|
| **0** | Evaluation Harness & Deep Tracing | Medium | Critical; provides the mathematical feedback loop for all progress. |
| **1** | Context Engineering & Prompt Budgeting | Low | Immediate cost reduction and context quality preservation. |
| **2** | ModelRouter & Local Inference | Medium | Eliminates vendor lock-in, cuts API costs, improves speed. |
| **3** | Isolated Sandbox & Security Layer | High | Precondition for executing self-written scripts safely. |
| **4** | Dynamic Self-Authoring Tools | Medium | Expands GC7's absolute operational footprint autonomously. |
| **5** | Grounded Planning & Value Verification | High | Shifts GC7 from short-term reactive actions to deliberate lookahead. |
| **6** | Associative GraphRAG Upgrades | High | Transitions memory from unstructured clips to relational concepts. |
| **7** | Counterfactual Metacognitive Decay | Low | Removes subjective protocol accumulation; purges prompt waste. |
| **8** | Local Model Fine-Tuning Flywheel | High | Initiates true model-level performance growth. |
| **9** | Hot-Swap Cortex & Canary Deployments | Very High | True cognitive architecture self-modification. |
| **10**| Multi-Agent with Write Quarantine | Very High | Safe, concurrent performance scaling on complex projects. |
