# Ghost Core: Advanced Robustness and True Metacognition Framework

To transition Ghost Core from a heuristic-driven agent to a truly self-improving cognitive architecture—a framework that cannot break but allows infinite adaptive change—the architecture must abandon static text-based rules and adopt a persistent, evolutionary logic substrate. 

The current metacognitive implementation (appending static string protocols to a JSON file) is fragile. It lacks conflict resolution, efficacy tracking, and the ability to prune obsolete rules. True robustness requires a system that treats self-modification as a safe, evolutionary process.

## 1. Architectural Paradigm: The Immutable Kernel & Mutable Cortex
A self-modifying system without a solid anchor will inevitably corrupt its own execution loop. The architecture must be bifurcated:

*   **The Kernel (Immutable):** The foundational execution loop (`main.py`), memory indexing protocols, database connectivity, Core Constitution enforcement, and the automated rollback engine. The agent has read-only access to this layer.
*   **The Cortex (Mutable):** Action logic, dynamically generated tools, context-building heuristics, and active protocols. The agent has read-write access to this layer via controlled APIs.

## 2. The Mechanisms of True Metacognition

### 2.1. Quantitative Protocol Fitness and Darwinian Decay
Protocols must cease to be permanent mandates and become "active hypotheses" with measurable lifespans.
*   **Fitness Tracking:** Every active protocol maintains a continuous fitness score. When a protocol is injected into the context window, the outcome of the subsequent task (Success/Failure metric from the `GoalManager`) mathematically adjusts this score.
*   **Automated Pruning:** Protocols whose fitness scores drop below a critical threshold—or protocols that correlate with high error rates or hallucination loops—are automatically decayed and purged from the system. This prevents contradictory rules from stacking and paralyzing the orchestrator.

### 2.2. The Simulation Matrix (Sandboxed "Dream State")
Metacognitive proposals (new protocols or generated python tools) cannot be deployed directly to the live environment without immense risk. They must survive simulation.
*   **Virtual Execution:** The system maintains a localized, mocked environment (the "Dream State").
*   **Trace Replay:** When Metacognition proposes a new rule to solve a recent failure, the agent isolates the exact STM state of that failure and replays it within the sandbox using the new rule.
*   **Verification:** If the sandbox execution errors out, loops infinitely, or violates the Constitution, the proposed rule is instantly discarded. If it demonstrably bypasses the previous failure point, it is promoted to the live Cortex.

### 2.3. Safe Self-Modification API (The Ouroboros Protocol)
To achieve true self-improvement, the agent must be capable of rewriting its own Python logic files in the Mutable Cortex.
*   **Shadow Deployments:** The agent uses an `edit_cortex_code` tool to write diffs. These changes are saved to a parallel "Shadow Directory", not the active execution path.
*   **Continuous Integration Gatekeeper:** The Kernel automatically spawns a secondary, isolated Python process to run a rigorous suite of unit and integration tests against the Shadow Directory.
*   **Automated Rollback (The Failsafe):** If the tests pass, the Kernel hot-swaps the code into the live directory. If the agent subsequently crashes or enters a fatal loop within the next *N* execution cycles, the Kernel triggers an immediate, hard rollback to the last known stable snapshot.

### 2.4. Epistemic Confidence Auditing (The "Critic" Model)
Current models suffer from confident hallucinations. True metacognition requires a real-time assessment of epistemic uncertainty.
*   **Dual-Process Watchdog:** A secondary, highly specific "Critic" model runs in parallel to the Orchestrator. Its sole purpose is to analyze the Orchestrator's `thought` outputs for circular reasoning, illogical leaps, or excessive confidence in unverified data.
*   **Epistemic Intercept:** If the Critic flags a thought cascade, it intercepts the `ActionExecutor` call. It forces the Orchestrator into an "Epistemic Reset", clearing the corrupted immediate STM and compelling the agent to use a verification tool (e.g., `web_search`, `query_window_element`) before proceeding.
