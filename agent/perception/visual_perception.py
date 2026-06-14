import os
import time
import logging
import ctypes
from ctypes import wintypes
import win32gui
import win32ui
import win32con
import win32api
from PIL import Image
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

import config

logger = logging.getLogger(__name__)

# --- VLM Setup (Lazy Loading) ---
_MODEL = None
_PROCESSOR = None
_MODEL_LOADED = False

def _ensure_model_loaded():
    """Lazily loads the Qwen2.5-VL model into VRAM only when first needed."""
    global _MODEL, _PROCESSOR, _MODEL_LOADED
    if _MODEL_LOADED:
        return
        
    logger.info("loading Qwen2.5-VL (3B) into VRAM (~5GB)...")
    try:
        model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
        
        # We load in bfloat16 to save memory (requires modern GPU, fallback to float16 if needed)
        _MODEL = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="auto"
        )
        # The default range for the number of visual tokens per image in the model is 256-1280
        min_pixels = 256 * 28 * 28
        max_pixels = 1280 * 28 * 28
        _PROCESSOR = AutoProcessor.from_pretrained(model_id, min_pixels=min_pixels, max_pixels=max_pixels)
        
        _MODEL_LOADED = True
        logger.info("Qwen2.5-VL loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load VLM: {e}")
        raise

# --- OmniParser Setup (Lazy Loading) ---
_VISION_ENGINE = None
def _ensure_omniparser_loaded():
    global _VISION_ENGINE
    if _VISION_ENGINE is None:
        from agent.perception.omniparser_vision import VisionEngine
        _VISION_ENGINE = VisionEngine()
    return _VISION_ENGINE

# --- Core Tools ---

def look_at_screen(region_left: int = None, region_top: int = None, region_width: int = None, region_height: int = None, monitor_index: int = 1, analyze_content: bool = True) -> str:
    """
    Uses the OmniParser Vision Engine to analyze the screen and return UI elements with exact GLOBAL click coordinates.
    CRITICAL MULTI-MONITOR USAGE: Do NOT guess which monitor an app is on. Always use `get_window_bounds(app_name)` first 
    to get the exact Left/Top/Width/Height of the target application, and pass those exact values into the region_* arguments here.
    This guarantees the vision model only searches the exact app window, ignoring monitor layouts entirely.
    
    If you want to click a coordinate returned by this tool, use `click_coordinate(x, y)`.
    
    Args:
        region_left: The X coordinate of the top-left corner of the region.
        region_top: The Y coordinate of the top-left corner of the region.
        region_width: The width of the region.
        region_height: The height of the region.
        monitor_index: Which monitor to capture. 1=Primary, 2=Secondary, etc. 0=All monitors combined. (Default 1).
        analyze_content: (EXTREMELY SLOW - USE SPARINGLY) If True, the engine will run a heavy VLM on *every single* 
                         bounding box to read its text (OCR) or describe the icon. This takes ~10-20 seconds. 
                         Only use this if you cannot infer the element from its location alone.
        
    Returns:
        JSON string containing the number of elements found, the path to the annotated "Set-of-Mark" image, 
        and the global coordinates of every detected element (and their semantic 'content' if analyze_content=True).
    """
    import json
    try:
        engine = _ensure_omniparser_loaded()
        
        region = None
        if all(v is not None for v in [region_left, region_top, region_width, region_height]):
            region = {
                'left': int(region_left),
                'top': int(region_top),
                'width': int(region_width),
                'height': int(region_height)
            }
            
        result = engine.analyze_ui(region=region, monitor_index=monitor_index, analyze_content=analyze_content)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to execute look_at_screen: {e}"})

def capture_window_background(window_title: str) -> str:
    """
    Takes a screenshot of a specific window, EVEN IF it is in the background or hidden behind other windows.
    Saves the image temporarily and returns the path.
    
    Args:
        window_title: The exact or partial name of the window to capture.
    """
    try:
        # Find the window
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

        # Get window dimensions
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        # Create device contexts and bitmap
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)

        # PrintWindow with PW_RENDERFULLCONTENT (flag 2)
        # This is the magic that forces hardware accelerated apps to render to our buffer
        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        
        if result != 1:
            # Cleanup
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            return f"Error: PrintWindow failed. Application might block background capture."

        # Convert to PIL Image
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1
        )
        
        # Save it
        cache_dir = config.DATA_DIR / "vision_cache"
        os.makedirs(cache_dir, exist_ok=True)
        save_path = cache_dir / f"temp_capture_{hwnd}.png"
        img.save(save_path)

        # Cleanup
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        return str(save_path)
        
    except Exception as e:
        return f"Error capturing background window: {e}"


def analyze_window_visually(window_title: str, query: str) -> str:
    """
    Uses the Vision-Language Model to 'look' at a window and answer questions about it.
    Does NOT return click coordinates. Use UI Automation tools for interaction.
    
    Args:
        window_title: The window to take a screenshot of.
        query: What you want to know about the image (e.g., 'What is the error message on the screen?').
    """
    try:
        # 1. Capture the window
        image_path = capture_window_background(window_title)
        if image_path.startswith("Error"):
            return image_path
            
        # 2. Ensure model is loaded
        _ensure_model_loaded()
        
        # 3. Prepare the VLM Prompt
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": f"file://{image_path}"},
                    {"type": "text", "text": query},
                ],
            }
        ]
        
        # 4. Process and Run
        text = _PROCESSOR.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = _PROCESSOR(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(_MODEL.device)

        # Inference
        generated_ids = _MODEL.generate(**inputs, max_new_tokens=256)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = _PROCESSOR.batch_decode(
            generated_ids_trimmed, skip_special_tokens=False, clean_up_tokenization_spaces=False
        )[0]
        
        return f"VLM Analysis of '{window_title}':\n{output_text}"

    except Exception as e:
        return f"Error running VLM vision analysis: {e}"

def analyze_image_visually(image_path: str, query: str) -> str:
    """
    Uses the Vision-Language Model to 'look' at an arbitrary image file and answer questions about it.
    
    Args:
        image_path: The absolute path to the image file.
        query: What you want to know about the image (e.g., 'What is in this picture?').
    """
    import os
    if not os.path.exists(image_path):
        return f"Error: File not found at {image_path}"
        
    try:
        # 1. Ensure model is loaded
        _ensure_model_loaded()
        
        # 2. Prepare the VLM Prompt
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": f"file://{image_path}"},
                    {"type": "text", "text": query},
                ],
            }
        ]
        
        # 3. Process and Run
        text = _PROCESSOR.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = _PROCESSOR(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(_MODEL.device)

        # Inference
        generated_ids = _MODEL.generate(**inputs, max_new_tokens=256)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = _PROCESSOR.batch_decode(
            generated_ids_trimmed, skip_special_tokens=False, clean_up_tokenization_spaces=False
        )[0]
        
        return f"VLM Analysis of image '{os.path.basename(image_path)}':\n{output_text}"

    except Exception as e:
        return f"Error running VLM vision analysis on image: {e}"
