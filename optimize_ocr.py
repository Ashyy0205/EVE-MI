import cv2
import time
import os
import json
import numpy as np
import pytesseract
from vision import VisionSystem

# Ensure output directory exists
output_dir = "ocr_optimization"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

def test_region(vision, region_name, region):
    print(f"\n{'='*60}")
    print(f" Testing Region: {region_name} {region}")
    print(f"{'='*60}")
    
    if not region or region[2] == 0 or region[3] == 0:
        print("Invalid region dimensions.")
        return

    img = vision.capture_screen(region)
    cv2.imwrite(f"{output_dir}/{region_name}_raw.png", img)
    
    # Scale up
    scale = 4
    width = int(img.shape[1] * scale)
    height = int(img.shape[0] * scale)
    # Use INTER_LINEAR to match production code for Overview/Selected Item
    img_scaled = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
    
    # Define methods (copied from vision.py to ensure parity)
    methods = []
    
    # Method 1: HSV
    hsv = cv2.cvtColor(img_scaled, cv2.COLOR_BGR2HSV)
    v_channel = hsv[:,:,2]
    _, thresh1 = cv2.threshold(v_channel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    methods.append(("HSV", thresh1))

    # Method 2: Gray
    gray = cv2.cvtColor(img_scaled, cv2.COLOR_BGR2GRAY)
    _, thresh2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    methods.append(("Gray", thresh2))

    # Method 3: Fixed
    _, thresh3 = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    methods.append(("Fixed", thresh3))

    # Method 4: Dilated
    kernel = np.ones((2,2), np.uint8)
    thresh4 = cv2.erode(thresh3, kernel, iterations=1)
    methods.append(("Dilated", thresh4))

    # Method 5: HighContrast
    _, thresh5 = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY_INV)
    methods.append(("HighContrast", thresh5))
    
    # Method 6: SuperHigh
    _, thresh6 = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    methods.append(("SuperHigh", thresh6))
    
    # Method 7: Adaptive
    thresh7 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    methods.append(("Adaptive", thresh7))
    
    # Method 8: Inverted
    _, thresh8 = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    methods.append(("Inverted", thresh8))

    # Method 9: Shadows (New)
    _, thresh9 = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
    methods.append(("Shadows", thresh9))

    print(f"{'Method':<15} | {'PSM':<3} | {'Text Found'}")
    print("-" * 60)

    for method_name, thresh in methods:
        # Save debug image
        cv2.imwrite(f"{output_dir}/{region_name}_{method_name}.png", thresh)
        
        # Add padding for OCR
        padding = 20
        pad_val = 0 if method_name == "Inverted" else 255
        thresh_padded = cv2.copyMakeBorder(thresh, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=pad_val)

        for psm in [6, 7]:
            config = f'--psm {psm}'
            try:
                text = pytesseract.image_to_string(thresh_padded, config=config).strip()
                # Clean up newlines for display
                display_text = text.replace('\n', ' \\n ')
                print(f"{method_name:<15} | {psm:<3} | '{display_text}'")
            except Exception as e:
                print(f"{method_name:<15} | {psm:<3} | Error: {e}")

def main():
    vision = VisionSystem()
    
    # Load config
    if os.path.exists('config.json'):
        with open('config.json', 'r') as f:
            config = json.load(f)
    else:
        print("config.json not found!")
        return
        
    print("Starting OCR Optimization Capture in 5 seconds...")
    print("Please switch to the EVE Online window and ensure the UI is visible.")
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    print("Capturing...")
    
    # Calculate fallback undock region if missing
    undock_region = config.get("undock_region")
    if not undock_region and config.get("overview_region"):
        ov = config.get("overview_region")
        # Fallback: Top right area above overview
        undock_region = (ov[0], 0, ov[2], 800)
        print(f"Using fallback undock region: {undock_region}")

    # Test specific regions of interest
    regions_to_test = [
        ("undock_region", undock_region),
        # ("selected_item_region", config.get("selected_item_region")),
        # ("overview_region", config.get("overview_region")),
        # ("warp_status_region", config.get("warp_status_region")),
        # ("inventory_window_region", config.get("inventory_window_region"))
    ]
    
    for name, region in regions_to_test:
        if region:
            test_region(vision, name, region)
        else:
            print(f"Skipping {name} (not defined in config)")
            
    print(f"\nDone! Check the '{output_dir}' folder for generated images.")

if __name__ == "__main__":
    main()