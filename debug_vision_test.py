import cv2
import json
import os
from vision import VisionSystem

def debug_vision():
    print("Loading config...")
    if not os.path.exists('config.json'):
        print("Config not found!")
        return

    with open('config.json', 'r') as f:
        config = json.load(f)

    vision = VisionSystem()
    
    # 0. Test Full Screen Capture
    print("Capturing Full Screen...")
    img_full = vision.capture_screen(None)
    cv2.imwrite('debug_fullscreen.png', img_full)
    print(f"Saved 'debug_fullscreen.png' ({img_full.shape[1]}x{img_full.shape[0]})")

    # 1. Test Overview Capture
    print("Capturing Overview Region...")
    ov_region = tuple(config['overview_region'])
    img = vision.capture_screen(ov_region)
    cv2.imwrite('debug_overview.png', img)
    print(f"Saved 'debug_overview.png' ({img.shape[1]}x{img.shape[0]})")
    
    # 2. Test Tooltip Capture (Simulated)
    # We can't force the tooltip to appear here, but we can check the region
    print("Capturing Tooltip Region...")
    tt_region = tuple(config['tooltip_region'])
    img_tt = vision.capture_screen(tt_region)
    cv2.imwrite('debug_tooltip.png', img_tt)
    print(f"Saved 'debug_tooltip.png' ({img_tt.shape[1]}x{img_tt.shape[0]})")

    print("\nCHECK THE IMAGES:")
    print("1. Open 'debug_overview.png'. Does it show the asteroid list?")
    print("2. Open 'debug_tooltip.png'. Is it black (expected if no tooltip) or garbage?")

if __name__ == "__main__":
    debug_vision()
