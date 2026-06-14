import json
import logging
import os
from typing import Dict, List, Optional

import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProtocolManager:
    """
    Manages the agent's behavioral protocols.
    Protocols are persistent instructions that guide the agent's behavior.
    """

    def __init__(self):
        """
        Initializes the ProtocolManager and loads protocols from the JSON file.
        """
        self.protocols_file = config.PROTOCOLS_FILE
        self.protocols: Dict[str, str] = self._load_protocols()
        logger.info(f"ProtocolManager initialized. Loaded {len(self.protocols)} protocols.")

    def _load_protocols(self) -> Dict[str, str]:
        """Loads protocols from the JSON file."""
        try:
            if os.path.exists(self.protocols_file):
                with open(self.protocols_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading protocols file: {e}. Starting with empty protocols.")
        return {}

    def _save_protocols(self) -> None:
        """Saves the current protocols to the JSON file."""
        try:
            with open(self.protocols_file, 'w', encoding='utf-8') as f:
                json.dump(self.protocols, f, indent=4)
        except IOError as e:
            logger.error(f"Error saving protocols file: {e}")

    def add_protocol(self, name: str, instruction: str) -> None:
        """
        Adds or updates a protocol.
        
        Args:
            name (str): The name of the protocol (e.g., "Test Safety").
            instruction (str): The content of the protocol (e.g., "Always run tests before committing.").
        """
        self.protocols[name] = instruction
        self._save_protocols()
        logger.info(f"Protocol '{name}' added/updated.")

    def remove_protocol(self, name: str) -> bool:
        """
        Removes a protocol by name.
        
        Returns:
            bool: True if removed, False if not found.
        """
        if name in self.protocols:
            del self.protocols[name]
            self._save_protocols()
            logger.info(f"Protocol '{name}' removed.")
            return True
        logger.warning(f"Protocol '{name}' not found.")
        return False

    def purge_doomed(self) -> List[str]:
        """
        Purges low-scoring protocols from the active list, archiving them.
        """
        from agent.cortex.protocol_fitness import get_doomed_protocols
        doomed = get_doomed_protocols()
        purged = []
        if not doomed:
            return purged
            
        retired_file = config.DATA_DIR / "retired_protocols.md"
        try:
            with open(retired_file, "a", encoding="utf-8") as f:
                for name in doomed:
                    if name in self.protocols:
                        f.write(f"## Retired Protocol: {name}\n\n{self.protocols[name]}\n\n")
        except Exception as e:
            logger.error(f"Failed to write to retired protocols file: {e}")

        for name in doomed:
            if self.remove_protocol(name):
                purged.append(name)
        return purged

    def get_all_protocols(self) -> Dict[str, str]:
        """Returns all protocols."""
        return self.protocols

    def get_protocols_formatted(self) -> str:
        """Returns a formatted string of all protocols for the context."""
        ablation_name = os.environ.get("GC7_PROTOCOL_ABLATION")
        if not self.protocols:
            return "No active protocols."
        
        lines = []
        for name, instruction in self.protocols.items():
            if ablation_name and name == ablation_name:
                continue
            lines.append(f"- **{name}**: {instruction}")
        return "\n".join(lines) if lines else "No active protocols."
