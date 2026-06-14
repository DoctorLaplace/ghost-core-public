import uiautomation as auto
import logging
from ctypes import wintypes
import ctypes
import config
import re

logger = logging.getLogger(__name__)

def list_open_windows(include_hidden: bool = False) -> str:
    """
    Returns a list of all currently open top-level application windows.
    Use this to see what applications are running before trying to interact with them.
    
    Args:
        include_hidden: If True, includes background/hidden windows (usually system processes). defaults to False.
    """
    ctypes.windll.ole32.CoInitialize(None)
    try:
        root = auto.GetRootControl()
        windows = []
        for child in root.GetChildren():
            # Only get standard windows by default
            if child.ControlType == auto.ControlType.WindowControl:
                name = child.Name
                # Filter out empty or common invisible shells if not include_hidden
                if not include_hidden and (not name or name == "Program Manager"):
                    continue
                windows.append(name)
                
        if not windows:
            return "No open windows found."
            
        return "Open Windows:\n- " + "\n- ".join(windows)
    except Exception as e:
        return f"Error listing windows: {e}"
    finally:
        ctypes.windll.ole32.CoUninitialize()

def inspect_window_ui(window_title: str) -> str:
    """
    Returns a filtered UI tree of actionable elements inside a specific window.
    This provides the 'element_name' you need for clicking or typing.
    It strips out layout panels and only shows Menus, Buttons, TextBoxes, Links, etc.
    
    Args:
        window_title: The name of the window (as seen in list_open_windows)
    """
    ctypes.windll.ole32.CoInitialize(None)
    try:
        window = auto.WindowControl(searchDepth=1, Name=window_title)
        if not window.Exists(0, 0):
            # Try a partial match if exact fails
            window = auto.WindowControl(searchDepth=1, RegexName=f".*{re.escape(window_title)}.*")
            if not window.Exists(0,0):
                return f"Window containing '{window_title}' not found."

        # Actionable control types ہم care about
        actionable_types = [
            auto.ControlType.ButtonControl,
            auto.ControlType.DocumentControl,
            auto.ControlType.EditControl,
            auto.ControlType.HyperlinkControl,
            auto.ControlType.MenuItemControl,
            auto.ControlType.TabItemControl,
            auto.ControlType.ComboBoxControl
        ]

        MAX_CHILDREN = 200 # Token limit safeguard
        found_elements = []
        
        # Traverse the tree
        for control, depth in auto.WalkControl(window):
            if control.ControlType in actionable_types:
                name = control.Name or "[Unnamed]"
                ctrl_type = control.ControlTypeName
                found_elements.append(f"{'  ' * (depth-1)}- [{ctrl_type}] {name}")
                
            if len(found_elements) > MAX_CHILDREN:
                found_elements.append("\n... [WARNING: MAX ELEMENTS REACHED. UI IS TOO COMPLEX. Use query_window_element for specifics.]")
                break

        if not found_elements:
            return f"No standard actionable UI elements found in '{window_title}'. The app might use a custom renderer (like a game or Electron app)."

        return f"--- UI Tree for '{window.Name}' ---\n" + "\n".join(found_elements)
        
    except Exception as e:
        return f"Error inspecting window: {e}"
    finally:
        ctypes.windll.ole32.CoUninitialize()

def search_window_ui(window_title: str, search_query: str) -> str:
    """
    Internally searches the entire UI tree of a window for elements matching a text query,
    bypassing context window limits.
    
    Args:
        window_title: The name of the window to search in.
        search_query: Text or regex pattern to search for in element names or values.
    """
    ctypes.windll.ole32.CoInitialize(None)
    try:
        window = auto.WindowControl(searchDepth=1, Name=window_title)
        if not window.Exists(0, 0):
            window = auto.WindowControl(searchDepth=1, RegexName=f".*{re.escape(window_title)}.*")
            if not window.Exists(0,0):
                return f"Window containing '{window_title}' not found."

        # Actionable control types ہم care about
        actionable_types = [
            auto.ControlType.ButtonControl,
            auto.ControlType.DocumentControl,
            auto.ControlType.EditControl,
            auto.ControlType.HyperlinkControl,
            auto.ControlType.MenuItemControl,
            auto.ControlType.TabItemControl,
            auto.ControlType.ComboBoxControl,
            auto.ControlType.TextControl,
            auto.ControlType.WindowControl # Sometimes dialog boxes are actionable
        ]

        found_elements = []
        search_lower = search_query.lower()
        
        # Traverse the tree internally without limiting to a small number
        for control, depth in auto.WalkControl(window):
            if control.ControlType in actionable_types:
                name = control.Name or ""
                
                # Check for match in Name, ClassName, or AutomationId
                match = False
                if search_lower in name.lower():
                    match = True
                elif control.AutomationId and search_lower in control.AutomationId.lower():
                     match = True
                elif control.ClassName and search_lower in control.ClassName.lower():
                     match = True
                     
                if match:
                    ctrl_type = control.ControlTypeName
                    
                    # Try to get the bounding rectangle so we know exactly where it is natively
                    rect_str = "Unknown Bounds"
                    try:
                        rect = control.BoundingRectangle
                        if rect:
                             rect_str = f"Bounds: (L:{rect.left}, T:{rect.top}, R:{rect.right}, B:{rect.bottom})"
                    except:
                        pass
                        
                    found_elements.append(f"[{ctrl_type}] Name: '{name}' | ID: '{control.AutomationId}' | {rect_str}")
                    
                    # Prevent catastrophic dumps if query is too broad, but give it a larger limit
                    if len(found_elements) >= 30:
                        found_elements.append("\n... [WARNING: Over 30 matches found. Please refine your search_query.]")
                        break

        if not found_elements:
            return f"No elements matching '{search_query}' found in '{window_title}' after searching the entire tree."

        return f"--- Search Results for '{search_query}' in '{window.Name}' ---\n" + "\n".join(found_elements)
        
    except Exception as e:
        return f"Error searching window UI: {e}"
    finally:
        ctypes.windll.ole32.CoUninitialize()

def query_window_element(window_title: str, element_name: str) -> str:
    """
    Returns detailed properties of a specific element inside a window without loading the whole tree.
    Use this if inspect_window_ui hit its limit, or if you need to know if an element is enabled/toggled.
    
    Args:
        window_title: The parent window name.
        element_name: The exact name of the button/textbox you are looking for.
    """
    ctypes.windll.ole32.CoInitialize(None)
    try:
        window = auto.WindowControl(searchDepth=1, RegexName=f".*{re.escape(window_title)}.*")
        if not window.Exists(0,0):
             return f"Window '{window_title}' not found."
             
        element = window.Control(searchDepth=10, Name=element_name)
        if not element.Exists(0,0):
            return f"Element '{element_name}' not found inside '{window.Name}'."
            
        # Gather details
        details = [
            f"Name: {element.Name}",
            f"ControlType: {element.ControlTypeName}",
            f"AutomationId: {element.AutomationId}",
            f"ClassName: {element.ClassName}",
            f"IsOffscreen: {element.IsOffscreen}"
        ]
        
        # Check patterns for value or toggle state
        val_pattern = element.GetPattern(auto.PatternId.ValuePattern)
        if val_pattern:
            details.append(f"Current Value: {val_pattern.Value}")
            
        tog_pattern = element.GetPattern(auto.PatternId.TogglePattern)
        if tog_pattern:
            state = tog_pattern.ToggleState
            state_str = "Checked" if state == 1 else ("Unchecked" if state == 0 else "Indeterminate")
            details.append(f"Toggle State: {state_str}")

        return "\n".join(details)
    except Exception as e:
         return f"Error querying element: {e}"
    finally:
         ctypes.windll.ole32.CoUninitialize()

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

def get_window_bounds(window_title: str) -> str:
    """
    Returns the exact physical desktop bounding box (Left, Top, Width, Height) of a target window.
    Feed these coordinates into look_at_screen(region_...) to take targeted screenshots of an app
    across multi-monitor setups, preventing monitor-confusion.
    
    Args:
        window_title: The explicit or partial name of the window.
    """
    import win32gui
    import json
    try:
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            # Fallback to partial match
            def enum_cb(h, hwnds):
                if win32gui.IsWindowVisible(h) and window_title.lower() in win32gui.GetWindowText(h).lower():
                    hwnds.append(h)
            hwnds = []
            win32gui.EnumWindows(enum_cb, hwnds)
            if hwnds:
                hwnd = hwnds[0]
            else:
                 return f"Error: Window containing '{window_title}' not found."
                 
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top
        
        return json.dumps({
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": width,
            "height": height
        }, indent=2)
    except Exception as e:
        return f"Error getting window bounds: {e}"
