import logging
import os
from pathlib import Path
import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WorkspaceManager:
    """
    Manages the persistent workspace file (scratchpad) for the agent.
    """

    def __init__(self):
        """
        Initializes the WorkspaceManager and ensures the workspace file exists.
        """
        self.workspace_file = config.WORKSPACE_FILE
        self._ensure_workspace_exists()
        logger.info(f"WorkspaceManager initialized. File: {self.workspace_file}")

    def _ensure_workspace_exists(self):
        """Creates the workspace file if it doesn't exist."""
        if not self.workspace_file.exists():
            try:
                with open(self.workspace_file, 'w', encoding='utf-8') as f:
                    f.write("# Persistent Workspace\n\nUse this file to store notes, hypotheses, and state across tasks.\n")
                logger.info("Created new workspace file.")
            except IOError as e:
                logger.error(f"Failed to create workspace file: {e}")

    def get_content(self) -> str:
        """Reads the current content of the workspace."""
        try:
            with open(self.workspace_file, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            logger.error(f"Error reading workspace file: {e}")
            return "Error: Could not read workspace file."

    def update_content(self, content: str) -> str:
        """Overwrites the workspace with new content."""
        try:
            with open(self.workspace_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info("Workspace updated.")
            return "Workspace updated successfully."
        except IOError as e:
            error_msg = f"Error updating workspace file: {e}"
            logger.error(error_msg)
            return error_msg

    def append_content(self, content: str) -> str:
        """Appends content to the end of the workspace."""
        try:
            with open(self.workspace_file, 'a', encoding='utf-8') as f:
                f.write("\n" + content)
            logger.info("Workspace appended.")
            return "Content appended to workspace successfully."
        except IOError as e:
            error_msg = f"Error appending to workspace file: {e}"
            logger.error(error_msg)
            return error_msg

# Example usage for direct testing:
if __name__ == '__main__':
    print("Running WorkspaceManager standalone test...")
    
    # Ensure config has the attribute for testing if run directly without full env
    if not hasattr(config, 'WORKSPACE_FILE'):
        config.WORKSPACE_FILE = Path("test_workspace.md")

    manager = WorkspaceManager()
    
    print(f"\nInitial Content:\n{manager.get_content()}")
    
    manager.update_content("# Test Workspace\nThis is a test.")
    print(f"\nUpdated Content:\n{manager.get_content()}")
    
    manager.append_content("\n- Appended line.")
    print(f"\nAppended Content:\n{manager.get_content()}")
    
    # Cleanup
    if config.WORKSPACE_FILE.name == "test_workspace.md" and config.WORKSPACE_FILE.exists():
        os.remove(config.WORKSPACE_FILE)
        
    print("\nStandalone test completed.")
