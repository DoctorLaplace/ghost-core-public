import os
import logging
from google import genai
import config

logger = logging.getLogger(__name__)

import time
from agent.kernel.tracer import Tracer, active_trace_storage

tracer = Tracer()

class UnifiedResponse:
    """Wraps API responses to provide a uniform interface (.text attribute)."""
    def __init__(self, text: str):
        self.text = text

class UnifiedModelClient:
    """
    Unified client wrapper that routes model generation requests
    to either Gemini or Anthropic API depending on the active model name.
    """
    def __init__(self, gemini_api_key=None, anthropic_api_key=None):
        self.gemini_api_key = gemini_api_key or config.GEMINI_API_KEY
        self.anthropic_api_key = anthropic_api_key or config.ANTHROPIC_API_KEY
        self._gemini_client = None
        self._anthropic_client = None
        self.models = self.ModelsNamespace(self)

    @property
    def gemini_client(self):
        if self._gemini_client is None:
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not found or not set in configuration.")
            logger.info("Initializing google-genai Client...")
            self._gemini_client = genai.Client(api_key=self.gemini_api_key)
        return self._gemini_client

    @property
    def anthropic_client(self):
        if self._anthropic_client is None:
            # Check for API key presence
            if not self.anthropic_api_key or self.anthropic_api_key == "YOUR_ANTHROPIC_API_KEY_HERE":
                raise ValueError(
                    "ANTHROPIC_API_KEY not found or not set in .env file. "
                    "Please configure ANTHROPIC_API_KEY to use Claude models."
                )
            logger.info("Initializing anthropic Client...")
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    class ModelsNamespace:
        def __init__(self, outer):
            self.outer = outer

        def generate_content(self, model, contents, config=None, purpose: str = "orchestration"):
            """
            Drop-in replacement for gemini_client.models.generate_content.
            """
            from agent.kernel.model_router import resolve_model
            model = resolve_model(purpose)
            # Extract prompt content as string for logging
            if isinstance(contents, list):
                contents_str = ""
                for item in contents:
                    if isinstance(item, str):
                        contents_str += item
                    elif hasattr(item, "text"):
                        contents_str += item.text
                    else:
                        contents_str += str(item)
            else:
                contents_str = str(contents)

            prompt_len = len(contents_str)
            trace_id = getattr(active_trace_storage, "trace_id", None)
            print(f"DEBUG: trace_id in generate_content: {trace_id}")

            # Log request
            if trace_id:
                try:
                    tracer.log_event(trace_id, "llm_request", {
                        "prompt_len_chars": prompt_len,
                        "model": model,
                        "prompt": contents_str
                    })
                except Exception:
                    pass

            t0 = time.time()
            text_response = ""

            if model.startswith("claude-"):
                logger.info(f"Routing generation request to Anthropic for model: {model}")
                client = self.outer.anthropic_client

                try:
                    # Execute Anthropic API Call
                    message = client.messages.create(
                        model=model,
                        max_tokens=4000,
                        messages=[
                            {"role": "user", "content": contents_str}
                        ]
                    )
                    
                    # Inspect stop reason or empty content lists (typical for Refusals)
                    if hasattr(message, "stop_reason") and message.stop_reason == "refusal":
                        explanation = "Request refused by Anthropic safety policies."
                        if hasattr(message, "stop_details") and message.stop_details:
                            explanation = getattr(message.stop_details, "explanation", explanation)
                        text_response = f"{{\"error\": \"Anthropic refusal: {explanation}\"}}"
                    elif not message.content:
                        text_response = "{\"error\": \"Anthropic returned empty content or refusal.\"}"
                    else:
                        text_blocks = [block.text for block in message.content if hasattr(block, "text")]
                        text_response = "".join(text_blocks)
                    
                    response_obj = UnifiedResponse(text_response)
                except Exception as e:
                    logger.error(f"Anthropic generation call failed: {e}")
                    raise
            else:
                logger.debug(f"Routing generation request to Gemini for model: {model}")
                try:
                    gemini_resp = self.outer.gemini_client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config
                    )
                    text_response = gemini_resp.text
                    response_obj = gemini_resp
                except Exception as e:
                    logger.error(f"Gemini generation call failed: {e}")
                    raise

            t1 = time.time()
            latency = t1 - t0

            # Log response
            if trace_id:
                try:
                    tracer.log_event(trace_id, "llm_response", {
                        "model": model,
                        "latency_sec": latency,
                        "response_len_chars": len(str(text_response)),
                        "response": str(text_response)
                    })
                except Exception:
                    pass

            return response_obj

