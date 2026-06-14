import os
import cv2
import torch
import numpy as np
import mss
from pathlib import Path
from ultralytics import YOLO

# Configuration
GC6_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = GC6_ROOT / "models" / "icon_detect" / "model.pt"
CACHE_DIR = GC6_ROOT / "data" / "vision_cache"
MAX_CACHE_FILES = 10

class VisionEngine:
    """
    On-Demand OmniParser Vision Engine using Microsoft's YOLOv8 icon_detect weights.
    Maintains a zero-idle VRAM footprint by loading/unloading per method call.
    """
    
    def __init__(self):
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._ensure_cache_limit()

    def _ensure_cache_limit(self):
        """Maintains the LRU history of screenshots in the vision_cache."""
        files = sorted(
            CACHE_DIR.glob("capture_*.png"),
            key=os.path.getmtime
        )
        while len(files) >= MAX_CACHE_FILES * 2: # Clean up base AND marked images
            files[0].unlink() # Delete oldest
            files.pop(0)

    def _get_next_cache_index(self):
        """Gets the next rolling ID for the cache."""
        existing = [f for f in CACHE_DIR.glob("capture_*_base.png")]
        if not existing:
            return 1
        
        # Parse the highest number and increment
        indices = [int(f.stem.split('_')[1]) for f in existing]
        next_id = (max(indices) % MAX_CACHE_FILES) + 1
        return next_id

    def capture_screen(self, region=None, monitor_index=1):
        """
        Captures the screen or a specific region using MSS (very fast).
        Args:
            region: dict with {'left', 'top', 'width', 'height'}. Overrides monitor_index.
            monitor_index: int. 1=Primary, 2=Secondary, etc. 0=All monitors combined.
        Returns:
            numpy array of the image (BGR), and the actual physical offset
        """
        with mss.mss() as sct:
            if region:
                monitor = region
                offset_x, offset_y = region['left'], region['top']
            else:
                try:
                    monitor = sct.monitors[monitor_index]
                except IndexError:
                    print(f"Monitor {monitor_index} not found. Defaulting to primary.")
                    monitor = sct.monitors[1]
                offset_x, offset_y = monitor['left'], monitor['top']
            
            sct_img = sct.grab(monitor)
            # Convert to numpy array (BGRA to BGR for OpenCV/YOLO compatibility)
            img = np.array(sct_img)[:, :, :3] 
            
            context = {
                "capture_source": "Region" if region else f"Monitor_{monitor_index}",
                "resolution": f"{monitor['width']}x{monitor['height']}",
                "global_offset_x": offset_x,
                "global_offset_y": offset_y
            }
            return img, offset_x, offset_y, context

    def analyze_ui(self, region=None, monitor_index=1, conf_threshold=0.08, analyze_content=True):
        """
        Loads YOLO, parses the screen, draws Set-of-Mark boxes, and unloads.
        """
        if not MODEL_PATH.exists():
            return {"error": f"Model not found at {MODEL_PATH}. Run download script."}

        # 1. Capture Image
        img, offset_x, offset_y, context_info = self.capture_screen(region, monitor_index)
        
        # 2. Assign Cache IDs
        cache_id = self._get_next_cache_index()
        base_path = CACHE_DIR / f"capture_{cache_id:02d}_base.png"
        marked_path = CACHE_DIR / f"capture_{cache_id:02d}_marked.png"
        
        cv2.imwrite(str(base_path), img)

        # 3. Load Model into VRAM
        print("Loading OmniParser YOLO to VRAM...")
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = YOLO(str(MODEL_PATH))
        model.to(device)

        # 4. Inference
        # imgsz=640 is standard, YOLO will scale down automatically
        results = model.predict(source=img, conf=conf_threshold, device=device, verbose=False)
        
        element_data = {}
        annotated_img = img.copy()

        # 5. Process Boxes and Affine Transform
        # YOLO ultralytics automatically handles the affine coords back to the original image size!
        # We just need to add the monitor offset if a sub-region was captured.
        
        if len(results) > 0:
            boxes = results[0].boxes
            for i, box in enumerate(boxes):
                # Get raw box coords relative to the captured image
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                
                # Calculate True Global OS Coordinates
                global_center_x = int(((x1 + x2) / 2) + offset_x)
                global_center_y = int(((y1 + y2) / 2) + offset_y)
                
                element_id = i + 1
                element_info = {
                    "global_x": global_center_x,
                    "global_y": global_center_y,
                    "width": int(x2 - x1),
                    "height": int(y2 - y1),
                    "confidence": float(box.conf[0].cpu().numpy())
                }

                # 6. Optional Content Analysis (VLM / OCR)
                # If requested, crop the raw box from the original image and run analysis 
                # (We do this stringently: crop, save to temp, pass to VLM, delete temp to not overload context)
                if analyze_content:
                    try:
                        # Add a small padding for better VLM reading context
                        pad = 5
                        h, w, _ = img.shape
                        cx1, cy1 = max(0, int(x1) - pad), max(0, int(y1) - pad)
                        cx2, cy2 = min(w, int(x2) + pad), min(h, int(y2) + pad)
                        crop_img = img[cy1:cy2, cx1:cx2]
                        
                        temp_crop_path = CACHE_DIR / f"temp_crop_{element_id}.png"
                        cv2.imwrite(str(temp_crop_path), crop_img)
                        
                        # Use the existing VLM tool (lazy loaded to prevent circular import panic)
                        from agent.perception.visual_perception import analyze_image_visually
                        # A very constrained prompt to keep JSON output small
                        content = analyze_image_visually(
                            str(temp_crop_path), 
                            "Answer exactly in 1 sentence: What text or explicit icon is in this image?"
                        )
                        
                        if temp_crop_path.exists():
                            temp_crop_path.unlink()
                            
                        # Clean the VLM string output
                        if "VLM Analysis" in content:
                           content = content.split(":\n")[-1].strip()
                        element_info["content"] = content
                    except Exception as e:
                        element_info["content"] = f"Analysis Failed: {e}"

                element_data[element_id] = element_info

                # 7. Draw Set-of-Mark Bounding Box & Label
                # Draw Box
                cv2.rectangle(annotated_img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
                # Draw Label Background
                label = f"[{element_id}]"
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated_img, (int(x1), int(y1)-20), (int(x1)+w, int(y1)), (0, 0, 255), -1)
                # Draw Label Text
                cv2.putText(annotated_img, label, (int(x1), int(y1)-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Save Marked Image
        cv2.imwrite(str(marked_path), annotated_img)
        self._ensure_cache_limit()

        # 8. Aggressive VRAM Cleanup
        print("Unloading model and flushing VRAM...")
        del model
        if device == 'cuda':
            torch.cuda.empty_cache()

        return {
            "context": context_info,
            "marked_image_path": str(marked_path),
            "base_image_path": str(base_path),
            "elements_found": len(element_data),
            "elements": element_data
        }

if __name__ == "__main__":
    # Quick Test
    engine = VisionEngine()
    print("Testing Vision Engine...")
    result = engine.analyze_ui()
    print(f"Found {result['elements_found']} UI elements.")
    print(f"Saved marked image to: {result['marked_image_path']}")
