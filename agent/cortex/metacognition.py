import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

import config
from agent.cortex.protocol_manager import ProtocolManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Metacognition:
    """
    Manages the agent's self-reflection and self-improvement loop.
    Actively generates protocols to improve future performance.
    """

    def __init__(self, gemini_client=None, model_name=None, protocol_manager: ProtocolManager = None):
        """
        Initializes the Metacognition engine.

        Args:
            gemini_client: An initialized GenAI Client instance.
            model_name: Gemini model name to use for analysis.
            protocol_manager: Instance of ProtocolManager to save new protocols.
        """
        self.client = gemini_client
        self.model_name = model_name
        self.protocol_manager = protocol_manager
        logger.info("Metacognition engine initialized.")

    def analyze_and_propose_protocol(self, recent_activity_log: str) -> Dict[str, Any]:
        """
        Uses the Gemini model to analyze recent activity and formulate a
        new Protocol to improve performance.
        
        If a valid protocol is generated, it is AUTOMATICALLY SAVED.

        Args:
            recent_activity_log (str): A summary of the agent's recent actions and outcomes.

        Returns:
            Dict[str, Any]: The result of the analysis.
        """
        if not self.client:
            return {"error": "Gemini client not provided to Metacognition engine."}
        
        if not recent_activity_log.strip():
            return {"error": "Recent activity log is empty."}

        prompt = f"""
        You are the metacognition engine for an autonomous AI agent. Your task is to analyze the agent's recent activity to identify inefficiencies, errors, or bad habits.
        
        Based on this analysis, you must generate a **Protocol**—a permanent instruction that the agent will follow in the future to prevent this issue.

        **Recent Agent Activity:**
        ---
        {recent_activity_log}
        ---

        **Analysis Task:**
        1.  **Identify Issue:** Find a pattern of inefficiency, repetition, or error.
        2.  **Formulate Protocol:** Create a concise, actionable rule (Protocol) to fix it.
        
        **Output Format:**
        Provide your response as a single JSON object with the following keys:
        - "analysis": Brief explanation of the issue.
        - "protocol_name": Short name (e.g., "Check Requirements").
        - "protocol_instruction": The actual instruction (e.g., "Always check requirements.txt before installing packages.").
        
        If no significant issue is found, return an empty JSON object {{}}.
        """
        
        try:
            logger.info("Sending metacognition prompt to Gemini...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                purpose="summarization"
            )
            cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
            
            if not cleaned_response or cleaned_response == "{}":
                logger.info("Metacognition found no issues.")
                return {"status": "no_action"}

            data = json.loads(cleaned_response)
            
            if "protocol_name" in data and "protocol_instruction" in data:
                # Active Step: Save the protocol immediately
                if self.protocol_manager:
                    self.protocol_manager.add_protocol(data["protocol_name"], data["protocol_instruction"])
                    logger.info(f"Active Metacognition: Added protocol '{data['protocol_name']}'")
                    return {
                        "status": "protocol_added",
                        "protocol": data
                    }
                else:
                    return {"error": "ProtocolManager not available."}
            
            return {"status": "no_protocol_generated", "data": data}

        except Exception as e:
            logger.error(f"Failed to run metacognition: {e}", exc_info=True)
            return {"error": f"Metacognition error: {e}"}

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running Metacognition standalone test...")
    
    class MockGeminiClient:
        class MockModels:
            def generate_content(self, model, contents):
                print("\n--- PROMPT ---")
                print(contents[:200] + "...")
                return type('obj', (object,), {'text': '{"analysis": "Agent forgot to test.", "protocol_name": "Always Test", "protocol_instruction": "Run tests."}'})
        def __init__(self):
            self.models = self.MockModels()

    class MockProtocolManager:
        def add_protocol(self, name, instruction):
            print(f"Mock Manager: Added '{name}' -> '{instruction}'")

    mock_client = MockGeminiClient()
    meta = Metacognition(gemini_client=mock_client, model_name="mock-model", protocol_manager=MockProtocolManager())
    meta.analyze_and_propose_protocol("Log: Agent wrote code but didn't test.")