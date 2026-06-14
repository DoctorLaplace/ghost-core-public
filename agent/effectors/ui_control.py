import uiautomation as auto
import time
import re
import logging
from ctypes import wintypes
import ctypes
import config

logger = logging.getLogger(__name__)

# --- Core Setup for Idle Detection ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD)
    ]

def get_idle_time() -> float:
    """Returns the time in seconds since the last user input (mouse/keyboard)."""
    lastInputInfo = LASTINPUTINFO()
    lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo)):
        millis = ctypes.windll.kernel32.GetTickCount() - lastInputInfo.dwTime
        return millis / 1000.0
    return 0.0

def _wait_for_idle(timeout_seconds: int = 15) -> bool:
    """Blocks until the user has been idle for the configured timeout. Returns False if gave up."""
    required_idle = getattr(config, 'USER_IDLE_TIMEOUT_SECONDS', 3)
    start_time = time.time()
    
    while True:
        current_idle = get_idle_time()
        if current_idle >= required_idle:
            return True
            
        if time.time() - start_time > timeout_seconds:
            return False
            
        time.sleep(0.5)


# --- Action Tools (Polite Focus) ---

def _polite_takeover_and_act(window_title: str, action_func) -> str:
    """Helper to handle the wait, switch, act, and switch back logic."""
    ctypes.windll.ole32.CoInitialize(None)
    if not getattr(config, 'ALLOW_FOCUS_TAKEOVER', False):
        return "Error: Focus takeover is disabled in config. I cannot interact with the UI."
        
    try:
         window = auto.WindowControl(searchDepth=1, RegexName=f".*{re.escape(window_title)}.*")
         if not window.Exists(0,0):
             return f"Window '{window_title}' not found."
             
         # 1. Wait for idle
         if not _wait_for_idle():
             return f"Action aborted: User is actively using the computer. Cannot intrude."
             
         # 2. Record current foreground
         hwnd_foreground = ctypes.windll.user32.GetForegroundWindow()
         
         # 3. Take Focus
         if window.NativeWindowHandle != hwnd_foreground:
             window.SetActive()
             time.sleep(0.1) # Small buffer for UI to paint
             
         # 4. Perform Action
         result = action_func(window)
         
         # 5. Restore Focus
         if hwnd_foreground and hwnd_foreground != window.NativeWindowHandle:
             ctypes.windll.user32.SetForegroundWindow(hwnd_foreground)
             
         return result
    except Exception as e:
         return f"Critical error during UI interaction: {e}"
    finally:
         ctypes.windll.ole32.CoUninitialize()

def click_ui_element(window_title: str, element_name: str) -> str:
    """
    Clicks a specific UI element (like a Button or Link) inside a window.
    This respects 'Polite Focus' and will wait for the user to be idle before acting.
    
    Args:
        window_title: The window containing the element.
        element_name: The exact name of the element to click.
    """
    def _do_click(window):
        element = window.Control(searchDepth=10, Name=element_name)
        if not element.Exists(0,0):
            return f"Element '{element_name}' not found."
            
        # Try programmatic invoke first (invisible)
        inv_pattern = element.GetPattern(auto.PatternId.InvokePattern)
        if inv_pattern:
            inv_pattern.Invoke()
            return f"Successfully invoked '{element_name}'."
            
        # Fallback to a synthetic click on the element's bounding box
        element.Click()
        return f"Successfully physically clicked '{element_name}'."
        
    return _polite_takeover_and_act(window_title, _do_click)

def type_ui_element(window_title: str, element_name: str, text: str) -> str:
    """
    Types text into a specific UI element (like an EditControl or TextBox).
    This respects 'Polite Focus' and will wait for the user to be idle before acting.
    
    Args:
        window_title: The window containing the text field.
        element_name: The exact name of the text field.
        text: The string to type.
    """
    def _do_type(window):
        element = window.Control(searchDepth=10, Name=element_name)
        if not element.Exists(0,0):
            return f"Element '{element_name}' not found."
            
        # Try programmatic value set first
        val_pattern = element.GetPattern(auto.PatternId.ValuePattern)
        if val_pattern:
            val_pattern.SetValue(text)
            return f"Successfully set value of '{element_name}' to '{text}' programmatically."
            
        # Fallback to focusing the element and typing
        element.SetFocus()
        auto.SendKeys(text)
        return f"Successfully typed into '{element_name}'."
        
    return _polite_takeover_and_act(window_title, _do_type)

def click_coordinate(x: int, y: int, action: str = 'left') -> str:
    """
    Moves the mouse to the exact global X/Y pixel coordinates on the desktop and performs a click.
    Use this to click elements found via visual perception tools (like look_at_screen).
    Ignores polite focus and forces a physical system click.
    
    Args:
        x: The global X coordinate to click.
        y: The global Y coordinate to click.
        action: The type of click ('left', 'right', 'double'). Defaults to 'left'.
    """
    import win32api
    import win32con
    try:
        x, y = int(x), int(y)
        win32api.SetCursorPos((x, y))
        time.sleep(0.1)
        
        if action == 'left':
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
        elif action == 'right':
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, x, y, 0, 0)
        elif action == 'double':
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
        else:
            return f"Error: Unknown click action '{action}'"
            
        return f"Successfully performed '{action}' click at coordinates ({x}, {y})."
    except Exception as e:
        return f"Error clicking coordinates: {e}"


