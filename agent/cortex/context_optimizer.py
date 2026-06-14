import logging
import platform
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any

import config
from agent.kernel.memory import MemoryModule
from agent.kernel.goal_manager import GoalManager
from agent.cortex.action_executor import ActionExecutor
from agent.cortex.workspace_manager import WorkspaceManager
from agent.cortex.protocol_manager import ProtocolManager
from agent.sensors.active_window import get_active_window_title

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Static Prompt Components ---
JSON_RESPONSE_FORMAT = """
Your goal is to decide the single next best action to take to make progress on the CURRENT TASK.
Analyze the situation, your goals, and available tools. Formulate a short "thought" process explaining your reasoning.
Then, provide your decision as a single, valid JSON object.

The JSON object must have two keys:
1.  `"thought"`: A brief string explaining your reasoning for the chosen action.
2.  `"action"`: An object containing the details of the action to be taken. This action object must have a `"tool_name"` key and an `"args"` key.
    - If you need to use a tool, set `"tool_name"` to the tool's name and `"args"` to a dictionary of its arguments.
    - If you have sufficient information to answer the director's request, use the tool `"answer_director"`. The `"args"` dictionary should contain a `"response"` key with your final answer.
    - If you believe the task is complete, use `"answer_director"` to state this.

Example of a valid JSON response:
```json
{
  "thought": "The director wants to know what the JWST is. My memories don't have this information, so I need to use the web_search tool to find out.",
  "action": {
    "tool_name": "perform_search",
    "args": {
      "query": "What is the James Webb Space Telescope?"
    }
  }
}
```

Now, provide your response for the current task. Your entire output must be only the JSON object.
"""

class ContextOptimizer:
    """
    Assembles a comprehensive prompt for the AI model by gathering context from all relevant modules.
    """

    def __init__(self, memory: MemoryModule, goal_manager: GoalManager, action_executor: ActionExecutor, workspace_manager: WorkspaceManager, protocol_manager: ProtocolManager):
        """
        Initializes the ContextOptimizer with references to other core components.

        Args:
            memory (MemoryModule): The agent's memory system.
            goal_manager (GoalManager): The agent's goal management system.
            action_executor (ActionExecutor): The agent's tool execution system.
            workspace_manager (WorkspaceManager): The agent's workspace manager.
            protocol_manager (ProtocolManager): The agent's protocol manager.
        """
        self.memory = memory
        self.goal_manager = goal_manager
        self.action_executor = action_executor
        self.workspace_manager = workspace_manager
        self.protocol_manager = protocol_manager
        self.constitution = self._load_constitution()
        self.archive_file = config.LOG_DIR / "stm_archive.log"
        self.max_archive_size_bytes = 5 * 1024 * 1024 # 5 MB max archive size
        logger.info("ContextOptimizer initialized.")

    def _load_constitution(self) -> str:
        """Loads the agent's core constitution from the file."""
        try:
            with open(config.CORE_CONSTITUTION_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Core constitution file not found at: {config.CORE_CONSTITUTION_FILE}")
            return "Error: Core constitution not found. Proceed with caution."
        except Exception as e:
            logger.error(f"Error loading core constitution: {e}")
            return f"Error loading core constitution: {e}"
    def build_prompt(self, task_description: str) -> str:
        logger.info(f"Building prompt for task: '{task_description}'")
        # Reload constitution dynamically to support hotswapping
        self.constitution = self._load_constitution()

        goal_context = self.goal_manager.get_goal_context_string()
        tools_context = self.action_executor.get_available_tools_string()
        os_info = f"Operating System: {platform.system()} ({platform.release()})"
        active_window = get_active_window_title()

        # --- NEW: Build a structured event log from STM ---
        event_log = []
        
        # Determine global length and which events to keep
        # Approximate 1 token = 4 chars
        MAX_GLOBAL_CHARS = config.STM_MAX_TOKENS * 4
        current_chars = 0
        events_to_keep = []
        events_to_drop = []

        # Iterate backwards (most recent first) to prioritize recent context
        for event in reversed(list(self.memory.stm)):
            source = event.get('source', 'UNKNOWN').upper()
            timestamp = event.get('timestamp_utc', '')
            text = event.get('text', '')
            
            # Apply TRUNCATE_OVERSIZED_STM_THRESHOLD per event
            max_event_chars = config.TRUNCATE_OVERSIZED_STM_THRESHOLD * 4
            if len(text) > max_event_chars:
                head = text[:max_event_chars // 2]
                tail = text[-max_event_chars // 2:]
                text = f"{head}\n... [LOG TRUNCATED - OVERSIZED THRESHOLD EXCEEDED] ...\n{tail}"
                
            formatted_event = f"[{timestamp}] [{source}] {text}"
            event_length = len(formatted_event)

            if current_chars + event_length <= MAX_GLOBAL_CHARS:
                events_to_keep.insert(0, formatted_event) # Insert at beginning to maintain chronological order
                current_chars += event_length
            elif len(events_to_keep) == 0:
                # Ensure the most recent event is never completely dropped; aggressively truncate to fit global STM
                aggressive_limit = MAX_GLOBAL_CHARS - 500
                head = formatted_event[:aggressive_limit // 2]
                tail = formatted_event[-aggressive_limit // 2:]
                aggressively_truncated = f"{head}\n... [AGGRESSIVELY TRUNCATED TO FIT GLOBAL STM LIMIT] ...\n{tail}"
                events_to_keep.insert(0, aggressively_truncated)
                current_chars += len(aggressively_truncated)
            else:
                events_to_drop.insert(0, event) # Keep full event dictionary for archiving

        # Archive dropped events
        if events_to_drop:
            self._archive_dropped_events(events_to_drop)

        # Do NOT modify self.memory.stm here to avoid race conditions with background assessment queue.
        # The deque handles rolling over automatically.

        event_log_str = "\n".join(events_to_keep) or "No recent events in the log."

        # --- Extract Dynamic Knowledge (Episodic & Strategic) ---
        episodic_count = getattr(config, 'LTM_RETRIEVAL_COUNT', 5)
        insight_count = getattr(config, 'DYNAMIC_INSIGHT_COUNT', 5)
        
        episodic_memories = self.memory.get_episodic_memories(task_description, num_results=episodic_count)
        strategic_insights = self.memory.get_strategic_insights(task_description, num_results=insight_count)
        
        episodic_str = "\n".join(f"- {mem}" for mem in episodic_memories) or "No relevant past events found."
        strategic_str = "\n".join(f"- {mem}" for mem in strategic_insights) or "No strategic insights available."

        # --- Active Protocols ---
        protocols_str = ""
        if self.protocol_manager:
            try:
                protocols_str = self.protocol_manager.get_protocols_formatted() or ""
            except Exception:
                pass

        # --- Enforce Token Budget ---
        from agent.kernel.token_budget import fit_to_budget, estimate_tokens
        
        sections_to_fit = [
            ("constitution", self.constitution, 1),
            ("current task", task_description, 1),
            ("protocols", protocols_str, 2),
            ("workspace", self.workspace_manager.get_content() or "", 3),
            ("event log", event_log_str, 4),
            ("insights", strategic_str, 5),
            ("episodic", episodic_str, 6)
        ]
        
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

        prompt = f"""# GHOST CORE 7 - CONTROL PANEL
You are {config.AGENT_NAME}, an autonomous AI agent.

# CORE CONSTITUTION
{fitted.get("constitution", "")}

# ACTIVE PROTOCOLS
These are your self-imposed rules and best practices. You MUST follow them.
{fitted.get("protocols", "")}

# EXECUTION ENVIRONMENT
- {os_info}
- [ACTIVE OS WINDOW]: {active_window}

# LONG-TERM GOALS
{goal_context}

# AVAILABLE TOOLS
{tools_context}

# PERSISTENT WORKSPACE (SCRATCHPAD)
This is your persistent workspace file. You MUST use it to store notes, hypotheses, and state across tasks.
If this is empty and you are starting a complex task, your first action should be to initialize it.
---
{fitted.get("workspace", "")}
---

# STRATEGIC INSIGHTS (Rules & Patterns)
These are contextually relevant strategic rules and patterns derived from your past experiences. You MUST obey these insights as they represent learned success patterns.
{fitted.get("insights", "")}

# EPISODIC KNOWLEDGE (Past Events)
These are records of discrete actions or events from the past that relate to your current task.
{fitted.get("episodic", "")}

# RECENT EVENT LOG (from Short-Term Memory)
This is a log of the most recent events, including user directives and your own actions. You can use the timestamps to answer questions about time.
NOTE: If you see '[LOG TRUNCATED - ACTION SUCCESSFUL]', it means the output was too long to display here, but the action completed successfully. DO NOT retry the action.
---
{fitted.get("event log", "")}
---

# CURRENT TASK
Based on all context above, your immediate task is: **{fitted.get("current task", "")}**

# INSTRUCTION
{JSON_RESPONSE_FORMAT}
"""
        return prompt

    def _archive_dropped_events(self, dropped_events: list):
        """Appends dropped events to a persistent archive file and manages its size."""
        try:
            os.makedirs(os.path.dirname(self.archive_file), exist_ok=True)
            
            # Check file size and truncate if necessary
            if os.path.exists(self.archive_file) and os.path.getsize(self.archive_file) > self.max_archive_size_bytes:
                # Read, trim oldest, write back
                with open(self.archive_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                # Keep only the last half of the file if it breached the limit
                lines = lines[len(lines)//2:]
                with open(self.archive_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
            
            # Append new dropped events
            with open(self.archive_file, 'a', encoding='utf-8') as f:
                for event in dropped_events:
                    # Write as JSON lines
                    timestamp = event.get('timestamp_utc', datetime.now(timezone.utc).isoformat())
                    event['archived_at'] = timestamp
                    f.write(json.dumps(event) + '\n')
                    
        except Exception as e:
            logger.error(f"Failed to archive dropped STM events: {e}")

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running ContextOptimizer standalone test...")

    # --- Mock Dependencies ---
    class MockMemory:
        def get_relevant_context(self, task):
            return {
                "short_term_memory": ["2023-01-01T12:00:00Z: Agent initialized.", "2023-01-01T12:01:00Z: Director asked 'What is Gemini?'"],
                "long_term_memory": ["Gemini is a family of multimodal models by Google.", "An API key is needed to use the Gemini API."]
            }
        def get_episodic_memories(self, _, num_results): return []
        def get_strategic_insights(self, _, num_results): return []
        @property
        def stm(self): return []
    
    class MockGoalManager:
        def get_goal_context_string(self):
            return "Goal: Answer the director's question [in_progress]\n  - Task: Find out what Gemini is [in_progress]"
            
    class MockActionExecutor:
        def get_available_tools_string(self):
            return """--- Available Tools ---\nTool Name: perform_search\n  Usage: perform_search(query: str)\n  Description: Performs a web search."""
            
    class MockWorkspaceManager:
        def get_content(self):
            return "# My Workspace\n- Current hypothesis: X\n- To-do: Y"

    class MockProtocolManager:
        def get_protocols_formatted(self):
            return "- **Test Protocol**: Always run tests."

    # --- Test Execution ---
    mock_memory = MockMemory()
    mock_gm = MockGoalManager()
    mock_ae = MockActionExecutor()
    mock_wm = MockWorkspaceManager()
    mock_pm = MockProtocolManager()
    
    context_builder = ContextOptimizer(memory=mock_memory, goal_manager=mock_gm, action_executor=mock_ae, workspace_manager=mock_wm, protocol_manager=mock_pm)
    
    # Mock constitution loading
    context_builder.constitution = "CONSTITUTION"
    
    final_prompt = context_builder.build_prompt("Find out what Google's Gemini model is.")
    
    print("\n--- GENERATED PROMPT ---")
    print(final_prompt)
    print("--- END OF PROMPT ---")
    
    print("\nStandalone test completed.")