# agent/kernel/model_router.py
import config

def classify_call(purpose: str) -> str:
    """
    Classifies the call purpose into a model tier.
    Returns "frontier" for orchestration, and "cheap" for other purposes.
    """
    # Mapping table for dict lookup
    purposes = {
        "orchestration": "frontier",
        "summarization": "cheap",
        "classification": "cheap",
        "title_generation": "cheap",
        "memory_scoring": "cheap",
        "embedding_text": "cheap"
    }
    return purposes.get(purpose, "cheap")

def resolve_model(purpose: str) -> str:
    """
    Resolves the model name to use based on the call purpose.
    If ROUTER_ENABLED is False, always returns the frontier model name.
    """
    # Sync config.MODEL_TIERS dict with dynamic configuration variables
    if hasattr(config, "MODEL_TIERS") and isinstance(config.MODEL_TIERS, dict):
        config.MODEL_TIERS["frontier"] = getattr(config, "GEMINI_MODEL_NAME", config.MODEL_TIERS.get("frontier"))
        config.MODEL_TIERS["cheap"] = getattr(config, "LIGHT_DUTY_MODEL_NAME", config.MODEL_TIERS.get("cheap"))

    # If router is disabled or purpose is not specified, fall back to frontier
    if not getattr(config, "ROUTER_ENABLED", True):
        return config.MODEL_TIERS["frontier"]
        
    tier = classify_call(purpose)
    return config.MODEL_TIERS.get(tier, config.MODEL_TIERS["frontier"])
