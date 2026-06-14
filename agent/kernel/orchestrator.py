from agent.kernel.tracer import Tracer, active_trace_storage

# In agent/components/orchestrator.py

import json
import logging
from typing import Dict, Any
import re
from google import genai
import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The API response schema has been reverted to dynamic JSON parsing 
# due to hallucination loops triggered by strict Pydantic models in google-generativeai 0.8.6.

class Orchestrator:
    """
    The central decision-making component of the agent. It uses the Gemini model
    to decide the next action based on a comprehensive prompt.
    """

    def __init__(self, gemini_client=None, workspace_manager=None):
        """
        Initializes the Orchestrator and configures the Gemini API client.
        """
        self.tracer = Tracer()
        self.workspace_manager = workspace_manager
        if gemini_client:
            self.client = gemini_client
        else:
            try:
                self.client = genai.Client(api_key=config.GEMINI_API_KEY)
            except Exception as e:
                logger.error(f"Failed to configure Gemini API client. Is GEMINI_API_KEY set correctly? Error: {e}")
                raise
        logger.info(f"Orchestrator initialized with google-genai Client.")

    def trace_tool_call(self, tool_name: str, args: dict):
        """Logs event_type='tool_call' with keys of arguments."""
        try:
            trace_id = getattr(active_trace_storage, "trace_id", None)
            if trace_id:
                self.tracer.log_event(trace_id, "tool_call", {
                    "tool": tool_name,
                    "args_keys": list(args.keys())
                })
        except Exception:
            pass

    def trace_tool_result(self, tool_name: str, success: bool, result: any):
        """Logs event_type='tool_result'."""
        try:
            trace_id = getattr(active_trace_storage, "trace_id", None)
            if trace_id:
                self.tracer.log_event(trace_id, "tool_result", {
                    "tool": tool_name,
                    "success": success,
                    "result_len": len(str(result))
                })
        except Exception:
            pass


    def _lenient_json_parse(self, text: str) -> Dict[str, Any]:
        """
        Extracts thought and action fields from a malformed JSON string
        using targeted key-boundaries partitioning when standard JSON parsing fails.
        """
        # Clean text to outer brackets
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            raise ValueError("No outer braces found")
        
        json_body = text[start_idx:end_idx+1]
        
        # Define keys to search for uniquely
        wrapper_keys = ["thought", "action", "tool_name", "args"]
        arg_keys = [
            "path", "content", "query", "response", "command", "description", 
            "director_request", "name", "instruction", "model", "persona",
            "task_id", "subtasks", "topic", "generalized_rule", "window_title",
            "element_name", "text", "x", "y", "action", "num_results", "timeout",
            "region_left", "region_top", "region_width", "region_height",
            "monitor_index", "analyze_content", "image_path", "include_hidden",
            "search_query", "conf_threshold"
        ]
        # Keep unique keys
        all_keys = list(dict.fromkeys(wrapper_keys + arg_keys))
        
        key_positions = []
        for key in all_keys:
            pattern = rf'"{key}"\s*:'
            for m in re.finditer(pattern, json_body):
                key_positions.append({
                    "key": key,
                    "start": m.start(),
                    "end": m.end()
                })
                
        key_positions.sort(key=lambda x: x["start"])
        
        def extract_string_value(raw_str: str) -> str:
            raw_str = raw_str.strip()
            if not raw_str.startswith('"'):
                return raw_str
                
            for idx in range(len(raw_str) - 1, 0, -1):
                if raw_str[idx] == '"':
                    trailing = raw_str[idx+1:]
                    if re.match(r'^[\s,\}\]]*$', trailing):
                        val = raw_str[1:idx]
                        return val
            
            # Fallback
            val = raw_str[1:]
            if val.endswith('"'):
                val = val[:-1]
            return val

        values = {}
        for i in range(len(key_positions)):
            kp = key_positions[i]
            key = kp["key"]
            start_val = kp["end"]
            
            end_val = len(json_body)
            if i + 1 < len(key_positions):
                end_val = key_positions[i+1]["start"]
                
            raw_val_str = json_body[start_val:end_val].strip()
            
            if key in ["action", "args"]:
                continue
                
            # Extract string value if it starts with quote, else parse normally
            if raw_val_str.startswith('"'):
                cleaned_val = extract_string_value(raw_val_str)
                cleaned_val = cleaned_val.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n')
                values[key] = cleaned_val
            elif raw_val_str.startswith('['):
                # Clean trailing list structural characters
                list_str = raw_val_str.rstrip(' \t\n\r,}]')
                if not list_str.endswith(']'):
                    list_str += ']'
                try:
                    values[key] = json.loads(list_str)
                except:
                    # regex fallback for list of strings
                    values[key] = re.findall(r'"(.*?)"', list_str)
            else:
                # literal / boolean / number
                lit_str = raw_val_str.rstrip(' \t\n\r,}]')
                if lit_str.lower() == "true":
                    values[key] = True
                elif lit_str.lower() == "false":
                    values[key] = False
                elif lit_str.lower() == "null":
                    values[key] = None
                else:
                    try:
                        if '.' in lit_str:
                            values[key] = float(lit_str)
                        else:
                            values[key] = int(lit_str)
                    except ValueError:
                        values[key] = lit_str

        thought = values.get("thought", "")
        tool_name = values.get("tool_name", "")
        
        args = {}
        for k, v in values.items():
            if k in arg_keys:
                args[k] = v
                
        return {
            "thought": thought,
            "action": {
                "tool_name": tool_name,
                "args": args
            }
        }


    def decide_next_action(self, prompt: str, task_description: str = "") -> Dict[str, Any]:
        """
        Sends a prompt to the Gemini model and parses the response to determine the next action.

        Args:
            prompt (str): The complete prompt assembled by the ContextBuilder.
            task_description (str): Description of the current task.

        Returns:
            Dict[str, Any]: A dictionary representing the parsed JSON response from the model,
                            or an error dictionary if the process fails.
        """
        # Planning / Grounding Hook
        if getattr(config, "PLANNER_ENABLED", False) and task_description:
            if not hasattr(self, "_active_task") or self._active_task != task_description:
                self._active_task = task_description
                try:
                    if getattr(config, "CANARY_ENABLED", False):
                        from agent.kernel.canary import should_use_canary, load_cortex_module
                        trace_id = getattr(active_trace_storage, "trace_id", "")
                        task_id = trace_id.split("_")[0] if "_" in trace_id else (trace_id or "default")
                        planner_mod = load_cortex_module("planner", should_use_canary(task_id))
                    else:
                        import agent.cortex.planner as planner_mod
                    
                    generate_plans = planner_mod.generate_plans
                    critique_and_select = planner_mod.critique_and_select
                    dry_run_step = planner_mod.dry_run_step
                    
                    # Define cheap helper for LLM calls
                    def llm_call(prompt_text, purpose):
                        return self.client.models.generate_content(
                            model=config.GEMINI_MODEL_NAME,
                            contents=prompt_text,
                            purpose=purpose
                        )
                    
                    logger.info("Planner: Generating candidate plans...")
                    plans = generate_plans(task_description, prompt, llm_call)
                    
                    # Log plan_generated trace event
                    try:
                        trace_id = getattr(active_trace_storage, "trace_id", None)
                        if trace_id:
                            self.tracer.log_event(trace_id, "plan_generated", {"count": len(plans)})
                    except Exception:
                        pass
                    
                    selected_plan = {}
                    if plans:
                        logger.info("Planner: Critiquing and selecting plan...")
                        selected_plan = critique_and_select(plans, llm_call)
                        
                        # Log plan_selected trace event
                        try:
                            trace_id = getattr(active_trace_storage, "trace_id", None)
                            if trace_id:
                                self.tracer.log_event(trace_id, "plan_selected", {
                                    "plan_id": selected_plan.get("plan_id"),
                                    "estimated_risk": selected_plan.get("estimated_risk")
                                })
                        except Exception:
                            pass
                            
                    if selected_plan and self.workspace_manager:
                        logger.info("Planner: Writing selected plan to workspace...")
                        plan_json_str = json.dumps(selected_plan, indent=2)
                        self.workspace_manager.append_content(f"\n# SELECTED PLAN\n{plan_json_str}\n")
                        
                    steps = selected_plan.get("steps", [])
                    if steps:
                        first_step = steps[0]
                        logger.info(f"Planner: Dry-running plan's first step: '{first_step}'")
                        dry_run_res = dry_run_step(first_step)
                        
                        # Log dry_run trace event
                        try:
                            trace_id = getattr(active_trace_storage, "trace_id", None)
                            if trace_id:
                                self.tracer.log_event(trace_id, "dry_run", {
                                    "grounded": dry_run_res.get("grounded", True),
                                    "reason": dry_run_res.get("reason", "")
                                })
                        except Exception:
                            pass
                            
                        if not dry_run_res.get("grounded", True):
                            logger.warning("Planner: First step not grounded! Regenerating plans exactly once...")
                            plans = generate_plans(task_description, prompt, llm_call)
                            if plans:
                                selected_plan = critique_and_select(plans, llm_call)
                                if selected_plan and self.workspace_manager:
                                    plan_json_str = json.dumps(selected_plan, indent=2)
                                    self.workspace_manager.append_content(f"\n# SELECTED PLAN (REGENERATED)\n{plan_json_str}\n")
                except Exception as e:
                    logger.error(f"Planner run crashed: {e}", exc_info=True)

        try:
            logger.info("Sending prompt to Gemini model for decision (using JSON mime-type)...")
            
            # Note: We specifically DO NOT use response_schema=OrchestratorDecision here. 
            # In google-generativeai 0.8.6 with gemini-3-flash-preview, strict Pydantic schema 
            # objects occasionally cause the API to hang deeply into an infinite hallucination loop.
            from google.genai import types
            response = self.client.models.generate_content(
                model=config.GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            logger.debug(f"Raw structured response from Gemini: {response.text}")

            try:
                # 1. First attempt: Direct JSON parsing
                decision = json.loads(response.text)
                logger.info(f"Successfully parsed raw JSON decision from Gemini. Action: {decision.get('action', {}).get('tool_name')}")
                return decision
            except json.JSONDecodeError:
                logger.warning("Failed direct JSON parse. Attempting markdown/regex extraction...")
                
                # 2. Second attempt: Markdown block extraction
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', response.text, re.DOTALL)
                if match:
                    try:
                        decision = json.loads(match.group(1))
                        logger.info(f"Successfully recovered JSON decision via Regex extraction. Action: {decision.get('action', {}).get('tool_name')}")
                        return decision
                    except json.JSONDecodeError:
                        pass
                
                # 3. Third attempt: Aggressive structural extraction
                # Looks for the outermost '{' and '}'
                logger.warning("Failed regex extraction. Attempting aggressive outer-bracket extraction...")
                start_idx = response.text.find('{')
                end_idx = response.text.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    try:
                        subset = response.text[start_idx:end_idx+1]
                        decision = json.loads(subset)
                        logger.info(f"Successfully recovered JSON decision via aggressive bracket extraction. Action: {decision.get('action', {}).get('tool_name')}")
                        return decision
                    except json.JSONDecodeError:
                        pass
                
                # 4. Fourth attempt: Lenient manual regex parsing for malformed string escaping
                logger.warning("Failed aggressive bracket extraction. Attempting lenient regex parsing for malformed JSON...")
                try:
                    decision = self._lenient_json_parse(response.text)
                    logger.info(f"Successfully recovered JSON decision via lenient regex parsing. Action: {decision.get('action', {}).get('tool_name')}")
                    return decision
                except Exception as ex:
                    logger.warning(f"Lenient regex parsing failed: {ex}")
                
                raise ValueError(f"All JSON extraction methods failed for response. It is likely severely malformed.")

        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to decode JSON from Model's response. Error: {e}. Response text: '{response.text}'"
            logger.error(error_msg)
            return {"error": error_msg, "raw_response": response.text}
        except Exception as e:
            error_msg = f"An unexpected error occurred while communicating with the Cognition Engine: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}

    def record_task_outcome(self, succeeded: bool) -> None:
        """
        Records the task outcome for every currently-active protocol.
        Guarded with try-except to never crash the orchestrator.
        """
        try:
            if getattr(config, "CANARY_ENABLED", False):
                from agent.kernel.canary import should_use_canary, load_cortex_module
                trace_id = getattr(active_trace_storage, "trace_id", "")
                task_id = trace_id.split("_")[0] if "_" in trace_id else (trace_id or "default")
                use_canary = should_use_canary(task_id)
                pf_mod = load_cortex_module("protocol_fitness", use_canary)
                pm_mod = load_cortex_module("protocol_manager", use_canary)
            else:
                import agent.cortex.protocol_fitness as pf_mod
                import agent.cortex.protocol_manager as pm_mod

            record_outcome = pf_mod.record_outcome
            ProtocolManager = pm_mod.ProtocolManager

            pm = ProtocolManager()
            protocols = pm.get_all_protocols()
            for name in protocols.keys():
                record_outcome(name, succeeded)
        except Exception as e:
            logger.error(f"Failed to record protocol outcomes: {e}")

# Example usage for direct testing:
# This test mocks the Model API call to avoid using a real API key during testing.
if __name__ == '__main__':
    print("Running Orchestrator standalone test...")

    # --- Mock Gemini Client and Response ---
    class MockGeminiClient:
        class MockModels:
            def generate_content(self, model, contents, config=None):
                class MockResponse:
                    def __init__(self, text):
                        self.text = text
                
                # Simulate a successful response
                if "test_success" in contents:
                    response_text = """
                    ```json
                    {
                        "thought": "This is a test thought for a successful execution.",
                        "action": {
                            "tool_name": "perform_search",
                            "args": {
                                "query": "What is a mock object?"
                            }
                        }
                    }
                    ```
                    """
                    return MockResponse(response_text)
                
                # Simulate a malformed JSON response
                elif "test_malformed" in contents:
                    response_text = """Here is your response:
                    {
                        "thought": "This is a malformed response.",
                        "action": {
                            "tool_name": "perform_search",
                            "args": {}
                        }
                    }
                    Hope it helps!
                    """
                    return MockResponse(response_text)
                
                else:
                     return MockResponse('{"error": "Unknown test condition"}')
        def __init__(self):
            self.models = self.MockModels()


    # --- Test Execution ---
    mock_client = MockGeminiClient()
    orchestrator = Orchestrator(gemini_client=mock_client)

    print("\n--- Testing a successful decision ---")
    success_prompt = "This is a prompt to test_success."
    decision1 = orchestrator.decide_next_action(success_prompt)
    print(f"Decision: {decision1}")
    assert "error" not in decision1
    assert decision1['action']['tool_name'] == 'perform_search'

    print("\n--- Testing a malformed decision ---")
    malformed_prompt = "This is a prompt to test_malformed."
    decision2 = orchestrator.decide_next_action(malformed_prompt)
    print(f"Decision: {decision2}")
    assert "error" not in decision2
    assert decision2['action']['tool_name'] == 'perform_search'

    print("\nStandalone test completed.")