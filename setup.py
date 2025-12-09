import sys
import json
from PyQt6.QtWidgets import QApplication, QMainWindow, QRubberBand
from PyQt6.QtCore import QRect, QPoint, Qt, QSize, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen

class RegionSelector(QMainWindow):
    def __init__(self):
        super().__init__()
        # Make the window frameless, full screen, and always on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Calculate total geometry of all screens to cover multiple monitors
        total_rect = QRect()
        for screen in QApplication.screens():
            total_rect = total_rect.united(screen.geometry())
            
        self.setGeometry(total_rect)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        self.begin = QPoint()
        self.end = QPoint()
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        self.step = 1 
        # 1 = Overview (Box)
        # 2 = Selected Item (Box)
        # 3 = Inventory Hover (Click)
        # 4 = Tooltip (Box)
        # 5 = DropOff List Region (Box)
        # 6 = Entire Inventory Window (Box)
        
        self.overview_rect = None
        self.selected_item_rect = None
        self.inventory_hover_point = None
        self.tooltip_rect = None
        self.dropoff_list_rect = None
        self.inventory_window_rect = None
        self.warp_status_rect = None
        
        print("Instructions:")
        print("STEP 1: Draw a box around the OVERVIEW list.")
        
        self.show()

    def paintEvent(self, event):
        # Draw a semi-transparent black overlay
        painter = QPainter(self)
        painter.setBrush(QColor(0, 0, 0, 100)) # Black with alpha=100
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        
        # Draw instructions text
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(20)
        painter.setFont(font)
        
        if self.step == 1:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 1: Draw box around OVERVIEW list")
        elif self.step == 2:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 2: Draw box around SELECTED ITEM window")
        elif self.step == 3:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 3: CLICK the specific point to HOVER on the inventory bar")
        elif self.step == 4:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 4: Draw box around where the TOOLTIP appears")
        elif self.step == 5:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 5: Draw box around the LOCATIONS list (where 'DropOff' is)")
        elif self.step == 6:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 6: Draw box around the ENTIRE Inventory Window (Sidebar + Items)")
        elif self.step == 7:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "STEP 7: Draw box around WARP STATUS text (Center Screen)")

    def mousePressEvent(self, event):
        if self.step in [3]:
            # Point selection steps
            point = event.pos()
            if self.step == 3:
                self.inventory_hover_point = point
                self.step = 4
                print("Hover point saved. Hiding for 5s to check tooltip...")
                self.hide()
                QTimer.singleShot(5000, self.show_overlay)
        else:
            # Box selection steps
            self.begin = event.pos()
            self.rubberBand.setGeometry(QRect(self.begin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if self.step not in [3]:
            self.rubberBand.setGeometry(QRect(self.begin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if self.step in [3]:
            return # Handled in mousePress

        self.end = event.pos()
        rect = self.rubberBand.geometry()
        self.rubberBand.hide()
        
        if self.step == 1:
            self.overview_rect = rect
            self.step = 2
            print("Overview saved. Now draw the SELECTED ITEM window.")
            self.update()
        elif self.step == 2:
            self.selected_item_rect = rect
            self.step = 3
            print("Selected Item saved. Now CLICK the inventory hover point.")
            self.update()
        elif self.step == 4:
            self.tooltip_rect = rect
            self.step = 5
            print("Tooltip saved. Now draw the LOCATIONS list region.")
            self.update()
        elif self.step == 5:
            self.dropoff_list_rect = rect
            self.step = 6
            print("Locations list saved. Now draw the ENTIRE Inventory Window.")
            self.update()
        elif self.step == 6:
            self.inventory_window_rect = rect
            self.step = 7
            print("Inventory Window saved. Hiding for 5s so you can initiate a WARP...")
            self.hide()
            QTimer.singleShot(5000, self.show_overlay)
        elif self.step == 7:
            self.warp_status_rect = rect
            self.save_config()
            self.close()

    def show_overlay(self):
        self.show()
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def save_config(self):
        # The coordinates we have (from event.pos() and rubberBand) are RELATIVE to this window.
        # Since this window covers all screens, its top-left might be at negative coordinates (e.g. -1920).
        # We need to convert these back to GLOBAL coordinates for MSS/Pillow.
        
        offset_x = self.geometry().x()
        offset_y = self.geometry().y()
        
        print(f"DEBUG: Window Offset: ({offset_x}, {offset_y})")
        
        # Helper to adjust rects
        def adjust_rect(rect):
            return [
                rect.x() + offset_x, 
                rect.y() + offset_y, 
                rect.width(), 
                rect.height()
            ]
            
        # Helper to adjust points
        def adjust_point(point):
            return [
                point.x() + offset_x,
                point.y() + offset_y
            ]

        # Save as [x, y, w, h] for rects, [x, y] for points
        config = {
            "overview_region": adjust_rect(self.overview_rect),
            "selected_item_region": adjust_rect(self.selected_item_rect),
            "inventory_hover_point": adjust_point(self.inventory_hover_point),
            "tooltip_region": adjust_rect(self.tooltip_rect),
            "dropoff_list_region": adjust_rect(self.dropoff_list_rect),
            "inventory_window_region": adjust_rect(self.inventory_window_rect),
            "warp_status_region": adjust_rect(self.warp_status_rect)
        }
        
        print(f"DEBUG: Saving Config: {config}")
        
        try:
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=4)
            print(f"\nSUCCESS! Config saved.")
            
            # Immediate Verification
            print("Verifying capture of Overview region...")
            try:
                from PIL import ImageGrab
                x, y, w, h = config["overview_region"]
                bbox = (x, y, x+w, y+h)
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
                img.save("verify_setup_overview.png")
                print("Saved 'verify_setup_overview.png'. Please check this file to ensure it captured the correct area.")
            except ImportError:
                print("Pillow not installed, skipping verification.")
            except Exception as e:
                print(f"Verification failed: {e}")

            print("You can now run 'main.py'.")
        except Exception as e:
            print(f"Error saving config: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    selector = RegionSelector()
    sys.exit(app.exec())
