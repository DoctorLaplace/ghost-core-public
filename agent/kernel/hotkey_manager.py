import logging
import asyncio
import keyboard
import config

logger = logging.getLogger(__name__)

class HotkeyManager:
    """
    Manages global OS hotkeys and channels them into the application's async event loop.
    We run keyboard hooks which execute synchronously on a background thread.
    We must use `loop.call_soon_threadsafe` to bridge them into the main event loop.
    """
    def __init__(self, director_send_event_func, loop):
        self.send_event = director_send_event_func
        self.loop = loop
        self._setup_hotkeys()
        
    def _setup_hotkeys(self):
        try:
            keyboard.add_hotkey(config.OVERLAY_TOGGLE_HOTKEY, self._handle_overlay_toggle, suppress=False)
            logger.info(f"Registered global hotkey (Overlay Toggle): {config.OVERLAY_TOGGLE_HOTKEY}")
            
            keyboard.add_hotkey(config.FOCUS_MODE_HOTKEY, self._handle_focus_toggle, suppress=False)
            logger.info(f"Registered global hotkey (Focus Mode): {config.FOCUS_MODE_HOTKEY}")
        except Exception as e:
            logger.error(f"Failed to register global hotkeys: {e}. Ensure script has appropriate permissions.")
            
    def _handle_overlay_toggle(self):
        # Triggered by OS thread
        self.is_hidden = getattr(self, 'is_hidden', False)
        
        # We bounce instructions off stdout so the Node shell wrapper can adjust window frame hitboxes
        if self.is_hidden:
            print("[ELECTRON] SHOW", flush=True)
            self.is_hidden = False
        else:
            print("[ELECTRON] HIDE", flush=True)
            self.is_hidden = True
            
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.send_event("hotkey", "toggle_overlay"))
        )
        
    def _handle_focus_toggle(self):
        # Triggered by OS thread
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.send_event("hotkey", "toggle_focus"))
        )

    def shutdown(self):
        try:
            keyboard.unhook_all()
            logger.info("Un-hooked all OS hotkeys.")
        except Exception as e:
            pass
