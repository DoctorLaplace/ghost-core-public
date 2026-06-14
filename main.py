import asyncio
import logging
import logging.handlers
import platform
import threading
import os
import sys
import json
import functools
import time
import ctypes
import uvicorn
import colorlog
from google import genai
from agent.kernel.model_client import UnifiedModelClient

import config

# Force console standard streams to UTF-8 on Windows to avoid charmap codec errors
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

# --- Kernel Imports (Immutable Core — always available) ---
from agent.kernel.memory import MemoryModule
from agent.kernel.goal_manager import GoalManager, STATUS_COMPLETED, STATUS_FAILED
from agent.kernel.orchestrator import Orchestrator
from agent.kernel.hotkey_manager import HotkeyManager
from agent.kernel.system_controls import wipe_all_databases
from agent.kernel.tracer import Tracer

# --- Cortex Imports (Mutable — agent-improvable) ---
from agent.cortex.metacognition import Metacognition
from agent.cortex.workspace_manager import WorkspaceManager
from agent.cortex.protocol_manager import ProtocolManager
from agent.cortex.action_executor import ActionExecutor

from server.main import app as fastapi_app, get_command, send_event

# --- 1. Advanced Logging Setup ---
def setup_logging():
    """Sets up a logger that outputs to console with colors and to a file."""
    logger = logging.getLogger('agent')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    if platform.system() != 'Windows':
        cformat = '%(log_color)s' + log_format
        console_formatter = colorlog.ColoredFormatter(cformat, log_colors={
            'DEBUG':    'cyan', 'INFO':     'green', 'WARNING':  'yellow',
            'ERROR':    'red', 'CRITICAL': 'red,bg_white',
        })
    else:
        console_formatter = logging.Formatter(log_format)
        
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    
    log_file = config.LOG_DIR / f"{config.AGENT_NAME.lower()}_main.log"
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# --- 2. Agent Class ---
class Agent:
    def __init__(self):
        logger.info(f"Initializing agent: {config.AGENT_NAME}...")
        # Initialize Unified Model Client (supporting both Gemini and Anthropic)
        client = UnifiedModelClient(
            gemini_api_key=config.GEMINI_API_KEY,
            anthropic_api_key=config.ANTHROPIC_API_KEY
        )
        
        # --- Kernel and Cortex Components ---
        self.memory = MemoryModule(gemini_client=client, model_name=config.LIGHT_DUTY_MODEL_NAME)
        self.goal_manager = GoalManager(gemini_client=client, model_name=config.LIGHT_DUTY_MODEL_NAME, on_update_callback=self.broadcast_state)
        
        self.action_executor = ActionExecutor()
        self.workspace_manager = WorkspaceManager()
        self.protocol_manager = ProtocolManager()
        
        self.orchestrator = Orchestrator(gemini_client=client, workspace_manager=self.workspace_manager)
        self.tracer = Tracer()
        self.current_trace_id = None
        
        # Context Builder: Cortex (advanced) with Kernel fallback (minimal)
        try:
            from agent.cortex.context_optimizer import ContextOptimizer
            self.context_builder = ContextOptimizer(
                self.memory, self.goal_manager, self.action_executor,
                self.workspace_manager, self.protocol_manager
            )
            logger.info("Cortex online. Advanced context optimization active.")
        except Exception as e:
            from agent.kernel.prompt_assembler import PromptAssembler
            self.context_builder = PromptAssembler(
                self.memory, self.goal_manager, self.action_executor,
                self.workspace_manager, self.protocol_manager
            )
            logger.warning(f"Cortex degraded ({e}). Kernel-level prompt assembly active.")
        
        # Initialize Metacognition
        self.metacognition = Metacognition(gemini_client=client, model_name=config.GEMINI_MODEL_NAME, protocol_manager=self.protocol_manager)
        self.reflection_counter = 0
        self.REFLECTION_INTERVAL = 10  # Reflect every 10 task completions
        
        self.is_running = True
        logger.info("Agent components initialized successfully (Kernel + Cortex).")



    async def broadcast_state(self):
        """Broadcasts current state variables to the C2 Dashboard UI."""
        await send_event("goal_update", self.goal_manager.goals)
        await send_event("workspace_update", self.workspace_manager.get_content())
        await send_event("memory_update", self.memory.get_short_term_memories())
        await send_event("ltm_update", self.memory.get_recent_long_term_memories(15))
        await send_event("tool_update", list(self.action_executor.tools.keys()))
        await send_event("config_update", {
            "model_name": config.GEMINI_MODEL_NAME,
            "router_enabled": getattr(config, "ROUTER_ENABLED", True)
        })

    async def run(self):
        """The main asynchronous loop for the agent."""
        logger.info("Agent is running. Waiting for commands from the Director UI...")
        await send_event("system", f"{config.AGENT_NAME} is online and awaiting commands.")
        await send_event("status_ping", "online")
        await self.broadcast_state()
        
        # Get the running loop for offloading blocking tasks
        loop = asyncio.get_running_loop()

        self.hotkey_manager = HotkeyManager(send_event, loop)

        current_task_id = None

        while self.is_running:
            try:
                # Check for a new command from the director.
                try:
                    director_command = await asyncio.wait_for(get_command(), timeout=1.0)
                    if director_command == "_ui_sync":
                         logger.info("UI Sync requested. Broadcasting current state.")
                         await self.broadcast_state()
                         continue
                    elif director_command == "_halt":
                         logger.info("Halt command received. Clearing all goals and tasks.")
                         self.goal_manager.clear_all_goals()
                         current_task_id = None
                         await send_event("system", "Agent execution halted. All active tasks cancelled.")
                         await send_event("status_ping", "online")
                         await self.broadcast_state()
                         continue

                         
                    # Check for structured JSON commands from the settings UI
                    if director_command.strip().startswith("{"):
                        try:
                            cmd_data = json.loads(director_command)
                            cmd_type = cmd_data.get("type")
                            if cmd_type == "change_model":
                                new_model = cmd_data.get("model")
                                if new_model:
                                    config.GEMINI_MODEL_NAME = new_model
                                    if hasattr(config, "MODEL_TIERS") and isinstance(config.MODEL_TIERS, dict):
                                        config.MODEL_TIERS["frontier"] = new_model
                                    self.metacognition.model_name = new_model
                                    logger.info(f"Model updated via UI settings: {new_model}")
                                    await send_event("system", f"Cognition Engine model updated to: {new_model}")
                                
                                if "routing_enabled" in cmd_data:
                                    routing_val = bool(cmd_data["routing_enabled"])
                                    config.ROUTER_ENABLED = routing_val
                                    logger.info(f"Model routing updated: {routing_val}")
                                    await send_event("system", f"Model routing is now {'ENABLED' if routing_val else 'DISABLED'}.")

                                new_persona = cmd_data.get("persona")
                                if new_persona:
                                    try:
                                        import shutil
                                        safe_persona = os.path.basename(new_persona)
                                        source_path = config.BASE_DIR / "agent" / "volition" / "personas" / safe_persona
                                        target_path = config.CORE_CONSTITUTION_FILE
                                        if source_path.exists():
                                            shutil.copy(source_path, target_path)
                                            if hasattr(self, 'context_builder') and hasattr(self.context_builder, '_load_constitution'):
                                                self.context_builder.constitution = self.context_builder._load_constitution()
                                            logger.info(f"Persona swapped to: {safe_persona}")
                                            persona_name = safe_persona.replace('.md', '').upper()
                                            await send_event("system", f"Cognition Persona updated to: {persona_name}")
                                        else:
                                            logger.error(f"Persona file not found: {source_path}")
                                    except Exception as e:
                                        logger.error(f"Failed to swap persona: {e}")

                                await self.broadcast_state()
                                continue
                            elif cmd_type == "ui_state":
                                is_hidden = cmd_data.get("is_hidden", False)
                                if hasattr(self, 'hotkey_manager'):
                                    self.hotkey_manager.is_hidden = is_hidden
                                logger.info(f"Synchronized hotkey manager is_hidden state to: {is_hidden}")
                                continue
                        except Exception as e:
                            logger.error(f"Failed to parse JSON command: {e}")
                         
                    # LOG THE DIRECTOR'S COMMAND TO MEMORY
                    self.memory.add_event({"source": "director", "task_id": None, "text": director_command})
                    self.goal_manager.set_new_goal(director_command, director_command)
                    current_task_id = None # Abort current task to start the new one
                    logger.info("New directive from Director received. Prioritizing new goal.")
                    await send_event("system", "New directive received. Prioritizing new goal.")
                    await self.broadcast_state()
                except asyncio.TimeoutError:
                    pass # No new command, continue with the current task

                if not current_task_id:
                    next_task = self.goal_manager.get_next_task()
                    if next_task:
                        current_task_id = next_task['id']
                        logger.info(f"New task accepted: '{next_task['description']}' (ID: {current_task_id})")
                        try:
                            self.current_trace_id = self.tracer.start_trace(current_task_id)
                        except Exception:
                            self.current_trace_id = None
                        await send_event("system", f"New task accepted: '{next_task['description']}'")
                        await self.broadcast_state()
                    else:
                        await asyncio.sleep(1)
                        continue

                current_task = self.goal_manager.get_task_by_id(current_task_id)
                if not current_task or current_task['status'] in [STATUS_COMPLETED, STATUS_FAILED]:
                    logger.info(f"Task {current_task_id} is complete or failed. Looking for a new task.")
                    current_task_id = None
                    continue

                task_description = current_task['description']
                prompt = self.context_builder.build_prompt(task_description)
                
                # --- ASYNC CHANGE: Offload Orchestrator blocking call ---
                await send_event("status_ping", "thinking")
                decision = await loop.run_in_executor(None, functools.partial(self.orchestrator.decide_next_action, prompt, task_description))

                if "error" in decision:
                    error_message = f"Orchestration error: {decision['error']}"
                    logger.error(error_message)
                    await send_event("error", error_message)
                    await send_event("status_ping", "error")
                    self.goal_manager.fail_task(current_task_id)
                    self.orchestrator.record_task_outcome(False)
                    try:
                        if self.current_trace_id:
                            self.tracer.end_trace(self.current_trace_id, "failure")
                    except Exception:
                        pass
                    self.current_trace_id = None
                    current_task_id = None
                    await self.broadcast_state()
                    continue
                
                thought = decision.get("thought", "No thought provided.")
                action = decision.get("action", {})
                
                await send_event("thought", thought)
                logger.info(f"Agent Thought: {thought}")

                tool_name = action.get("tool_name")
                args = action.get("args", {})
                
                await send_event("action", f"Using tool `{tool_name}` with parameters: `{args}`")
                logger.info(f"Action: Executing tool '{tool_name}' with args: {args}")

                if tool_name == "answer_director":
                    self.orchestrator.trace_tool_call(tool_name, args)
                    response = args.get("response", "Task is complete.")
                    self.orchestrator.trace_tool_result(tool_name, True, response)
                    
                    # --- FIX TASK REPETITION LOOP ---
                    # Only log completion if it actually succeeds.
                    # NEW: complete_task returns (bool, str)
                    is_complete, msg = self.goal_manager.complete_task(current_task_id)
                    
                    if is_complete:
                        await send_event("system", f"Task complete. Final response:\n{response}")
                        await send_event("status_ping", "online")
                        logger.info(f"Task '{current_task_id}' completed. Final response: {response}")
                        self.memory.add_event({"source": "agent", "task_id": current_task_id, "text": f"Completed task '{task_description}' with answer: {response}"})
                        self.orchestrator.record_task_outcome(True)
                        try:
                            if self.current_trace_id:
                                self.tracer.end_trace(self.current_trace_id, "success")
                        except Exception:
                            pass
                        self.current_trace_id = None
                        current_task_id = None # Success, ready for next task
                        await self.broadcast_state()
                        
                        # Trigger metacognitive reflection periodically
                        self.reflection_counter += 1
                        if self.reflection_counter >= self.REFLECTION_INTERVAL:
                            await self._perform_metacognitive_reflection()
                            self.reflection_counter = 0
                    else:
                        # Completion rejected (e.g., subtasks pending)
                        warning_msg = f"Task completion REJECTED. {msg}"
                        await send_event("error", warning_msg)
                        logger.warning(warning_msg)
                        self.memory.add_event({"source": "system", "task_id": current_task_id, "text": warning_msg})
                        self.orchestrator.record_task_outcome(False)
                        try:
                            if self.current_trace_id:
                                self.tracer.end_trace(self.current_trace_id, "failure")
                        except Exception:
                            pass
                        self.current_trace_id = None
                        await self.broadcast_state()
                        # We keep current_task_id so the agent retries properly (addressing subtasks).
                
                elif tool_name:
                    # --- ASYNC CHANGE: Offload Tool Executor blocking call ---
                    # Use functools.partial to pass kwargs correctly
                    self.orchestrator.trace_tool_call(tool_name, args)
                    tool_func = functools.partial(self.action_executor.execute_tool, tool_name, **args)
                    try:
                        result = await loop.run_in_executor(None, tool_func)
                        self.orchestrator.trace_tool_result(tool_name, True, result)
                    except Exception as e:
                        self.orchestrator.trace_tool_result(tool_name, False, e)
                        raise
                    
                    await send_event("system", f"Tool `{tool_name}` executed. Result:\n{result[:1000]}...")
                    logger.info(f"Tool Result: {result[:500]}...")
                    self.memory.add_event({"source": "tool_executor", "task_id": current_task_id, "text": f"Executed tool '{tool_name}' with args {args}. Result: {result}"})
                    
                    if tool_name == "decompose_task":
                        current_task_id = None # Drop the parent task so the agent picks up the subtasks
                        
                    await self.broadcast_state()
                
                else:
                    error_message = "Orchestrator failed to specify a valid tool_name."
                    logger.error(error_message)
                    await send_event("error", error_message)
                    await send_event("status_ping", "error")

            except asyncio.CancelledError:
                self.is_running = False
            except Exception as e:
                error_message = f"Critical error in main loop: {e}"
                logger.critical(error_message, exc_info=True)
                await send_event("error", "A critical error occurred. See logs.")
                await send_event("status_ping", "error")
                if current_task_id:
                     self.goal_manager.fail_task(current_task_id)
                     try:
                         if self.current_trace_id:
                             self.tracer.end_trace(self.current_trace_id, "failure")
                     except Exception:
                         pass
                     self.current_trace_id = None
                current_task_id = None
                await self.broadcast_state()
                await asyncio.sleep(5)

        self.shutdown()
        
    async def _perform_metacognitive_reflection(self):
        """Triggers the metacognition engine to analyze recent activity."""
        logger.info("🧠 Initiating metacognitive reflection...")
        await send_event("metacognition", "Initiating self-reflection cycle...")
        
        try:
            # Gather recent activity from STM
            recent_memories = self.memory.get_short_term_memories()
            if not recent_memories:
                logger.info("No recent memories to analyze.")
                return
            
            activity_log = "\n".join([f"- {mem.get('text', '')}" for mem in recent_memories[-20:]])
            
            # Formulate hypothesis and experiment
            # Offload this too as it calls LLM
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self.metacognition.analyze_and_propose_protocol, activity_log)
            
            if "status" in result and result["status"] == "protocol_added":
                protocol = result["protocol"]
                logger.info(f"✓ Active Metacognition: Added protocol '{protocol['protocol_name']}'")
                await send_event("metacognition", f"💡 New Protocol Added\n**{protocol['protocol_name']}**: {protocol['protocol_instruction']}")
            elif "error" in result:
                logger.warning(f"Metacognition failed: {result['error']}")
                await send_event("metacognition", f"⚠️ Reflection failed - {result['error']}")
            else:
                logger.info("Metacognition: No new protocol needed.")
                await send_event("metacognition", "No new protocol needed.")

        except Exception as e:
            logger.error(f"Error during metacognitive reflection: {e}", exc_info=True)
            await send_event("metacognition", "❌ Error during reflection")
        
    def shutdown(self):
        logger.info("Agent is shutting down...")
        if hasattr(self, 'hotkey_manager'):
            self.hotkey_manager.shutdown()
        self.memory.close_connections()
        logger.info("Agent shutdown complete.")

# --- 3. Refactored Application Lifecycle ---

# Create a single agent instance that will live for the duration of the application
agent = Agent()

@fastapi_app.on_event("startup")
async def startup_event():
    """
    This function is called by Uvicorn when the server starts.
    It creates the agent's main run loop as a background task.
    """
    logger.info("Application startup event triggered.")
    asyncio.create_task(agent.memory._process_assessment_queue()) # Start async memory assessment worker
    asyncio.create_task(agent.run())

@fastapi_app.on_event("shutdown")
def shutdown_event():
    """
    This function is called by Uvicorn when the server shuts down.
    It calls the agent's shutdown method for graceful cleanup.
    """
    logger.info("Application shutdown event triggered.")
    agent.shutdown()

# --- 4. Headless Server Logic ---

if __name__ == "__main__":
    # Force system terminal color support if needed
    os.system('color')
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--prompt":
        prompt_arg = " ".join(sys.argv[2:])
        logger.info(f"Running in single-prompt CLI mode for prompt: '{prompt_arg}'")
        
        async def run_single_prompt(prompt_text):
            # Start background memory assessment queue
            asyncio.create_task(agent.memory._process_assessment_queue())
            
            # Set target goal
            agent.goal_manager.clear_all_goals()
            agent.goal_manager.set_new_goal(prompt_text, prompt_text)
            
            loop = asyncio.get_running_loop()
            current_task_id = None
            
            # Run task loop until no more active goals/tasks
            while True:
                if not current_task_id:
                    next_task = agent.goal_manager.get_next_task()
                    if next_task:
                        current_task_id = next_task['id']
                        try:
                            agent.current_trace_id = agent.tracer.start_trace(current_task_id)
                        except Exception:
                            agent.current_trace_id = None
                    else:
                        break
                        
                current_task = agent.goal_manager.get_task_by_id(current_task_id)
                if not current_task or current_task['status'] in [STATUS_COMPLETED, STATUS_FAILED]:
                    current_task_id = None
                    continue
                    
                task_description = current_task['description']
                prompt = agent.context_builder.build_prompt(task_description)
                
                decision = await loop.run_in_executor(None, functools.partial(agent.orchestrator.decide_next_action, prompt, task_description))
                
                if "error" in decision:
                    agent.goal_manager.fail_task(current_task_id)
                    agent.orchestrator.record_task_outcome(False)
                    try:
                        if agent.current_trace_id:
                            agent.tracer.end_trace(agent.current_trace_id, "failure")
                    except Exception:
                        pass
                    agent.current_trace_id = None
                    current_task_id = None
                    continue
                    
                thought = decision.get("thought", "No thought provided.")
                action = decision.get("action", {})
                
                tool_name = action.get("tool_name")
                args = action.get("args", {})
                
                if tool_name == "answer_director":
                    agent.orchestrator.trace_tool_call(tool_name, args)
                    response = args.get("response", "Task is complete.")
                    agent.orchestrator.trace_tool_result(tool_name, True, response)
                    
                    is_complete, msg = agent.goal_manager.complete_task(current_task_id)
                    if is_complete:
                        agent.memory.add_event({"source": "agent", "task_id": current_task_id, "text": f"Completed task with answer: {response}"})
                        agent.orchestrator.record_task_outcome(True)
                        try:
                            if agent.current_trace_id:
                                agent.tracer.end_trace(agent.current_trace_id, "success")
                        except Exception:
                            pass
                        agent.current_trace_id = None
                        current_task_id = None
                    else:
                        try:
                            if agent.current_trace_id:
                                agent.tracer.end_trace(agent.current_trace_id, "failure")
                        except Exception:
                            pass
                        agent.current_trace_id = None
                        agent.goal_manager.fail_task(current_task_id)
                        agent.orchestrator.record_task_outcome(False)
                        current_task_id = None
                        
                elif tool_name:
                    agent.orchestrator.trace_tool_call(tool_name, args)
                    tool_func = functools.partial(agent.action_executor.execute_tool, tool_name, **args)
                    try:
                        result = await loop.run_in_executor(None, tool_func)
                        agent.orchestrator.trace_tool_result(tool_name, True, result)
                        agent.memory.add_event({"source": "tool_executor", "task_id": current_task_id, "text": f"Executed tool '{tool_name}' with args {args}. Result: {result}"})
                    except Exception as e:
                        agent.orchestrator.trace_tool_result(tool_name, False, e)
                        raise
                        
                    if tool_name == "decompose_task":
                        current_task_id = None
                else:
                    agent.goal_manager.fail_task(current_task_id)
                    current_task_id = None
                    
            agent.shutdown()
            
        asyncio.run(run_single_prompt(prompt_arg))
        sys.exit(0)
    else:
        logger.info("Starting headless FastAPI server for Ghost Core 7...")
        uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")