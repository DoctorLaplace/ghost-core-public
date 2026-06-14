"""
Kernel-Level Prompt Assembler (Minimal Fallback)

This is the bare-minimum prompt builder that lives in the Kernel.
It provides just enough context for the LLM to function if the Cortex
(ContextOptimizer) is unavailable due to corruption, rollback, or hot-swap.

No heuristics, no token budgeting, no optimization — just raw data assembly.
"""
import logging
import platform
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class PromptAssembler:
    """
    Minimal prompt assembler for Kernel-level operation.
    Implements the same interface as ContextOptimizer but with zero heuristics.
    """

    def __init__(self, memory_module, goal_manager, action_executor=None,
                 workspace_manager=None, protocol_manager=None):
        self.memory = memory_module
        self.goal_manager = goal_manager
        self.action_executor = action_executor
        self.workspace_manager = workspace_manager
        self.protocol_manager = protocol_manager
        logger.warning("PromptAssembler initialized — Kernel fallback mode active. "
                       "Advanced context optimization is OFFLINE.")

    def build_prompt(self, task_description: str = "") -> str:
        """
        Builds a structured prompt from available context, enforcing a hard token budget.
        """
        from agent.kernel.token_budget import fit_to_budget, estimate_tokens
        
        # Build raw contents for major blocks
        
        # 1. Constitution
        constitution_content = ""
        try:
            constitution_path = config.CORE_CONSTITUTION_FILE
            if constitution_path.exists():
                constitution_content = constitution_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to load constitution: {e}")

        # 2. Protocols
        protocols_content = ""
        if self.protocol_manager:
            try:
                protocols_content = self.protocol_manager.get_protocols_formatted() or ""
            except Exception:
                pass

        # 3. Workspace
        workspace_content = ""
        if self.workspace_manager:
            try:
                workspace_content = self.workspace_manager.get_content() or ""
            except Exception:
                pass

        # 4. Event Log (Short-Term Memory)
        stm_text = ""
        try:
            stm_events = list(self.memory.stm)
            if stm_events:
                stm_text = "\n".join([f"- {evt}" for evt in stm_events[-20:]])
        except Exception:
            pass

        # 5. Insights
        insights_content = ""
        try:
            if hasattr(self.memory, "get_strategic_insights") and task_description:
                insights = self.memory.get_strategic_insights(task_description)
                if insights:
                    insights_content = "\n".join([f"- {insight.get('text', str(insight))}" for insight in insights])
        except Exception:
            pass

        # 6. Episodic Memories
        episodic_content = ""
        try:
            if hasattr(self.memory, "get_episodic_memories") and task_description:
                episodic = self.memory.get_episodic_memories(task_description)
                if episodic:
                    episodic_content = "\n".join([f"- {ep.get('text', str(ep))}" for ep in episodic])
        except Exception:
            pass

        # Prepare sections list with priorities
        # priorities: constitution=1, current task=1, protocols=2, workspace=3, event log=4, insights=5, episodic=6
        sections_to_fit = [
            ("constitution", constitution_content, 1),
            ("current task", task_description, 1),
            ("protocols", protocols_content, 2),
            ("workspace", workspace_content, 3),
            ("event log", stm_text, 4),
            ("insights", insights_content, 5),
            ("episodic", episodic_content, 6)
        ]

        # Enforce budget
        fitted = fit_to_budget(sections_to_fit, 24000)

        # Log prompt_budget trace event
        total_tokens_est = sum(estimate_tokens(content) for _, content, _ in sections_to_fit)
        dropped_sections = [name for name, content, _ in sections_to_fit if content and name not in fitted]
        try:
            from agent.kernel.tracer import active_trace_storage, Tracer
            trace_id = getattr(active_trace_storage, "trace_id", None)
            if trace_id:
                tracer_inst = Tracer()
                tracer_inst.log_event(trace_id, "prompt_budget", {
                    "total_tokens_est": total_tokens_est,
                    "dropped_sections": dropped_sections
                })
        except Exception:
            pass

        # Assemble final prompt matching original sections structure
        sections = []

        # Constitution
        if "constitution" in fitted and fitted["constitution"]:
            sections.append(f"# CORE CONSTITUTION\n{fitted['constitution']}")

        # OS Context (Always included, unbudgeted)
        sections.append(f"# SYSTEM CONTEXT\nOS: {platform.system()} {platform.release()}")

        # Active Protocols
        if "protocols" in fitted and fitted["protocols"]:
            sections.append(f"# ACTIVE PROTOCOLS\n{fitted['protocols']}")

        # Goals (Always included, unbudgeted)
        try:
            goals_str = self.goal_manager.get_goals_string()
            if goals_str:
                sections.append(f"# CURRENT GOALS\n{goals_str}")
        except Exception:
            pass

        # Available Tools (Always included, unbudgeted)
        if self.action_executor:
            try:
                tools_str = self.action_executor.get_available_tools_string()
                if tools_str:
                    sections.append(f"# AVAILABLE TOOLS\n{tools_str}")
            except Exception:
                pass

        # Workspace
        if "workspace" in fitted and fitted["workspace"]:
            sections.append(f"# WORKSPACE\n{fitted['workspace']}")

        # Event Log
        if "event log" in fitted and fitted["event log"]:
            sections.append(f"# RECENT EVENTS (Short-Term Memory)\n{fitted['event log']}")

        # Insights
        if "insights" in fitted and fitted["insights"]:
            sections.append(f"# STRATEGIC INSIGHTS\n{fitted['insights']}")

        # Episodic
        if "episodic" in fitted and fitted["episodic"]:
            sections.append(f"# RELEVANT EPISODIC MEMORIES\n{fitted['episodic']}")

        # Current Task
        if "current task" in fitted and fitted["current task"]:
            sections.append(f"# CURRENT TASK\n{fitted['current task']}")

        # Response Format (Always included, unbudgeted)
        sections.append("""# RESPONSE FORMAT
You MUST respond with ONLY a valid JSON object:
{
    "thought": "Your reasoning about what to do next",
    "action": "tool_name",
    "args": {"arg1": "value1"}
}
If the task is complete, use action "answer_director" with args {"response": "your answer"}.
""")

        return "\n\n---\n\n".join(sections)

