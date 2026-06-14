from agent.cortex.workspace_manager import WorkspaceManager

# Instantiate the manager once for this module
_workspace_manager = WorkspaceManager()

def read_workspace() -> str:
    """
    Reads the current content of the persistent workspace (scratchpad).
    Use this to recall your current state, hypothesis, or notes.
    """
    return _workspace_manager.get_content()

def overwrite_workspace(content: str) -> str:
    """
    Overwrites the ENTIRE workspace with new content.
    Use this to restructure your notes or clear old information.
    
    Args:
        content (str): The new content for the workspace.
    """
    return _workspace_manager.update_content(content)

def append_to_workspace(content: str) -> str:
    """
    Appends text to the end of the workspace.
    Use this to add a quick note or log a finding without deleting existing notes.
    
    Args:
        content (str): The content to append.
    """
    return _workspace_manager.append_content(content)
