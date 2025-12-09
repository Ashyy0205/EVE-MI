import pyautogui
import time
import logging

# Fail-safe: moving mouse to upper-left corner will abort script
pyautogui.FAILSAFE = True

class InputController:
    def __init__(self):
        self.logger = logging.getLogger("BotLogger")
        pyautogui.PAUSE = 0.1 # Short pause after each action
        # Disable failsafe because negative coordinates on multi-monitor setups can trigger it falsely
        pyautogui.FAILSAFE = False 
        self.safe_spot = (200, 200)

    def move_to_safe_spot(self):
        """
        Moves mouse to a neutral position to avoid tooltips.
        """
        pyautogui.moveTo(self.safe_spot[0], self.safe_spot[1])

    def approach_target(self, x, y):
        """
        Hold Q -> Click (x,y) -> Release Q
        """
        self.logger.info(f"Approaching target at {x}, {y}")
        pyautogui.moveTo(x, y)
        pyautogui.keyDown('q')
        time.sleep(0.1)
        pyautogui.click()
        time.sleep(0.1)
        pyautogui.keyUp('q')
        self.move_to_safe_spot()

    def lock_target(self, x, y):
        """
        Hold Ctrl -> Click (x,y) -> Release Ctrl
        """
        self.logger.info(f"Locking target at {x}, {y}")
        pyautogui.moveTo(x, y)
        pyautogui.keyDown('ctrl')
        time.sleep(0.1)
        pyautogui.click()
        time.sleep(0.1)
        pyautogui.keyUp('ctrl')
        self.move_to_safe_spot()
        
        # Wait for lock to establish
        time.sleep(2.0)

    def activate_miners(self):
        """
        Press F1, F2
        """
        self.logger.info("Activating miners")
        pyautogui.press('f1')
        time.sleep(0.5)
        pyautogui.press('f2')
        self.move_to_safe_spot()

    def toggle_selected_item_window(self):
        """
        Press Alt+S to toggle the selected item window
        """
        self.logger.info("Toggling Selected Item window (Alt+S)")
        pyautogui.keyDown('alt')
        time.sleep(0.1)
        pyautogui.press('s')
        time.sleep(0.1)
        pyautogui.keyUp('alt')
        self.move_to_safe_spot()

    def activate_scanner(self):
        """
        Press Alt+S to activate the survey scanner
        """
        self.logger.info("Activating scanner (Alt+S)")
        pyautogui.keyDown('alt')
        time.sleep(0.1)
        pyautogui.press('s')
        time.sleep(0.1)
        pyautogui.keyUp('alt')
        self.move_to_safe_spot()

    def move_mouse(self, point):
        """
        Moves mouse to a specific point (x, y).
        """
        pyautogui.moveTo(point[0], point[1])

    def hover_inventory_bar(self, point):
        """
        Moves mouse to the inventory hover point.
        point: (x, y)
        """
        pyautogui.moveTo(point[0], point[1])

    def right_click_point(self, point):
        """
        Moves to point and right clicks.
        point: (x, y)
        """
        self.logger.info(f"Right clicking at {point}")
        pyautogui.moveTo(point[0], point[1])
        time.sleep(0.2)
        pyautogui.rightClick()
        time.sleep(0.2)

    def click_point(self, point):
        """
        Moves to point and left clicks.
        point: (x, y)
        """
        self.logger.info(f"Clicking at {point}")
        pyautogui.moveTo(point[0], point[1])
        time.sleep(0.2)
        pyautogui.click()
        time.sleep(0.2)

    def stop_ship(self):
        """
        Ctrl + Space
        """
        self.logger.info("Stopping ship")
        pyautogui.keyDown('ctrl')
        time.sleep(0.1)
        pyautogui.press('space')
        time.sleep(0.1)
        pyautogui.keyUp('ctrl')
        self.move_to_safe_spot()

    def drag_and_drop(self, start_x, start_y, end_x, end_y):
        """
        Drags from start to end.
        """
        self.logger.info(f"Dragging from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        pyautogui.moveTo(start_x, start_y)
        time.sleep(0.2)
        pyautogui.mouseDown()
        time.sleep(0.2)
        pyautogui.moveTo(end_x, end_y, duration=0.5) # Smooth drag
        time.sleep(0.2)
        pyautogui.mouseUp()
        self.move_to_safe_spot()

    def select_all(self):
        """
        Press Ctrl+A
        """
        self.logger.info("Selecting all items (Ctrl+A)")
        pyautogui.keyDown('ctrl')
        time.sleep(0.1)
        pyautogui.press('a')
        time.sleep(0.1)
        pyautogui.keyUp('ctrl')
