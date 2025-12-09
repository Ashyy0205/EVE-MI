import cv2
import numpy as np
import pytesseract
import mss
import logging
import re
import difflib
import os
import sys

# Determine if we are running in a bundle (PyInstaller)
if getattr(sys, 'frozen', False):
    # If frozen, look for Tesseract in the same folder as the executable
    base_path = os.path.dirname(sys.executable)
    local_tesseract = os.path.join(base_path, 'Tesseract-OCR', 'tesseract.exe')
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
    local_tesseract = os.path.join(base_path, 'Tesseract-OCR', 'tesseract.exe')

# Set the path to tesseract executable
if os.path.exists(local_tesseract):
    pytesseract.pytesseract.tesseract_cmd = local_tesseract
else:
    # Fallback to default system install
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class VisionSystem:
    def __init__(self):
        print("[DIAG] VisionSystem.__init__ called")
        self.logger = logging.getLogger("BotLogger")
        # MSS is not thread-safe if shared across threads. 
        # We will initialize it inside capture_screen or use a thread-local storage if needed.
        # For simplicity, let's create a new instance for each capture or ensure single-threaded access.
        # However, creating it every time is slow.
        # The error suggests we are accessing it from a different thread than where it was created.
        self.sct = None
        print("[DIAG] VisionSystem.__init__ finished")

    def cleanup(self):
        if self.sct is not None:
            try:
                if hasattr(self.sct, 'close'):
                    self.sct.close()
            except Exception:
                pass
            self.sct = None

    def capture_screen(self, region=None):
        """
        Captures the screen or a specific region using MSS.
        region: tuple (x, y, width, height) or None for full screen
        Returns: numpy array (OpenCV image)
        """
        # Initialize MSS on the thread that uses it
        if self.sct is None:
            self.sct = mss.mss()

        if region:
            x, y, w, h = map(int, region)
            monitor = {"top": y, "left": x, "width": w, "height": h}
            screenshot = self.sct.grab(monitor)
        else:
            # Capture all monitors
            # monitor index 0 is the "All in One" virtual monitor
            screenshot = self.sct.grab(self.sct.monitors[0])
        
        # Convert MSS image to OpenCV format (BGRA -> BGR)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def has_selected_target(self, region, target_name=None):
        """
        Checks if the 'Selected Item' region has any text indicating a target.
        If target_name is provided, it verifies that the specific target is selected.
        Returns True if target is found/valid, False otherwise.
        """
        img = self.capture_screen(region)
        
        # Scale up - 4x for maximum detail
        # Use INTER_LINEAR for better text clarity on small UI fonts (Cubic can cause artifacts)
        scale = 4
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)

        methods = []

        # Method 1: HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:,:,2]
        _, thresh1 = cv2.threshold(v_channel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("HSV", thresh1))

        # Method 2: Gray
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("Gray", thresh2))

        # Method 3: Fixed Threshold
        _, thresh3 = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        methods.append(("Fixed", thresh3))

        # Method 4: Dilated
        kernel = np.ones((2,2), np.uint8)
        thresh4 = cv2.erode(thresh3, kernel, iterations=1)
        methods.append(("Dilated", thresh4))

        # Method 5: Adaptive Threshold (Great for text with shadows on varying backgrounds)
        thresh_adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        methods.append(("Adaptive", thresh_adapt))

        # Method 6: Shadow Detection (Look for dark pixels/shadows of text)
        # Text is white with black shadow. If background is bright, white text blends in, but shadow remains dark.
        # Invert: Dark pixels (shadows) become White (foreground).
        _, thresh_shadow = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
        methods.append(("Shadows", thresh_shadow))

        # Method 7: High Contrast (For bright backgrounds)
        # Threshold high to separate very bright text from bright-ish background
        _, thresh_high = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        methods.append(("HighContrast", thresh_high))

        for method_name, thresh in methods:
            # Use psm 6 (block of text) or 7 (single line)
            text = pytesseract.image_to_string(thresh, config='--psm 6').strip()
            text_lower = text.lower()
            
            # 1. Check for explicit "No Object" / "No Target"
            # If this appears anywhere, we definitely don't have a target
            if "no object" in text_lower or "no target" in text_lower:
                continue # This method says "No", try others? Or return False immediately?
                # If one method sees "No Object", it's likely correct.
                # But let's be safe and just say this method didn't find a target.
                continue

            # 2. Split into lines to handle "Selected Item" header cleanly
            lines = text_lower.split('\n')
            has_content = False
            found_target_name = False
            
            for line in lines:
                line = line.strip()
                if len(line) < 3:
                    continue
                    
                # Ignore the window header "Selected Item" (fuzzy match)
                if difflib.SequenceMatcher(None, "selected item", line).ratio() > 0.8:
                    continue

                # Check for "No Object Selected" line (fuzzy match)
                # This handles OCR errors like "No Objeci Selecied"
                # Increased threshold slightly and added more variations
                if difflib.SequenceMatcher(None, "no object selected", line).ratio() > 0.55:
                    has_content = False
                    break 
                
                if "no object" in line or "no target" in line:
                    has_content = False
                    break

                # Ignore "Distance" line if it's just the label (though usually it has numbers)
                # Actually, if we see "Distance", it implies a target exists!
                # "No Object Selected" does not show distance.
                if "distance" in line:
                    has_content = True
                    # Don't break yet if we are looking for a name
                    if not target_name:
                        break
                    
                # If we have a line that is NOT the header and NOT "No Object", it's likely the item name
                has_content = True
                
                # If we are looking for a specific target name, check it
                if target_name:
                    # Clean up line to remove common UI words that might cause false positives
                    clean_line = line.lower()
                    for noise in ["distance", "km", "m", "au", "type", "name", "selected", "item"]:
                        clean_line = clean_line.replace(noise, "")
                    
                    # Split into words for granular checking
                    words = clean_line.split()
                    
                    # Safety check: If "no object" survived cleaning (e.g. "no object"), skip
                    if "no object" in clean_line or "no target" in clean_line:
                        continue

                    valid_ores = [
                        'veldspar', 'scordite', 'pyroxeres', 'plagioclase', 
                        'kernite', 'jaspet', 'omber', 'hemorphite', 'hedbergite',
                        'spodumain', 'gneiss', 'crokite', 'bistot', 'arkonor', 'mercoxit'
                    ]
                    
                    for word in words:
                        # Skip garbage (Increased min length to 4 to avoid 'oer' matching 'omber')
                        if len(word) < 4: continue
                        
                        # 1. Check against specific target name parts
                        # e.g. target="Concentrated Veldspar", word="Veldspar"
                        target_parts = target_name.lower().split()
                        for part in target_parts:
                            # Increased threshold to 0.7 for stricter matching
                            if difflib.SequenceMatcher(None, part, word).ratio() > 0.7:
                                found_target_name = True
                                self.logger.info(f"Target verified: '{word}' matches target part '{part}' (Method: {method_name})")
                                break
                        
                        if found_target_name: break
                        
                        # 2. Check against ANY valid ore
                        # DISABLED when target_name is known to prevent hallucinations.
                        # If we are locked on 'Veldspar', we should NOT accept 'Omber' just because OCR saw 'oer'.
                        if not target_name:
                            for ore in valid_ores:
                                if difflib.SequenceMatcher(None, ore, word).ratio() > 0.7:
                                    found_target_name = True
                                    self.logger.info(f"Target verified: '{word}' matches ore '{ore}' (Method: {method_name})")
                                    break
                        
                        if found_target_name: break
                        
                        # 2b. Special Aliases for difficult ores (Only check if relevant to target)
                        # If target is Veldspar, we check for veld-like aliases.
                        if target_name and 'veldspar' in target_name.lower():
                             if 'yald' in word or 'vald' in word or 'veld' in word:
                                found_target_name = True
                                self.logger.info(f"Target verified: '{word}' matches Veldspar alias (Method: {method_name})")
                                break
                        elif not target_name:
                             # If no target specified, check generic aliases
                             if 'yald' in word or 'vald' in word or 'veld' in word:
                                found_target_name = True
                                self.logger.info(f"Target verified: '{word}' matches alias (Method: {method_name})")
                                break
                        
                        # 3. Check for "Asteroid" (Generic fallback)
                        if difflib.SequenceMatcher(None, "asteroid", word).ratio() > 0.7:
                            found_target_name = True
                            self.logger.info(f"Target verified: '{word}' matches 'asteroid' (Method: {method_name})")
                            break

                    if found_target_name:
                        break
                else:
                    break
            
            if has_content:
                if target_name:
                    if found_target_name:
                        return True
                else:
                    return True
        
        # If we get here, no method found the target
        if target_name:
             self.logger.debug(f"Target verification failed for '{target_name}'.")
        
        return False

    def read_inventory_tooltip(self, region):
        """
        Reads the inventory tooltip text and returns (current_m3, max_m3, percent_full).
        Returns (0, 0, 0) if failed.
        """
        img = self.capture_screen(region)
        
        # Scale up for better OCR
        # Use INTER_CUBIC for better text clarity on upscaling
        scale = 4
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)

        methods = []        # Method 1: HSV (Value Channel) + Otsu
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:,:,2]
        _, thresh_hsv = cv2.threshold(v_channel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("HSV", thresh_hsv))

        # Method 2: Gray + Otsu
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh_gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("Gray", thresh_gray))

        # Method 3: Gray + Fixed Threshold (Good if Otsu fails on dark background)
        # Text is white (high val), BG is dark (low val). 
        # THRESH_BINARY_INV: >127 becomes 0 (black), <127 becomes 255 (white).
        # So white text becomes black.
        _, thresh_fixed = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        methods.append(("Fixed", thresh_fixed))

        # Method 4: Dilated (Thicken text) - based on Fixed Threshold
        # Useful if the font is too thin or pixelated
        kernel = np.ones((2,2), np.uint8)
        thresh_dilated = cv2.erode(thresh_fixed, kernel, iterations=1) # Erode because text is black
        methods.append(("Dilated", thresh_dilated))

        valid_results = []

        for method_name, thresh in methods:
            # Add padding to help Tesseract with edge characters
            thresh_padded = cv2.copyMakeBorder(thresh, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            
            # Save debug image for this method
            cv2.imwrite(f"debug_tooltip_{method_name}.png", thresh_padded)

            # Whitelist digits and symbols to reduce confusion (e.g. B -> 8, S -> 5)
            custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789.,/m'
            text = pytesseract.image_to_string(thresh_padded, config=custom_config).strip()
            self.logger.info(f"[{method_name}] Raw tooltip text: '{text}'")
            
            # Regex to find "30,049.3/34,375.0"
            # Matches: number / number
            # Updated to allow spaces within the numbers (e.g. "30 500.2") which happens if commas are missed
            match = re.search(r'([\d,.\s]+)\s*/\s*([\d,.\s]+)', text)
            if match:
                try:
                    raw_max = match.group(2)
                    current_str = match.group(1).replace(',', '').replace(' ', '')
                    max_str = raw_max.replace(',', '').replace(' ', '')
                    
                    # Handle extra dots
                    if current_str.count('.') > 1:
                        current_str = current_str.replace('.', '', current_str.count('.') - 1)
                    if max_str.count('.') > 1:
                        max_str = max_str.replace('.', '', max_str.count('.') - 1)
                        
                    current_val = float(current_str)
                    max_val = float(max_str)
                    
                    # Fix for OCR missing decimal point in max_val (reading 34,375.0 as 34,3750)
                    # Pattern: Comma followed by 4 digits and no decimal point
                    if ',' in raw_max and '.' not in raw_max:
                        clean_raw = raw_max.strip()
                        parts = clean_raw.split(',')
                        if len(parts) > 1 and len(parts[-1].strip()) == 4:
                            max_val = max_val / 10.0
                            self.logger.info(f"Corrected max cargo (missing dot pattern) from {float(max_str)} to {max_val}")

                    # Fix for OCR reading thousands separators as decimals in max_val
                    # e.g. 34.3750 -> 34.375 instead of 34375.0
                    if max_val > 0 and (current_val / max_val) > 2.0:
                        # Try removing dots (treating them as thousands separators)
                        try:
                            alt_max_1 = float(max_str.replace('.', ''))
                            # Check if this makes sense (within 50% of current val)
                            if 0.5 < (current_val / alt_max_1) < 1.5:
                                max_val = alt_max_1
                                self.logger.info(f"Corrected max cargo from {float(max_str)} to {max_val}")
                            else:
                                # Try removing dots and dividing by 10 (e.g. 34.3750 -> 343750 -> 34375.0)
                                alt_max_2 = alt_max_1 / 10
                                if 0.5 < (current_val / alt_max_2) < 1.5:
                                    max_val = alt_max_2
                                    self.logger.info(f"Corrected max cargo from {float(max_str)} to {max_val}")
                        except:
                            pass

                    if max_val > 0:
                        percent = (current_val / max_val) * 100.0
                        
                        # Sanity check: Cargo cannot be significantly > 100%
                        # Tightened to 105% to catch OCR errors where digits are misread (e.g. 3 -> 9)
                        if percent > 105.0:
                            self.logger.warning(f"Discarding anomalous cargo reading: {current_val}/{max_val} ({percent:.1f}%)")
                            continue # Try next method

                        # Store valid result
                        valid_results.append({
                            'current': current_val,
                            'max': max_val,
                            'percent': percent,
                            'method': method_name
                        })
                except:
                    pass
        
        # Voting Logic
        if not valid_results:
            return 0.0, 0.0, 0.0
            
        # If only one result, return it
        if len(valid_results) == 1:
            r = valid_results[0]
            return r['current'], r['max'], r['percent']
            
        # Group by max_val (rounded to nearest int to handle float drift)
        from collections import Counter
        max_vals = [int(r['max']) for r in valid_results]
        counts = Counter(max_vals)
        
        # Get the most common max value(s)
        # most_common returns a list of (value, count) tuples
        most_common = counts.most_common()
        top_count = most_common[0][1]
        
        # Find all values that have the top count (handling ties)
        candidates = [val for val, count in most_common if count == top_count]
        
        winner_max = candidates[0]
        
        # Tie-breaking logic: If we have a tie, prefer the value supported by "Dilated" or "Fixed"
        if len(candidates) > 1:
            self.logger.info(f"Tie detected in cargo voting: {candidates}. Checking priority methods...")
            
            # Check if "Dilated" supports any candidate
            dilated_support = [r for r in valid_results if r['method'] == 'Dilated' and int(r['max']) in candidates]
            if dilated_support:
                winner_max = int(dilated_support[0]['max'])
                self.logger.info(f"Tie-breaker: Chose {winner_max} (Supported by Dilated)")
            else:
                # Check if "Fixed" supports any candidate
                fixed_support = [r for r in valid_results if r['method'] == 'Fixed' and int(r['max']) in candidates]
                if fixed_support:
                    winner_max = int(fixed_support[0]['max'])
                    self.logger.info(f"Tie-breaker: Chose {winner_max} (Supported by Fixed)")
        
        # Find the result object that matches the winner_max
        # We prefer the specific result from Dilated > Fixed > others if available for this max
        best_result = None
        
        # Try to find the result from Dilated first
        for r in valid_results:
            if int(r['max']) == winner_max and r['method'] == 'Dilated':
                best_result = r
                break
        
        # Then Fixed
        if not best_result:
            for r in valid_results:
                if int(r['max']) == winner_max and r['method'] == 'Fixed':
                    best_result = r
                    break
                    
        # Then any
        if not best_result:
            for r in valid_results:
                if int(r['max']) == winner_max:
                    best_result = r
                    break
                    
        self.logger.info(f"Consensus reached on max cargo: {best_result['max']} (Method: {best_result['method']})")
        return best_result['current'], best_result['max'], best_result['percent']

    def scan_overview(self, region):
        """
        Scans the overview region for text using Multi-Mode OCR (HSV, Gray, Fixed, Dilated).
        Returns a list of dictionaries containing parsed info.
        """
        img = self.capture_screen(region)
        
        # Scale up - 4x for maximum detail
        # Use INTER_LINEAR for overview text (Cubic can cause artifacts on small pixel fonts)
        scale = 4
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)

        methods = []

        # Method 1: HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:,:,2]
        _, thresh1 = cv2.threshold(v_channel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("HSV", thresh1))

        # Method 2: Gray
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("Gray", thresh2))

        # Method 3: Fixed Threshold
        _, thresh3 = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        methods.append(("Fixed", thresh3))

        # Method 4: Dilated
        kernel = np.ones((2,2), np.uint8)
        thresh4 = cv2.erode(thresh3, kernel, iterations=1)
        methods.append(("Dilated", thresh4))
        
        all_results = []

        for method_name, thresh in methods:
            # Add padding
            padding = 20
            thresh_padded = cv2.copyMakeBorder(thresh, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=255)
            
            custom_config = r'--oem 3 --psm 6' 
            data = pytesseract.image_to_data(thresh_padded, output_type=pytesseract.Output.DICT, config=custom_config)

            n_boxes = len(data['text'])
            
            # Reconstruct lines
            lines = {}
            tolerance = 6  # Reduced from 15 to prevent merging adjacent rows

            for i in range(n_boxes):
                text = data['text'][i].strip()
                if not text:
                    continue
                
                # Adjust coordinates (accounting for padding and scale)
                x = int((data['left'][i] - padding) / scale)
                y = int((data['top'][i] - padding) / scale)
                w = int(data['width'][i] / scale)
                h = int(data['height'][i] / scale)
                
                # Find a matching line
                found_line = None
                for line_y in lines:
                    if abs(line_y - y) < tolerance:
                        found_line = line_y
                        break
                
                if found_line is None:
                    found_line = y
                    lines[found_line] = []
                
                lines[found_line].append({
                    'text': text,
                    'x': x + region[0], 
                    'y': y + region[1], 
                    'w': w,
                    'h': h
                })

            # Process lines
            for y_coord in sorted(lines.keys()):
                line_words = lines[y_coord]
                line_words.sort(key=lambda k: k['x'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # Calculate average height to find vertical center
                avg_height = sum(w['h'] for w in line_words) / len(line_words)
                # Add half height to Y to click center of text, plus a larger buffer (6px) to ensure we don't click the row above
                center_y = int(y_coord + region[1] + (avg_height / 2) + 6)
                
                text_lower = full_text.lower()
                bad_words = ['belt', 'bel', 'delt', 'beit', 'belf', 'dott', 'dolt', 'cluster', 'couster']
                is_belt = any(bad in text_lower for bad in bad_words)
                
                if 'asteroid be' in text_lower or 'asteroid b' in text_lower:
                    is_belt = True
                
                is_far = 'au' in text_lower

                valid_ores = [
                    'veldspar', 'scordite', 'pyroxeres', 'plagioclase', 
                    'kernite', 'jaspet', 'omber', 'hemorphite', 'hedbergite'
                ]
                
                found_ore_name = None
                for ore in valid_ores:
                    if ore in text_lower:
                        found_ore_name = ore.capitalize()
                        break
                
                # If not found exactly, try fuzzy matching words in the text against valid_ores
                # This handles OCR errors like "scardite" -> "Scordite"
                if not found_ore_name:
                    words = text_lower.split()
                    for word in words:
                        # Skip short words/numbers
                        if len(word) < 4 or word.isdigit(): continue
                        
                        for ore in valid_ores:
                            # 80% match required (e.g. scardite vs scordite is 7/8 = 0.875)
                            if difflib.SequenceMatcher(None, word, ore).ratio() > 0.8:
                                found_ore_name = ore.capitalize()
                                break
                        if found_ore_name: break
                
                is_ore = found_ore_name is not None
                is_valid_asteroid = is_ore or ('asteroid' in text_lower and not is_belt and not is_far)
                
                # If it's a generic asteroid without a specific ore name, just call it "Asteroid"
                if is_valid_asteroid and not found_ore_name:
                    found_ore_name = "Asteroid"

                entry = {
                    'text': full_text,
                    'name': found_ore_name, # Clean name for verification
                    'y': center_y,
                    'x': region[0] + (region[2] // 2),
                    'is_asteroid': is_valid_asteroid,
                    'is_player': 'Player' in full_text,
                    'distance': self._parse_distance(full_text)
                }
                all_results.append(entry)

        # Deduplicate results by grouping nearby Y-coordinates
        # Instead of just checking for identical text, we group by row and pick the best result
        final_results = []
        
        # Sort all results by Y coordinate
        all_results.sort(key=lambda r: r['y'])
        
        if not all_results:
            return []
            
        current_group = [all_results[0]]
        
        for i in range(1, len(all_results)):
            entry = all_results[i]
            prev = current_group[-1]
            
            # If within 10 pixels vertically, consider it the same row
            if abs(entry['y'] - prev['y']) < 10:
                current_group.append(entry)
            else:
                # Process the completed group
                best_in_group = self._pick_best_result(current_group)
                final_results.append(best_in_group)
                current_group = [entry]
        
        # Process the last group
        if current_group:
            best_in_group = self._pick_best_result(current_group)
            final_results.append(best_in_group)
                
        return final_results

    def _pick_best_result(self, group):
        """
        Given a list of OCR results for the same row (from different methods),
        pick the one that seems most valid.
        """
        # Priority 1: Has a valid ore name
        ores = [r for r in group if r['name'] and r['name'] != "Asteroid"]
        if ores:
            # If multiple, pick the longest text (likely most complete)
            return max(ores, key=lambda r: len(r['text']))
            
        # Priority 2: Is an asteroid (generic)
        asteroids = [r for r in group if r['is_asteroid']]
        if asteroids:
            return max(asteroids, key=lambda r: len(r['text']))
            
        # Priority 3: Longest text
        return max(group, key=lambda r: len(r['text']))


    def find_text_in_region(self, region, target_text, exact_match=False):
        """
        Scans a region for specific text and returns the (x, y) center coordinates.
        Returns None if not found.
        """
        img = self.capture_screen(region)
        
        # Scale up - 4x for maximum detail
        # Use INTER_CUBIC for better text clarity on upscaling
        scale = 4
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)
        
        methods = []

        # Method 1: HSV (Value Channel)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:,:,2]
        _, thresh1 = cv2.threshold(v_channel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("HSV", thresh1))

        # Method 2: Gray + Otsu
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        methods.append(("Gray", thresh2))

        # Method 3: Fixed Threshold (Standard)
        _, thresh3 = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        methods.append(("Fixed", thresh3))

        # Method 3b: Dilated (Thicker text)
        # Good for thin fonts that get lost
        kernel = np.ones((2,2), np.uint8)
        thresh_dilated = cv2.erode(thresh3, kernel, iterations=1)
        methods.append(("Dilated", thresh_dilated))

        # Method 4: High Contrast (For light grey buttons)
        # Threshold at 190 to separate light grey (e.g. 150) from white text (255)
        _, thresh_high = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY_INV)
        methods.append(("HighContrast", thresh_high))

        # Method 5: Super High Contrast (For VERY light grey buttons)
        # Threshold at 240 to separate very light grey (e.g. 230) from pure white text (255)
        _, thresh_super = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        methods.append(("SuperHigh", thresh_super))

        # Method 6: Adaptive Threshold (Good for varying lighting/gradients)
        thresh_adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        methods.append(("Adaptive", thresh_adapt))

        # Method 7: Inverted (White text on Black background)
        # Sometimes Tesseract prefers this for certain fonts
        _, thresh_inv = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        methods.append(("Inverted", thresh_inv))
        
        all_found_texts = []
        
        # Try both PSM 6 (Block) and PSM 7 (Single Line)
        psm_modes = ['--psm 6', '--psm 7']
        
        best_fuzzy_match = None
        best_fuzzy_ratio = 0.0

        for method_name, thresh in methods:
            # Optimization: Skip certain methods for certain regions if known to fail
            # ... (comments omitted)
            
            # Add padding
            pad_val = 0 if method_name == "Inverted" else 255
            padding = 20
            thresh_padded = cv2.copyMakeBorder(thresh, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=pad_val)
            
            for psm in psm_modes:
                # Optimization: Skip PSM 7 for large regions like Overview/Inventory
                if psm == '--psm 7' and (region[2] > 300 and region[3] > 100):
                    continue

                data = pytesseract.image_to_data(thresh_padded, output_type=pytesseract.Output.DICT, config=psm)
                
                n_boxes = len(data['text'])
                target_lower = target_text.lower()
                target_words = target_lower.split()
                
                found_texts = []
                
                for i in range(n_boxes):
                    text = data['text'][i].strip().lower()
                    if not text:
                        continue
                    
                    found_texts.append(text)
                    
                    match = False
                    is_exact = False
                    
                    # Single word target
                    if len(target_words) == 1:
                        if exact_match:
                            if text == target_lower:
                                match = True
                                is_exact = True
                        else:
                            # Standard substring check
                            if target_lower in text:
                                match = True
                                is_exact = True
                            
                            # Fuzzy check (if not exact match required)
                            if not match and len(text) > 2:
                                # Special aliases for common misreads
                                # Removed 'un', 'undo', 'dock' as they cause false positives during docking (e.g. "Docking...")
                                if target_lower == 'undock' and any(alias in text for alias in ['endo', 'undoc', 'ndock', 'doce', 'eunos', '[ck']):
                                    # Treat alias as a very strong fuzzy match (0.95)
                                    ratio = 0.95
                                    if ratio > best_fuzzy_ratio:
                                        best_fuzzy_ratio = ratio
                                        best_fuzzy_match = (i, data, method_name, psm, padding, scale)
                                
                                if not match:
                                    ratio = difflib.SequenceMatcher(None, target_lower, text).ratio()
                                    # Lower threshold for short words
                                    threshold = 0.6 if len(target_lower) <= 6 else 0.8
                                    
                                    # Special case for "Guests" vs "Guster"
                                    if target_lower == "guests" and ratio < 0.8:
                                        threshold = 0.8
                                    
                                    # Special case for "Within" to avoid matching "Overview" or "Remove"
                                    # "Within" (6 chars) vs "Overview" (8 chars) can have low ratio but still trigger if threshold is 0.6
                                    if target_lower == "within":
                                        threshold = 0.85

                                    if ratio >= threshold:
                                        if ratio > best_fuzzy_ratio:
                                            best_fuzzy_ratio = ratio
                                            best_fuzzy_match = (i, data, method_name, psm, padding, scale)
                    
                    # Multi-word target (Phrase)
                    else:
                        if target_words[0] in text:
                            match_phrase = True
                            word_idx = 1
                            scan_idx = i + 1
                            
                            while word_idx < len(target_words):
                                while scan_idx < n_boxes and not data['text'][scan_idx].strip():
                                    scan_idx += 1
                                
                                if scan_idx >= n_boxes:
                                    match_phrase = False
                                    break
                                
                                next_text = data['text'][scan_idx].strip().lower()
                                if target_words[word_idx] not in next_text:
                                    match_phrase = False
                                    break
                                
                                word_idx += 1
                                scan_idx += 1
                            
                            if match_phrase:
                                match = True
                                is_exact = True
                    
                    if match and is_exact:
                        # Exact match found! Return immediately.
                        # Adjust for padding and scale
                        x = int((data['left'][i] - padding) / scale)
                        y = int((data['top'][i] - padding) / scale)
                        w = int(data['width'][i] / scale)
                        h = int(data['height'][i] / scale)
                        
                        center_x = region[0] + x + (w // 2)
                        center_y = region[1] + y + (h // 2)
                        
                        self.logger.info(f"Found EXACT text '{target_text}' at ({center_x}, {center_y}) using {method_name} method with {psm}")
                        return (center_x, center_y)
                
                all_found_texts.extend(found_texts)
        
        # If no exact match, check if we found a good fuzzy match
        if best_fuzzy_match:
            i, data, method_name, psm, padding, scale = best_fuzzy_match
            
            x = int((data['left'][i] - padding) / scale)
            y = int((data['top'][i] - padding) / scale)
            w = int(data['width'][i] / scale)
            h = int(data['height'][i] / scale)
            
            center_x = region[0] + x + (w // 2)
            center_y = region[1] + y + (h // 2)
            
            self.logger.info(f"Found FUZZY text '{target_text}' at ({center_x}, {center_y}) using {method_name} method with {psm} (Ratio: {best_fuzzy_ratio:.2f})")
            return (center_x, center_y)
            
        return None
        
        self.logger.info(f"Text '{target_text}' not found. Saw: {all_found_texts}")
        return None

    def _parse_distance(self, text):
        """
        Attempts to extract distance in km or m from the text line.
        Returns distance in km (float). 
        If 'm' is found, converts to km (e.g. 1500 m -> 1.5 km).
        """
        try:
            text_lower = text.lower()
            if 'au' in text_lower:
                return 999999.0 # Too far

            # Regex to find number followed by unit
            # Matches: "10 km", "10km", "1,234 m", "1234m", "10.5 km"
            # Group 1: The number (including commas/dots)
            # Group 2: The unit (km or m)
            match = re.search(r'([\d,.]+)\s*(km|m)', text_lower)
            if match:
                num_str = match.group(1).replace(',', '')
                unit = match.group(2)
                
                # Handle potential multiple dots if OCR messes up (e.g. 1.2.3)
                if num_str.count('.') > 1:
                    num_str = num_str.replace('.', '', num_str.count('.') - 1)
                
                val = float(num_str)
                
                if unit == 'm':
                    return val / 1000.0
                return val
                
        except Exception as e:
            # self.logger.error(f"Error parsing distance: {e}")
            pass
            
        return 9999.0 # Unknown distance
