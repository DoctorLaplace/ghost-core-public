import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger(__name__)

def get_active_window_title() -> str:
    """
    Uses the Windows API to get the title of the currently active (foreground) window.
    Returns the window title as a string, or 'Unknown Window' if unable to fetch.
    """
    try:
        # Get the handle to the foreground window
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return "Unknown Window"

        # Get the length of the window's title text
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return "No Title"

        # Create a buffer to hold the text
        buffer = ctypes.create_unicode_buffer(length + 1)
        
        # Copy the text into the buffer
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        
        return buffer.value
    except Exception as e:
        logger.error(f"Failed to get active window title: {e}")
        return "Unknown OS Context"

if __name__ == "__main__":
    import time
    print("Testing Active Window Sensor. Switch windows now. Polling for 5 seconds...")
    for _ in range(5):
        print(f"Active Window: {get_active_window_title()}")
        time.sleep(1)
