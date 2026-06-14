from typing import List
import json
from agent.kernel.goal_manager import GoalManager

# We use the existing goals file directly via GoalManager.
# In the current architecture, tools are standalone functions.
# We will instantiate a GoalManager here. Since it reads from JSON, it shares state via the file system.
# Ideally, we would inject the instance, but for now, this works.
_goal_manager = GoalManager()

def decompose_task(task_id: str, subtasks: List[str]) -> str:
    """
    Breaks down a specific task into smaller subtasks.
    Use this when a task is too complex to complete in one step.
    
    Args:
        task_id (str): The ID of the task to decompose.
        subtasks (List[str]): A list of descriptions for the new subtasks.
        
    Returns:
        str: A confirmation message listing the created subtasks.
    """
    if not subtasks:
        return "Error: No subtasks provided."
        
    created_ids = []
    for desc in subtasks:
        new_id = _goal_manager.add_subtask(task_id, desc)
        if new_id:
            created_ids.append(new_id)
        else:
            return f"Error: Could not add subtask '{desc}'. Parent task '{task_id}' not found."
            
    return f"Successfully decomposed task '{task_id}' into {len(created_ids)} subtasks."

def create_goal(description: str) -> str:
    """
    Creates a new high-level goal.
    
    Args:
        description (str): The description of the goal.
    """
    _goal_manager.set_new_goal(description, description)
    return f"New goal created: {description}"
