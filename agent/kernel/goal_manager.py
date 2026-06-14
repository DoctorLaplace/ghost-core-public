import json
import logging
import os
import uuid
import asyncio
from typing import Dict, Any, Optional, List, Tuple

import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define states for goals and tasks
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

class GoalManager:
    """
    Manages the agent's long-term goals, including settting, decomposing, and tracking them.
    Supports hierarchical tasks (subtasks).
    """

    def __init__(self, gemini_client=None, model_name=None, on_update_callback=None):
        """
        Initializes the GoalManager.
        """
        self.goals_file = config.GOALS_FILE
        self.goals: Dict[str, Any] = {}
        self.client = gemini_client
        self.model_name = model_name
        self.on_update_callback = on_update_callback
        logger.info(f"GoalManager initialized. using file: '{self.goals_file}'.")

    def _load_goals(self) -> None:
        """Loads goals from the JSON file into self.goals."""
        try:
            if os.path.exists(self.goals_file):
                with open(self.goals_file, 'r', encoding='utf-8') as f:
                    self.goals = json.load(f)
            else:
                self.goals = {}
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading goals file: {e}. Starting with an empty goal set.")
            self.goals = {}

    def _save_goals(self) -> None:
        """Saves the current goals to the JSON file."""
        try:
            with open(self.goals_file, 'w', encoding='utf-8') as f:
                json.dump(self.goals, f, indent=4)
        except IOError as e:
            logger.error(f"Error saving goals file: {e}")

    def set_new_goal(self, description: str, director_request: str) -> Dict[str, Any]:
        """
        Sets a new high-level goal for the agent. Creates a single root task.
        """
        self._load_goals() # Refresh state
        goal_id = f"goal_{uuid.uuid4()}"
        task_id = f"task_{uuid.uuid4()}"
        
        # A task is now a recursive structure
        root_task = {
            "id": task_id,
            "description": description,
            "status": STATUS_PENDING,
            "parent_id": None,
            "subtasks": [],
            "retries": 3 # Default 3 retries
        }
        
        goal = {
            "id": goal_id,
            "title": "Generating title...",
            "description": description,
            "director_request": director_request,
            "status": STATUS_PENDING,
            "root_tasks": [root_task] # List of root tasks
        }
        
        self.goals[goal_id] = goal
        self._save_goals()
        logger.info(f"Set new goal '{goal_id}': {description}")
        
        # Dispatch async title generation if client exists
        if self.client:
            asyncio.create_task(self._generate_goal_title(goal_id, description))
            
        return goal

    async def _generate_goal_title(self, goal_id: str, description: str):
        """Asynchronously generates a concise title for a goal."""
        try:
            prompt = f"Provide a very concise title (maximum 5 words) for the following goal description. Respond ONLY with the title string, no quotes or prefix.\n\nDescription: {description}"
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    purpose="title_generation"
                )
            )
            
            title = response.text.strip().replace('"', '').replace("'", "")
            if len(title) > 0:
                self._load_goals()
                if goal_id in self.goals:
                    self.goals[goal_id]['title'] = title
                    self._save_goals()
                    logger.info(f"Generated title for goal {goal_id}: {title}")
                    
                    if self.on_update_callback:
                        if asyncio.iscoroutinefunction(self.on_update_callback):
                            await self.on_update_callback()
                        else:
                            self.on_update_callback()
                            
        except Exception as e:
            logger.error(f"Failed to generate goal title: {e}")
            self._load_goals()
            if goal_id in self.goals:
                self.goals[goal_id]['title'] = "New Goal"
                self._save_goals()
                if self.on_update_callback:
                    if asyncio.iscoroutinefunction(self.on_update_callback):
                        await self.on_update_callback()
                    else:
                        self.on_update_callback()

    def add_subtask(self, parent_task_id: str, description: str) -> Optional[str]:
        """
        Adds a subtask to a specific parent task.
        """
        self._load_goals() # Refresh state
        parent_task = self.get_task_by_id(parent_task_id, reload=False) # Already loaded
        if not parent_task:
            logger.error(f"Cannot add subtask: Parent task '{parent_task_id}' not found.")
            return None
            
        new_task_id = f"task_{uuid.uuid4()}"
        new_task = {
            "id": new_task_id,
            "description": description,
            "status": STATUS_PENDING,
            "parent_id": parent_task_id,
            "subtasks": [],
            "retries": 3 # Default 3 retries
        }
        
        parent_task['subtasks'].append(new_task)
        self._save_goals()
        logger.info(f"Added subtask '{description}' (ID: {new_task_id}) to parent '{parent_task_id}'.")
        return new_task_id

    def get_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Finds the next actionable task.
        Strategy: Depth-First Search. Find the first leaf node that is PENDING.
        """
        self._load_goals() # Refresh state
        for goal in self.goals.values():
            if goal['status'] in [STATUS_PENDING, STATUS_IN_PROGRESS]:
                for root_task in goal['root_tasks']:
                    next_task = self._find_next_pending_leaf(root_task)
                    if next_task:
                        # If we found a task, ensure the goal and path are marked in progress
                        if goal['status'] == STATUS_PENDING:
                            goal['status'] = STATUS_IN_PROGRESS
                        self._mark_path_in_progress(root_task, next_task['id'])
                        self._save_goals()
                        return next_task
        return None

    def _find_next_pending_leaf(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Recursive helper to find the next pending leaf task."""
        if task['status'] in [STATUS_COMPLETED, STATUS_FAILED]:
            return None
            
        # If it has subtasks, look into them
        if task['subtasks']:
            for subtask in task['subtasks']:
                found = self._find_next_pending_leaf(subtask)
                if found:
                    return found
            # If all subtasks are done but this task isn't marked done (shouldn't happen if logic is correct),
            # or if no subtasks are pending, we return None.
            return None
        else:
            # It's a leaf. If it's pending or in_progress, it's the one.
            if task['status'] == STATUS_PENDING:
                return task
            # If it's already in progress, we return it too (keep working on it)
            if task['status'] == STATUS_IN_PROGRESS:
                return task
            return None

    def _mark_path_in_progress(self, current_node: Dict[str, Any], target_id: str) -> bool:
        """Recursively marks the path to the target as in_progress."""
        if current_node['id'] == target_id:
            if current_node['status'] == STATUS_PENDING:
                current_node['status'] = STATUS_IN_PROGRESS
            return True
        
        for subtask in current_node['subtasks']:
            if self._mark_path_in_progress(subtask, target_id):
                if current_node['status'] == STATUS_PENDING:
                    current_node['status'] = STATUS_IN_PROGRESS
                return True
        return False

    def complete_task(self, task_id: str) -> Tuple[bool, str]:
        """
        Marks a task as completed. If it has a parent, checks if parent is complete.
        Returns: (success: bool, message: str)
        """
        self._load_goals() # Refresh state (entry point)
        success, msg = self._complete_task_internal(task_id)
        if success:
            self._save_goals() # Save once at the end
        return success, msg

    def _complete_task_internal(self, task_id: str) -> Tuple[bool, str]:
        """Internal recursive method to avoid redundant I/O."""
        task = self.get_task_by_id(task_id, reload=False) # Already loaded
        if not task:
            msg = f"Could not find task '{task_id}' to complete."
            logger.warning(msg)
            return False, msg

        # Check if there are any incomplete subtasks
        if task['subtasks']:
            incomplete_subtasks = [t for t in task['subtasks'] if t['status'] not in [STATUS_COMPLETED, STATUS_FAILED]]
            failed_subtasks = [t for t in task['subtasks'] if t['status'] == STATUS_FAILED]
            
            if incomplete_subtasks:
                msg = f"Cannot complete task '{task_id}': Subtasks {[t['id'] for t in incomplete_subtasks]} are not complete."
                logger.warning(msg)
                return False, msg
                
            if failed_subtasks:
                 # Should bubble fail instead of complete if children consistently failed
                 msg = f"Cannot complete task '{task_id}': Subtasks {[t['id'] for t in failed_subtasks]} failed."
                 logger.warning(msg)
                 return False, msg

        task['status'] = STATUS_COMPLETED
        logger.info(f"Task '{task_id}' completed.")
        
        # Check parent completion
        if task['parent_id']:
            parent = self.get_task_by_id(task['parent_id'], reload=False)
            if parent:
                # If all subtasks of the parent are complete, complete the parent
                if all(t['status'] == STATUS_COMPLETED for t in parent['subtasks']):
                    logger.info(f"All subtasks for '{parent['id']}' are done. Completing parent.")
                    self._complete_task_internal(parent['id']) 
                    return True, f"Task '{task_id}' and parent '{parent['id']}' completed."
        else:
            # It's a root task. Check if goal is complete.
            self._check_goal_completion()
            
        return True, f"Task '{task_id}' completed."

    def _check_goal_completion(self):
        """Checks if any goals are fully complete or failed."""
        for goal in self.goals.values():
            if goal['status'] not in [STATUS_COMPLETED, STATUS_FAILED]:
                if any(t['status'] == STATUS_FAILED for t in goal['root_tasks']):
                    goal['status'] = STATUS_FAILED
                    logger.info(f"Goal '{goal['id']}' failed.")
                elif all(t['status'] == STATUS_COMPLETED for t in goal['root_tasks']):
                    goal['status'] = STATUS_COMPLETED
                    logger.info(f"Goal '{goal['id']}' completed.")

    def get_task_by_id(self, task_id: str, reload: bool = True) -> Optional[Dict[str, Any]]:
        """Finds a task by ID searching all goals."""
        if reload:
            self._load_goals()
        for goal in self.goals.values():
            for root_task in goal['root_tasks']:
                found = self._find_task_recursive(root_task, task_id)
                if found:
                    return found
        return None

    def _find_task_recursive(self, current_task: Dict[str, Any], target_id: str) -> Optional[Dict[str, Any]]:
        if current_task['id'] == target_id:
            return current_task
        for subtask in current_task['subtasks']:
            found = self._find_task_recursive(subtask, target_id)
            if found:
                return found
        return None

    def fail_task(self, task_id: str) -> None:
        """Marks a task as failed, handling retries and bubbling up if necessary."""
        self._load_goals() # Refresh state initially
        self._fail_task_internal(task_id)
        self._save_goals() # Save state at the end

    def _cancel_subtasks(self, task: Dict[str, Any]) -> None:
        """Recursively marks subtasks as failed/canceled if parent fails."""
        for subtask in task.get('subtasks', []):
            if subtask['status'] in [STATUS_PENDING, STATUS_IN_PROGRESS]:
                subtask['status'] = STATUS_FAILED
                self._cancel_subtasks(subtask)

    def _fail_task_internal(self, task_id: str) -> None:
        task = self.get_task_by_id(task_id, reload=False)
        if not task:
            return
            
        if task.get('retries', 0) > 0:
            task['retries'] -= 1
            task['status'] = STATUS_PENDING
            logger.warning(f"Task '{task_id}' failed. Retrying... ({task['retries']} retries left)")
        else:
            task['status'] = STATUS_FAILED
            logger.error(f"Task '{task_id}' failed and out of retries. Bubbling failure.")
            
            # Cancel any orphaned subtasks
            self._cancel_subtasks(task)
            
            # Bubble up the failure to the parent
            if task['parent_id']:
                self._fail_task_internal(task['parent_id'])
            else:
                 # Check goal failure if root task fails
                 self._check_goal_completion()

    def get_goal_context_string(self) -> str:
        """
        Provides a recursive string summary of goals.
        """
        self._load_goals() # Refresh state
        active_goals = [g for g in self.goals.values() if g['status'] != STATUS_COMPLETED]
        if not active_goals:
            return "No active long-term goals are currently set."
        
        lines = ["--- Current Goals & Status ---"]
        for goal in active_goals:
            lines.append(f"Goal: {goal['description']} [{goal['status'].upper()}]")
            for root_task in goal['root_tasks']:
                lines.extend(self._format_task_tree(root_task, indent=2))
        
        return "\n".join(lines)

    def _format_task_tree(self, task: Dict[str, Any], indent: int) -> List[str]:
        """Recursive helper to format the task tree."""
        spaces = " " * indent
        retries_info = f", Retries left: {task.get('retries', 0)}" if task['status'] in [STATUS_PENDING, STATUS_IN_PROGRESS] else ""
        lines = [f"{spaces}- Task: {task['description']} (ID: {task['id']}) [{task['status'].upper()}{retries_info}]"]
        for subtask in task['subtasks']:
            lines.extend(self._format_task_tree(subtask, indent + 2))
        return lines

    def clear_all_goals(self) -> None:
        """Clears all goals and saves the empty state to goals.json."""
        self.goals = {}
        self._save_goals()
        logger.info("All goals cleared successfully.")
        if self.on_update_callback:
            if asyncio.iscoroutinefunction(self.on_update_callback):
                asyncio.create_task(self.on_update_callback())
            else:
                self.on_update_callback()