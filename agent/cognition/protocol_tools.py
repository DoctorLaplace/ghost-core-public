from agent.cortex.protocol_manager import ProtocolManager

# Instantiate singleton manager
_protocol_manager = ProtocolManager()

def add_protocol(name: str, instruction: str) -> str:
    """
    Adds a new behavioral protocol or updates an existing one.
    Use this to enforce best practices or rules for yourself.
    
    Args:
        name (str): A short, descriptive name for the protocol (e.g., "Python Testing").
        instruction (str): The detailed instruction to follow (e.g., "Always run pytest after modifying .py files.").
    """
    _protocol_manager.add_protocol(name, instruction)
    return f"Protocol '{name}' successfully added."

def remove_protocol(name: str) -> str:
    """
    Removes an existing protocol.
    
    Args:
        name (str): The name of the protocol to remove.
    """
    if _protocol_manager.remove_protocol(name):
        return f"Protocol '{name}' successfully removed."
    return f"Error: Protocol '{name}' not found."

def list_protocols() -> str:
    """
    Lists all currently active protocols.
    """
    return _protocol_manager.get_protocols_formatted()
