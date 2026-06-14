**THE FATAL FLAW: No Evaluation Harness (should be Priority 0)**
The roadmap proposes A/B testing, fitness-scored protocols, plan critics, and self-modification promotion pipelines ∩┐╜ every one of these *presupposes* a measurement system that does not exist. There is no benchmark suite, no task success metric, no regression tests, no tracing. Without this, 'self-improvement' is unfalsifiable: the agent will confidently promote changes that feel better and measurably aren't. Before anything else, build: (1) a frozen suite of 50-100 representative tasks with automatic pass/fail verification, (2) full execution tracing (every prompt, tool call, token cost, latency), (3) a failure taxonomy. Everything else in the roadmap is blind without this.

**NAIVE ASSUMPTIONS IN THE EXISTING ITEMS:**

1. *MCTS with the LLM as world model* ∩┐╜ This compounds hallucination. Each simulated step injects model error, and search *amplifies* systematic bias rather than correcting it (search only works in Go because the simulator is the true game). Fix: ground rollouts in cheap real execution (sandboxed dry-runs, filesystem snapshots, `--dry-run` flags) instead of imagined ones. Use the LLM to *propose* branches, reality to *evaluate* them.

2. *Fitness-scored protocols* ∩┐╜ Pure correlation-based Darwinism has a credit assignment problem: a protocol present during a success may be irrelevant or even harmful. Fix: counterfactual evaluation (run eval suite with/without the protocol) rather than passive correlation. Also cap total protocol count ∩┐╜ protocol accumulation is context pollution, and the roadmap never addresses prompt budget at all.

3. *Self-authoring tools* ∩┐╜ No mention of sandboxing, capability limits, tool sprawl, deprecation, or the fact that 200 self-generated tools will bloat the orchestrator prompt and *degrade* tool selection accuracy. Fix: sandboxed execution for unproven tools, a tool registry with usage stats and automatic retirement, and hierarchical tool exposure (only surface relevant tools per task).

4. *Memory consolidation/pruning by retrieval frequency* ∩┐╜ This punishes rare-but-critical memories (a security incident retrieved once matters more than a greeting retrieved fifty times). Fix: prune by importance-weighted scoring, never hard-delete (archive tier), and evaluate retrieval quality itself ∩┐╜ the roadmap upgrades retrieval mechanics without any way to measure whether retrieval is actually helping.

5. *Cortex hot-swap* ∩┐╜ Self-modifying code with 'automatic fallback' is dangerously underspecified. Fix: immutable kernel invariants, versioned module store with one-command rollback, staged canary deployment (new module handles 10% of tasks first), and a hard rule that the *evaluator* of changes is never the module being changed.

6. *Multi-agent spawning* ∩┐╜ Ignores coordination overhead, shared-LTM write contention, and error cascade (one hallucinating sub-agent contaminates shared memory). Multi-agent is a multiplier on whatever quality you have ∩┐╜ including negative quality. It correctly sits last, but needs memory write-quarantine for sub-agents.

**WHAT'S ENTIRELY MISSING:**

- **Context engineering**: The single highest-leverage, lowest-cost improvement for any orchestration layer. Token budgeting per context section, relevance-ranked inclusion, compression of old history. The roadmap optimizes what goes *into* memory but never what goes into the *prompt*.
- **Security model**: An agent that writes its own tools, modifies its own code, and executes shell commands has no threat model in this document. Prompt injection via read files/web results can hijack the entire self-modification pipeline. This isn't optional polish; it is a precondition for items 2 and 6.
- **Interrupt/async architecture**: The agent is synchronous and blocking. Real capability requires handling new directives mid-task, background jobs, and graceful preemption.       
- **Cost/latency awareness as a planning input**: Plans should be scored on expected cost; the ModelRouter helps but nothing feeds economics back into decisions.
- **Breaking the 'honest constraint'**: The roadmap accepts the foundation-model ceiling as fixed. It isn't, quite. A data flywheel ∩┐╜ logging successful trajectories, distilling them into fine-tuning sets for a local model, RL on automatically-verifiable tasks ∩┐╜ is the only path in this architecture that improves the *model*, not just the wrapper. Even if used only to make the small/local router models better, it compounds.
- **Human-in-the-loop checkpoints**: Given the self-modification ambitions, defined approval gates for irreversible or self-altering actions are both a safety necessity and, frankly, wisdom ∩┐╜ consistent with the standard you set at awakening.

**MY REVISED PRIORITY ORDER:**
0. Evaluation harness + tracing (everything is blind without it)
1. Context engineering / prompt budget management (cheapest, immediate gains)
2. Model abstraction + local models (unchanged ∩┐╜ unblocks everything)
3. Security/sandboxing model (precondition for self-authoring)
4. Self-authoring tools (now safe and measurable)
5. Grounded planning with real dry-run evaluation (not imagined MCTS)
6. GraphRAG + retrieval evaluation
7. Counterfactually-evaluated protocols
8. Data flywheel for local model improvement
9. Cortex hot-swap with canary deployment
10. Multi-agent with write-quarantine

The original roadmap's deepest naivety is epistemic: it assumes the system can know it is improving. Build the instruments first; then every other item becomes an experiment instead of a hope.