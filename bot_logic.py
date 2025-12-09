import time
import logging
import json
import os
from enum import Enum, auto

class BotState(Enum):
    IDLE = auto()
    CHECK_CARGO = auto()
    SCANNING = auto()
    APPROACHING = auto()
    LOCKING = auto()
    MINING = auto()
    DOCKING = auto()
    UNLOADING = auto()
    UNDOCKING = auto()
    TRAVELING = auto()

class MiningBot:
    def __init__(self, vision_system, input_controller):
        self.vision = vision_system
        self.input = input_controller
        self.logger = logging.getLogger("BotLogger")
        
        self.state = BotState.IDLE
        self.running = False
        
        # Configuration
        self.overview_region, self.selected_item_region, self.inventory_hover_point, self.tooltip_region, self.dropoff_list_region, self.inventory_window_region, self.warp_status_region, self.undock_region = self.load_config()
        
        self.current_target = None
        self.mining_start_time = 0
        self.lost_target_counter = 0
        self.last_cargo_check = 0
        self.known_max_cargo = None # Track max cargo to filter OCR errors
        self.approach_command_sent = False # Track if we have already clicked approach
        self.scan_fail_count = 0 # Track consecutive scan failures
        # self.mining_duration = 60 # No longer used with new logic

    def load_config(self):
        default_overview = (800, 100, 400, 600)
        default_selected = (100, 100, 200, 200)
        default_inv_pt = (0, 0)
        default_tooltip = (0, 0, 0, 0)
        default_dropoff = (0, 0, 0, 0)
        default_inv_window = (0, 0, 0, 0)
        default_warp_status = (0, 0, 0, 0)
        default_undock = (0, 0, 0, 0)
        
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r') as f:
                    data = json.load(f)
                    overview = tuple(data.get('overview_region', default_overview))
                    selected = tuple(data.get('selected_item_region', default_selected))
                    inv_pt = tuple(data.get('inventory_hover_point', default_inv_pt))
                    tooltip = tuple(data.get('tooltip_region', default_tooltip))
                    dropoff = tuple(data.get('dropoff_list_region', default_dropoff))
                    inv_window = tuple(data.get('inventory_window_region', default_inv_window))
                    warp_status = tuple(data.get('warp_status_region', default_warp_status))
                    undock = tuple(data.get('undock_region', default_undock))
                    
                    self.logger.info(f"Loaded config.")
                    return overview, selected, inv_pt, tooltip, dropoff, inv_window, warp_status, undock
            except Exception as e:
                self.logger.error(f"Failed to load config: {e}")
        
        self.logger.warning("Config not found. Using defaults.")
        return default_overview, default_selected, default_inv_pt, default_tooltip, default_dropoff, default_inv_window, default_warp_status, default_undock

    def start(self):
        self.running = True
        self.logger.info("Bot started. Checking initial state...")
        
        # Check if we are docked (look for Undock button)
        if self.undock_region[2] > 0:
            undock_region = self.undock_region
        else:
            # Fallback: Check for "Undock" in the top-right area (Station Services)
            undock_region = (
                self.overview_region[0],  # x
                0,                        # y
                self.overview_region[2],  # w
                800                       # h (Search top 800px)
            )
            
        check = self.vision.find_text_in_region(undock_region, "Undock", exact_match=True)
        
        if check:
            self.logger.info("Undock button detected. We are docked. Starting UNDOCKING sequence.")
            self.state = BotState.UNDOCKING
        else:
            self.logger.info("Undock button not found. Assuming we are in space. Starting CHECK_CARGO.")
            self.state = BotState.CHECK_CARGO

    def stop(self):
        self.running = False
        self.state = BotState.IDLE
        self.logger.info("Bot stopped.")

    def update(self):
        if not self.running:
            return

        if self.state == BotState.CHECK_CARGO:
            self._handle_check_cargo()
        elif self.state == BotState.SCANNING:
            self._handle_scanning()
        elif self.state == BotState.APPROACHING:
            self._handle_approaching()
        elif self.state == BotState.LOCKING:
            self._handle_locking()
        elif self.state == BotState.MINING:
            self._handle_mining()
        elif self.state == BotState.DOCKING:
            self._handle_docking()
        elif self.state == BotState.UNLOADING:
            self._handle_unloading()
        elif self.state == BotState.UNDOCKING:
            self._handle_undocking()
        elif self.state == BotState.TRAVELING:
            self._handle_traveling()

    def _handle_check_cargo(self):
        self._check_cargo()
        # If cargo check didn't trigger docking, proceed to scanning
        if self.state == BotState.CHECK_CARGO:
            self.state = BotState.SCANNING

    def _handle_scanning(self):
        self.logger.info("Scanning overview...")
        results = self.vision.scan_overview(self.overview_region)
        
        # Filter for asteroids
        asteroids = [r for r in results if r['is_asteroid']]
        
        # Safety check for players
        players = [r for r in results if r['is_player']]
        if players:
            self.logger.warning("Player detected! Ignoring for now.")
            # self.stop() # User requested to ignore player safety stop
            # return

        if asteroids:
            # Pick the first one (or closest)
            self.current_target = asteroids[0]
            # Use the clean name if available, otherwise fallback to text
            self.current_target_name = self.current_target.get('name', self.current_target['text'])
            
            self.logger.info(f"Found target: {self.current_target['text']} (Identified as: {self.current_target_name})")
            self.state = BotState.APPROACHING
            self.approach_command_sent = False # Reset approach flag
            self.scan_fail_count = 0
        else:
            self.scan_fail_count += 1
            self.logger.info(f"No asteroids found. Retrying... ({self.scan_fail_count}/2)")
            
            if self.scan_fail_count >= 2:
                self.logger.info("No asteroids found after retries. Warping to next Asteroid Belt...")
                self.state = BotState.TRAVELING
                self.scan_fail_count = 0
            else:
                time.sleep(2)

    def _handle_approaching(self):
        if not self.current_target:
            self.state = BotState.SCANNING
            return

        # Check distance
        # We need to re-scan to get updated distance
        # For simplicity, we'll assume we can just read the line again or we just approach once
        # In a real loop, we'd track the specific row. 
        # Here, we'll do a quick re-scan to find the same target or just trust the initial command for a bit.
        
        # Let's re-scan to get current distance
        results = self.vision.scan_overview(self.overview_region)
        # Try to match our current target by text or position (fuzzy match)
        # This is tricky if things move. We'll just pick the first asteroid again for this simple logic.
        asteroids = [r for r in results if r['is_asteroid']]
        
        if not asteroids:
            self.state = BotState.SCANNING
            return
            
        target = asteroids[0] # Update target info
        dist = target['distance']
        
        self.logger.info(f"Target distance: {dist} km")

        if dist < 15.0:
            # We are close enough
            self.logger.info("In range (<15km). Stopping ship and locking.")
            self.input.stop_ship()
            time.sleep(1.0) # Wait for stop command to register
            self.state = BotState.LOCKING
        else:
            # Approach if not already doing so
            if not self.approach_command_sent:
                self.input.approach_target(target['x'], target['y'])
                self.approach_command_sent = True
                self.logger.info("Approach command sent. Waiting to reach range...")
            
            time.sleep(1.0) # Wait a bit while ship moves, then loop will check distance again

    def _handle_locking(self):
        self.logger.info("Locking target...")
        
        max_retries = 3
        for attempt in range(max_retries):
            # Scan to get fresh coordinates every attempt (ship might be moving)
            results = self.vision.scan_overview(self.overview_region)
            asteroids = [r for r in results if r['is_asteroid']]
            
            if not asteroids:
                self.logger.warning("No asteroids found during locking attempt.")
                self.state = BotState.SCANNING
                return
                
            target = asteroids[0]
            # Use the clean name if available, otherwise fallback to text
            self.current_target_name = target.get('name', target['text'])
            
            self.logger.info(f"Locking attempt {attempt+1}/{max_retries} at {target['x']}, {target['y']} ({self.current_target_name})")
            
            self.input.lock_target(target['x'], target['y'])
            
            # Wait for lock to finish
            time.sleep(4.0)

            # Check if we have a lock (Selected Item window has text matching target)
            if self.vision.has_selected_target(self.selected_item_region, self.current_target_name):
                self.logger.info("Lock confirmed.")
                break
            
            # If not, try toggling the window, maybe it's just closed
            self.logger.info("Lock not detected. Toggling Selected Item window...")
            self.input.toggle_selected_item_window()
            time.sleep(2.0)
            
            if self.vision.has_selected_target(self.selected_item_region, self.current_target_name):
                self.logger.info("Lock confirmed after toggle.")
                break
                
            self.logger.warning("Lock failed (Target name not found). Retrying...")
        else:
            self.logger.error("Failed to lock target after multiple attempts. Returning to SCANNING.")
            self.state = BotState.SCANNING
            return

        self.state = BotState.MINING
        self.mining_start_time = time.time()
        
        # Activate scanner
        self.input.activate_scanner()
        time.sleep(1.0)

        # Start lasers
        self.input.activate_miners()
        
        # Stop ship is now handled in APPROACHING state

    def _handle_mining(self):
        # Check if the asteroid is still selected
        # We look at the "Selected Item" region and verify the target name is still there
        has_target = self.vision.has_selected_target(self.selected_item_region, self.current_target_name)
        
        if not has_target:
            self.lost_target_counter += 1
            self.logger.warning(f"Target '{self.current_target_name}' potentially lost... ({self.lost_target_counter}/5)")
            
            if self.lost_target_counter >= 5:
                self.logger.info("Target confirmed lost (depleted). Waiting 45s for lasers to cycle down...")
                # Wait for lasers to fully deactivate/cycle down before starting new cycle
                time.sleep(45.0)
                self.state = BotState.CHECK_CARGO
                self.lost_target_counter = 0
            else:
                time.sleep(1)
        else:
            # Target is still there, reset counter
            self.lost_target_counter = 0
            
            # Target is still there, keep mining
            # DO NOT SCAN OVERVIEW or do anything else
            # Just wait and log occasionally
            if time.time() % 10 < 0.1:
                self.logger.info("Mining in progress... Target still active.")
            
            # Check cargo every 30 seconds
            if time.time() - self.last_cargo_check > 30:
                self._check_cargo()
                self.last_cargo_check = time.time()
                
            time.sleep(1) # Sleep to prevent high CPU usage

    def _check_cargo(self):
        # Only check if regions are defined
        if self.inventory_hover_point[0] == 0 or self.tooltip_region[2] == 0:
            return

        self.logger.info("Checking cargo capacity...")
        
        # Hover over the bar
        self.input.hover_inventory_bar(self.inventory_hover_point)
        time.sleep(1.0) # Wait for tooltip
        
        # Read tooltip
        curr, max_val, pct = self.vision.read_inventory_tooltip(self.tooltip_region)
        
        if max_val > 0:
            # --- Max Cargo Validation Logic ---
            if self.known_max_cargo is None:
                # First reading, accept it but be cautious if it's huge
                self.known_max_cargo = max_val
            else:
                # Check if new max_val is wildly different (e.g. > 2x or < 0.5x)
                ratio = max_val / self.known_max_cargo
                if ratio > 2.0 or ratio < 0.5:
                    self.logger.warning(f"Anomalous max cargo reading: {max_val} (Expected ~{self.known_max_cargo}). Ignoring.")
                    max_val = self.known_max_cargo # Use known good value
                else:
                    # Update known max (maybe average it? or just take it if it's close)
                    # For now, just keep the first good one to avoid drift from errors
                    pass
            
            # --- Current Cargo Validation Logic ---
            # If current cargo is > max_val * 1.02, it's likely an OCR error
            # Mining holds don't typically overfill beyond 100%
            if curr > max_val * 1.02:
                self.logger.warning(f"Anomalous current cargo reading: {curr} > {max_val} (102%+). Ignoring.")
                # Move mouse away and return
                self.input.move_to_safe_spot()
                return

            # Recalculate percentage with validated values
            pct = (curr / max_val) * 100.0
            
            self.logger.info(f"Cargo: {curr:.1f}/{max_val:.1f} m3 ({pct:.1f}%)")
            
            if pct >= 99.0:
                self.logger.info("Cargo full! Initiating docking sequence.")
                self.state = BotState.DOCKING
        else:
            self.logger.warning("Failed to read cargo tooltip.")
            
        # Move mouse away
        self.input.move_to_safe_spot()

    def _handle_docking(self):
        self.logger.info("Docking...")
        
        # 1. Find "DropOff" in the locations list
        self.logger.info("Scanning for 'DropOff' location...")
        dropoff_loc = self.vision.find_text_in_region(self.dropoff_list_region, "DropOff")
        
        if not dropoff_loc:
            self.logger.error("Could not find 'DropOff' in the locations list!")
            # Maybe retry or scroll? For now, just abort.
            self.stop()
            return
            
        self.logger.info(f"Found 'DropOff' at {dropoff_loc}. Right-clicking...")
        
        # 2. Right click it
        self.input.right_click_point(dropoff_loc)
        time.sleep(1.0) # Wait for menu
        
        # 3. Find "Dock" in the context menu
        # We scan a region around the mouse click. 
        # Context menus usually appear down-right from the cursor.
        # Let's define a search area: x to x+200, y to y+300
        menu_region = (dropoff_loc[0], dropoff_loc[1], 200, 300)
        
        self.logger.info("Scanning for 'Dock' command...")
        dock_loc = self.vision.find_text_in_region(menu_region, "Dock")
        
        if not dock_loc:
            self.logger.error("Could not find 'Dock' option in context menu!")
            self.stop()
            return
            
        self.logger.info(f"Found 'Dock' at {dock_loc}. Clicking...")
        self.input.click_point(dock_loc)
        
        self.logger.info("Docking command sent. Waiting for arrival...")
        
        # Wait for docking to complete
        # We check if the "Undock" button appears in the overview region (Station Services)
        docked = False
        consecutive_confirmations = 0
        required_confirmations = 2

        for i in range(40): # Wait up to 2 minutes (40 * 3s)
            time.sleep(3.0)
            self.logger.info(f"Checking docking status (looking for 'Undock')... ({i+1}/40)")
            
            # Use configured undock region if available
            if self.undock_region[2] > 0:
                undock_region = self.undock_region
            else:
                # Fallback: Check for "Undock" in the top-right area (Station Services)
                undock_region = (
                    self.overview_region[0],  # x
                    0,                        # y
                    self.overview_region[2],  # w
                    800                       # h (Search top 800px)
                )
            
            # Check for "Undock" or other station indicators
            is_docked = False
            
            # 1. Try "Undock" (Exact match required to avoid "Docking..." false positives)
            check = self.vision.find_text_in_region(undock_region, "Undock", exact_match=True)
            if check:
                is_docked = True
            
            # 2. Fallback: Try "Hangars" (Tab)
            if not is_docked:
                check = self.vision.find_text_in_region(undock_region, "Hangars")
                if check:
                    self.logger.info("Found 'Hangars' tab. Confirmed docked.")
                    is_docked = True
            
            # 3. Fallback: Try "Guests" (Tab)
            if not is_docked:
                check = self.vision.find_text_in_region(undock_region, "Guests")
                if check:
                    self.logger.info("Found 'Guests' tab. Confirmed docked.")
                    is_docked = True

            if is_docked:
                consecutive_confirmations += 1
                self.logger.info(f"Docking confirmed ({consecutive_confirmations}/{required_confirmations})")
                if consecutive_confirmations >= required_confirmations:
                    docked = True
                    break
            else:
                consecutive_confirmations = 0
        
        if docked:
            self.logger.info("Station interface detected. We are docked!")
            # No delay needed, seeing "Undock" means station loaded
            self.state = BotState.UNLOADING
        else:
            self.logger.error("Timed out waiting to dock (Undock button never appeared).")
            self.stop()

    def _handle_unloading(self):
        self.logger.info("Unloading cargo...")
        
        # 1. Focus Inventory Window
        # Click in the center of the inventory window to ensure focus
        cx = self.inventory_window_region[0] + (self.inventory_window_region[2] // 2)
        cy = self.inventory_window_region[1] + (self.inventory_window_region[3] // 2)
        self.input.click_point((cx, cy))
        time.sleep(0.5)
        
        # 1.5 Click "Mining Hold" in sidebar
        self.logger.info("Selecting 'Mining Hold'...")
        mining_hold = self.vision.find_text_in_region(self.inventory_window_region, "Mining Hold")
        
        if not mining_hold:
            # Fallback: "Mining hold"
            mining_hold = self.vision.find_text_in_region(self.inventory_window_region, "Mining hold")
            
        if mining_hold:
            self.logger.info(f"Found 'Mining Hold' at {mining_hold}. Clicking...")
            self.input.click_point(mining_hold)
            time.sleep(1.0) # Wait for view to switch
        else:
            self.logger.warning("Could not find 'Mining Hold' button. Assuming already selected or proceeding anyway.")

        # 2. Find "Item Hangar" drop target
        self.logger.info("Scanning for 'Item Hangar'...")
        # We search for "Item Hangar" or "Item hangar" or "Ship hangar" if needed
        # Using exact_match=False to catch "Item hangar"
        drop_target = self.vision.find_text_in_region(self.inventory_window_region, "Item Hangar")
        
        if not drop_target:
            # Fallback: try "Item hangar" (lowercase h)
            drop_target = self.vision.find_text_in_region(self.inventory_window_region, "Item hangar")
            
        if not drop_target:
            self.logger.error("Could not find 'Item Hangar' in inventory window!")
            self.stop()
            return
            
        self.logger.info(f"Found drop target at {drop_target}")

        # 3. Select All
        # Click in the item area (right side) to ensure focus is on the items, not the sidebar
        item_area_x = self.inventory_window_region[0] + int(self.inventory_window_region[2] * 0.75)
        item_area_y = self.inventory_window_region[1] + (self.inventory_window_region[3] // 2)
        self.input.click_point((item_area_x, item_area_y))
        time.sleep(0.5)
        
        self.input.select_all()
        time.sleep(0.5)
        
        # 4. Find a valid ore to drag
        # We look for any ore name in the inventory window
        valid_ores = ['veldspar', 'scordite', 'pyroxeres', 'plagioclase', 'kernite', 'jaspet', 'omber', 'hemorphite', 'hedbergite']
        
        found_ore_loc = None
        for ore in valid_ores:
            loc = self.vision.find_text_in_region(self.inventory_window_region, ore)
            if loc:
                self.logger.info(f"Found ore '{ore}' at {loc} to use as interaction point.")
                found_ore_loc = loc
                break
        
        if found_ore_loc:
            # --- Compression Step ---
            self.logger.info("Attempting to compress ore...")
            self.input.right_click_point(found_ore_loc)
            time.sleep(1.0)
            
            # Search for "Compress" in the context menu
            # Context menu appears near the click
            menu_region = (found_ore_loc[0], found_ore_loc[1], 300, 400)
            compress_opt = self.vision.find_text_in_region(menu_region, "Compress")
            
            if compress_opt:
                self.logger.info(f"Found 'Compress' option at {compress_opt}. Clicking...")
                self.input.click_point(compress_opt)
                time.sleep(3.0) # Wait for compression animation/server response
                
                # Re-select all items as the compression replaces items
                self.logger.info("Re-selecting all items after compression...")
                self.input.click_point((item_area_x, item_area_y)) # Ensure focus
                time.sleep(0.5)
                self.input.select_all()
                time.sleep(0.5)
                
                # Re-find ore location to drag (positions might have shifted)
                found_ore_loc = None
                for ore in valid_ores:
                    loc = self.vision.find_text_in_region(self.inventory_window_region, ore)
                    if loc:
                        found_ore_loc = loc
                        break
            else:
                self.logger.info("No 'Compress' option found (or already compressed). Proceeding to unload.")
                # Close context menu by clicking the item again (this might deselect others, so we re-select all)
                self.input.click_point(found_ore_loc)
                time.sleep(0.5)
                self.input.select_all()
                time.sleep(0.5)

        if found_ore_loc:
            # 5. Drag to Item Hangar
            self.input.drag_and_drop(found_ore_loc[0], found_ore_loc[1], drop_target[0], drop_target[1])
            self.logger.info("Cargo unloaded.")
            
            # Verify Unloading
            time.sleep(2.0) # Wait for server sync
            self.logger.info("Verifying cargo capacity...")
            
            # We need to hover over the inventory bar again to get the tooltip
            self.input.move_mouse(self.inventory_hover_point)
            time.sleep(0.5)
            
            current, max_cap, pct = self.vision.read_inventory_tooltip(self.tooltip_region)
            
            if max_cap > 0:
                self.logger.info(f"Cargo after unload: {current}/{max_cap} m3 ({pct:.1f}%)")
                
                if pct < 10.0:
                    self.logger.info("Unload successful. Proceeding to Undock.")
                    self.state = BotState.UNDOCKING
                else:
                    self.logger.warning("Cargo still seems full! Unload might have failed.")
                    self.stop()
            else:
                self.logger.warning("Could not verify cargo capacity. Assuming success and undocking.")
                self.state = BotState.UNDOCKING
            
        else:
            self.logger.warning("No ore found in inventory to unload (or OCR failed).")
            self.stop()

    def _handle_undocking(self):
        self.logger.info("Initiating Undock sequence...")
        
        # Use configured undock region if available, otherwise fallback to dynamic calculation
        if self.undock_region[2] > 0:
            undock_region = self.undock_region
            self.logger.info(f"Using configured Undock region: {undock_region}")
        else:
            # We use the same region logic as docking check to find the button
            # Increased height to 800 to cover more of the top area
            undock_region = (
                self.overview_region[0],  # x
                0,                        # y
                self.overview_region[2],  # w
                800                       # h
            )
            self.logger.info(f"Using dynamic Undock region: {undock_region}")
        
        # Check for "Undock" or other station indicators
        undock_btn = self.vision.find_text_in_region(undock_region, "Undock")
        
        if not undock_btn:
            self.logger.error("Could not find 'Undock' button!")
            self.stop()
            return
            
        self.logger.info(f"Clicking Undock at {undock_btn}")
        self.input.click_point(undock_btn)
        
        # Wait for Undock button to disappear
        self.logger.info("Waiting for undock to complete...")
        undocked = False
        for i in range(30): # Wait up to 90s
            time.sleep(3.0)
            check = self.vision.find_text_in_region(undock_region, "Undock")
            if not check:
                self.logger.info("Undock button gone. We are in space.")
                undocked = True
                break
        
        if undocked:
            time.sleep(5.0) # Give a moment for space to load
            self.state = BotState.TRAVELING
        else:
            self.logger.error("Timed out waiting to undock.")
            self.stop()

    def _handle_traveling(self):
        self.logger.info("Traveling to Asteroid Belt...")
        
        # Move mouse to safe spot to ensure no tooltips interfere with scanning
        self.input.move_to_safe_spot()
        time.sleep(0.5)
        
        # 1. Find "Asteroid Belt" in Overview using scan_overview for better accuracy
        # This avoids fuzzy matching errors where it might click a Planet or random text
        results = self.vision.scan_overview(self.overview_region)
        
        # Filter for all asteroid belts
        belt_entries = [e for e in results if "asteroid belt" in e['text'].lower()]
        
        if not belt_entries:
            self.logger.error("No Asteroid Belt found in Overview!")
            self.stop()
            return
            
        warp_initiated = False
        
        for entry in belt_entries:
            belt_loc = (entry['x'], entry['y'])
            self.logger.info(f"Checking belt: {entry['text']} at {belt_loc}")
            
            # Right-click to open context menu
            self.input.right_click_point(belt_loc)
            time.sleep(1.0)
            
            # Search for Warp option near the click
            menu_region = (belt_loc[0], belt_loc[1], 300, 400)
            
            # Use exact_match=True for "Within" to avoid matching "Remove Location from Overview"
            # "Within" is short and can be fuzzy matched to parts of "Overview" or "Remove"
            warp_opt = self.vision.find_text_in_region(menu_region, "Warp to Within", exact_match=True)
            
            if not warp_opt:
                # Try "Within" but enforce exact match to avoid "Overview" false positives
                warp_opt = self.vision.find_text_in_region(menu_region, "Within", exact_match=True)
            
            if not warp_opt:
                # "Warp to" is safer, but still good to be careful
                warp_opt = self.vision.find_text_in_region(menu_region, "Warp to", exact_match=True)
                
            if warp_opt:
                self.logger.info(f"Found Warp option at {warp_opt}. Clicking...")
                self.input.click_point(warp_opt)
                
                # Move mouse to safe spot to prevent interference with subsequent scanning
                self.input.move_to_safe_spot()
                
                warp_initiated = True
                break
            else:
                self.logger.info("No 'Warp to' option found (likely current belt). Trying next...")
                # Close context menu by clicking DropOff (or safe spot if DropOff not found)
                # User requested clicking DropOff to reset focus
                dropoff_loc = self.vision.find_text_in_region(self.dropoff_list_region, "DropOff")
                if dropoff_loc:
                    self.input.click_point(dropoff_loc)
                else:
                    self.input.move_to_safe_spot()
                    self.input.click_point(self.input.safe_spot) # Click safe spot to close menu
                time.sleep(1.0)
        
        if not warp_initiated:
            self.logger.error("Could not find a valid belt to warp to (all checked).")
            self.stop()
            return
        
        # 3. Monitor Warp Status
        self.logger.info("Warp initiated. Monitoring warp status...")
        time.sleep(5.0) # Wait for warp to actually start
        
        warping = True
        # Wait for "Warp" text to appear then disappear, or just disappear if we missed the start
        # Actually, user said "wait until all mentions of warp/warping is gone"
        
        # We check periodically. If we see "Warping", we are warping.
        # If we don't see it for a while, we are done.
        
        # First, wait for it to appear (timeout 10s)
        seen_warp_text = False
        for i in range(10):
            text_loc = self.vision.find_text_in_region(self.warp_status_region, "Warping")
            if not text_loc:
                text_loc = self.vision.find_text_in_region(self.warp_status_region, "Warp")
            
            if text_loc:
                seen_warp_text = True
                self.logger.info("Warp drive active detected.")
                break
            time.sleep(1.0)
            
        if not seen_warp_text:
            self.logger.warning("Did not detect 'Warping' text. Assuming short warp or missed it.")
        
        # Now wait for it to be GONE
        self.logger.info("Waiting for warp to finish...")
        while True:
            text_loc = self.vision.find_text_in_region(self.warp_status_region, "Warping")
            if not text_loc:
                text_loc = self.vision.find_text_in_region(self.warp_status_region, "Warp")
            
            if not text_loc:
                self.logger.info("Warp text gone. Arrived at destination.")
                break
            
            time.sleep(2.0)

        # Transition to mining loop
        self.logger.info("Arrived at belt. Starting mining loop...")
        self.state = BotState.CHECK_CARGO
            
        self.logger.info("Travel complete. Resuming mining operations.")
        self.state = BotState.SCANNING
