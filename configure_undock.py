import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QRubberBand
from PyQt6.QtCore import QRect, QPoint, Qt, QSize
from PyQt6.QtGui import QPainter, QColor

class UndockSelector(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        total_rect = QRect()
        for screen in QApplication.screens():
            total_rect = total_rect.united(screen.geometry())
            
        self.setGeometry(total_rect)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        self.begin = QPoint()
        self.end = QPoint()
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        self.selection_rect = None
        
        print("Instructions:")
        print("Draw a box around the UNDOCK button (and surrounding area if you want).")
        print("Press ESC to cancel.")
        
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(20)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Draw box around UNDOCK button")

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.rubberBand.setGeometry(QRect(self.begin, QSize()))
        self.rubberBand.show()

    def mouseMoveEvent(self, event):
        self.rubberBand.setGeometry(QRect(self.begin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        self.end = event.pos()
        self.selection_rect = self.rubberBand.geometry()
        self.rubberBand.hide()
        self.save_config()
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def save_config(self):
        offset_x = self.geometry().x()
        offset_y = self.geometry().y()
        
        rect = self.selection_rect
        final_rect = [
            rect.x() + offset_x, 
            rect.y() + offset_y, 
            rect.width(), 
            rect.height()
        ]
        
        print(f"Captured Region: {final_rect}")
        
        config_path = 'config.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {}
            
        config['undock_region'] = final_rect
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
            
        print(f"Updated 'undock_region' in {config_path}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    selector = UndockSelector()
    sys.exit(app.exec())
