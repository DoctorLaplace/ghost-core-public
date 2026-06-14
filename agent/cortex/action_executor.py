# In agent/components/action_executor.py

import os
import importlib
import inspect
import logging
from typing import Dict, Any, Callable

import config
# --- 1. IMPORT THE NEW FILE SYSTEM TOOL MODULE ---
from agent.perception import ui_inspection, visual_perception
from agent.effectors import ui_control, terminal, file_system, web_search
from agent.cognition import workspace_tools, planning_tools, protocol_tools, knowledge_tools

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Discovers, lists, and executes available tools for the agent.
    """

    def __init__(self):
        """
        Initializes the ActionExecutor and discovers all available tools.
        """
        self.tools: Dict[str, Callable] = {}
        self.reload_tools()

    def reload_tools(self) -> None:
        """
        Reloads all pre-defined and dynamically generated tools. 
        Updates the self.tools dictionary.
        """
        logger.info("Reloading ActionExecutor tools...")
        self.tools = self._discover_tools()
        logger.info(f"ActionExecutor reloaded with {len(self.tools)} tools: {list(self.tools.keys())}")

    def _discover_tools(self) -> Dict[str, Callable]:
        """
        Scans the predefined and generated tools directories to find all callable tools.

        Returns:
            Dict[str, Callable]: A dictionary mapping tool names to their function objects.
        """
        discovered_tools = {}

        # --- 1. Load Pre-defined Tools ---
        # We explicitly import these for reliability
        # --- 2. ADD THE NEW MODULE TO THE LIST OF PREDEFINED TOOLS ---
        predefined_modules = [ui_inspection, visual_perception, ui_control, terminal, file_system, web_search, workspace_tools, planning_tools, protocol_tools, knowledge_tools]
        for module in predefined_modules:
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    discovered_tools[name] = func

        # --- 2. Load Generated Tools ---
        # We load these dynamically
        gen_tools_dir = config.GENERATED_TOOLS_DIR
        if os.path.exists(gen_tools_dir):
            for filename in os.listdir(gen_tools_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    module_name = filename[:-3]
                    try:
                        # Construct the full module path
                        full_module_path = f"agent.generated_tools.{module_name}"
                        module = importlib.import_module(full_module_path)
                        if hasattr(module, module_name):
                            func = getattr(module, module_name)
                            if inspect.isfunction(func):
                                if module_name in discovered_tools:
                                    logger.warning(f"Tool '{module_name}' from {module_name} conflicts with an existing tool. It will be overwritten.")
                                discovered_tools[module_name] = func
                            else:
                                logger.warning(f"Attribute '{module_name}' in {filename} is not a function.")
                        else:
                            logger.warning(f"Function '{module_name}' not found in {filename}.")
                    except Exception as e:
                        logger.error(f"Failed to load generated tool from {filename}: {e}")
                        try:
                            from agent.kernel.tracer import active_trace_storage, Tracer
                            trace_id = getattr(active_trace_storage, "trace_id", None)
                            if trace_id:
                                tracer_inst = Tracer()
                                tracer_inst.log_event(trace_id, "tool_load_failed", {
                                    "name": module_name,
                                    "error": str(e)
                                })
                        except Exception:
                            pass
                        
        return discovered_tools

    def get_available_tools_string(self) -> str:
        """
        Generates a formatted string describing all available tools, including their
        names, parameters, and docstrings. This is used to inform the AI model.

        Returns:
            str: A descriptive string of all tools.
        """
        if not self.tools:
            return "No tools are available."

        lines = ["--- Available Tools ---"]
        for name, func in self.tools.items():
            try:
                # Get signature to show parameters
                sig = inspect.signature(func)
                # Get docstring for description
                doc = inspect.getdoc(func) or "No description available."
                
                lines.append(f"Tool Name: {name}")
                lines.append(f"  Usage: {name}{sig}")
                lines.append(f"  Description: {doc.strip()}")
                lines.append("-" * 20)
            except Exception as e:
                logger.error(f"Could not generate description for tool '{name}': {e}")
                
        return "\n".join(lines)

    def execute_tool(self, tool_name: str, **kwargs: Any) -> str:
        """
        Executes a specified tool with the given arguments.

        Args:
            tool_name (str): The name of the tool to execute.
            **kwargs: The keyword arguments to pass to the tool's function.

        Returns:
            str: The result from the tool as a string, or an error message.
        """
        if tool_name not in self.tools:
            error_msg = f"Error: Tool '{tool_name}' not found. Please use one of the available tools."
            logger.error(error_msg)
            return error_msg
        
        tool_function = self.tools[tool_name]
        
        try:
            logger.info(f"Executing tool '{tool_name}' with args: {kwargs}")
            # The tool function is expected to return a string.
            result_str = str(tool_function(**kwargs))
            
            # --- POINTER SYSTEM ---
            # If the tool output is massive, we save it to disk and return a pointer instead of flooding STM.
            # We don't pointerize file read operations, letting ContextBuilder's TRUNCATE_OVERSIZED_STM_THRESHOLD handle huge files.
            is_read_tool = tool_name in ["read_file", "view_file"] or (tool_name == "execute_command" and "cat " in kwargs.get("command", ""))
            pointer_threshold_chars = (config.STM_MAX_TOKENS * 4) // 2 
            
            if len(result_str) > pointer_threshold_chars and not is_read_tool:
                try:
                    import uuid
                    log_dir = config.LOG_DIR / "oversized_outputs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    pointer_file = log_dir / f"output_pointer_{uuid.uuid4().hex[:8]}.txt"
                    with open(pointer_file, "w", encoding="utf-8") as f:
                        f.write(result_str)
                    return f"[POINTER SYSTEM]: The tool '{tool_name}' returned a massive output ({len(result_str) // 4} tokens). The full output was saved to {pointer_file}. You may use terminal commands (like 'cat {pointer_file} | head') or file reading tools to investigate it."
                except Exception as e:
                    logger.error(f"Failed to create pointer file: {e}")
                    
            return result_str
        except TypeError as e:
            error_msg = f"Error: Invalid arguments for tool '{tool_name}'. {e}. Please check the tool's usage."
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Error: An unexpected error occurred while executing tool '{tool_name}': {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running ActionExecutor standalone test...")
    
    executor = ActionExecutor()
    
    print("\n--- Testing Tool Discovery ---")
    tools_string = executor.get_available_tools_string()
    print(tools_string)
    
    print("\n--- Testing Successful Tool Execution (web_search) ---")
    search_result = executor.execute_tool("perform_search", query="Python programming language")
    print(f"Result (first 150 chars): {search_result[:150]}...")

    print("\n--- Testing Successful Tool Execution (terminal) ---")
    # Use a safe, universal command
    terminal_result = executor.execute_tool("execute_command", command="echo Hello World")
    print(f"Result: {terminal_result.strip()}")

    print("\n--- Testing Non-Existent Tool ---")
    error_result1 = executor.execute_tool("non_existent_tool", arg1="value")
    print(f"Result: {error_result1}")

    print("\n--- Testing Tool with Incorrect Arguments ---")
    error_result2 = executor.execute_tool("perform_search", wrong_arg="some value")
    print(f"Result: {error_result2}")
    
    print("\nStandalone test completed.")