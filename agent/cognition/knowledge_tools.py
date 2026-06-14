import logging
from agent.kernel.db.vector_db import VectorDB

# Initialize logger and global VectorDB instance for the tool module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_vector_db = VectorDB()

def derive_insight(topic: str, generalized_rule: str) -> str:
    """
    Synthesizes a permanent strategic insight from the current context and saves it to Long-Term Memory.
    Use this tool after solving a complex problem, encountering an error, or recognizing a workflow pattern.
    This creates a permanent rule that will automatically be retrieved whenever you face similar tasks in the future.
    
    Args:
        topic (str): A concise, 2-4 word classification for the insight (e.g., "Python Subprocess Errors" or "React State Anti-patterns").
        generalized_rule (str): The specific, universally applicable rule to remember. Explain the exact mechanism, why it failed, and how to do it correctly next time.
        
    Returns:
        str: Confirmation of insight preservation.
    """
    if not topic or not generalized_rule:
        return "Error: Both 'topic' and 'generalized_rule' must be provided."
        
    metadata = {
        "title": topic,
        "type": "strategic_insight",
        "source": "derive_insight_tool"
    }
    
    try:
        point_id = _vector_db.add_memory(generalized_rule, metadata=metadata)
        if point_id:
            logger.info(f"Derived new strategic insight: [{topic}] {generalized_rule}")
            return f"Successfully derived strategic insight under topic '{topic}'. The rule is now permanently etched into your cognitive architecture."
        else:
            return "Failed to derive insight: VectorDB insertion failed."
    except Exception as e:
        logger.error(f"Error in derive_insight tool: {e}")
        return f"Error deriving insight: {e}"
