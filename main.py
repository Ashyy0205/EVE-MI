import sys
import logging
import subprocess
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTextEdit, QLabel, QStyleFactory)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt

from vision import VisionSystem
from input_controller import InputController
# from background_input import BackgroundInputController
from bot_logic import MiningBot, BotState
from setup import RegionSelector

# Setup logging to emit to GUI
class SignallingLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class BotThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.vision = VisionSystem()
        self.input_ctrl = InputController()
        # Use Background Input Controller for non-intrusive control
        # self.input_ctrl = BackgroundInputController(window_title="EVE") 
        self.bot = MiningBot(self.vision, self.input_ctrl)
        self.running = False

    def run(self):
        # Setup logging inside the thread
        logger = logging.getLogger("BotLogger")
        logger.setLevel(logging.INFO)
        handler = SignallingLogHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self.bot.start()
        self.running = True
        
        while self.running:
            self.bot.update()
            self.msleep(100) # Update loop delay

    def stop(self):
        self.running = False
        self.bot.stop()
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoMiner Bot")
        self.resize(400, 500)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Controls
        self.btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Bot")
        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn = QPushButton("Stop Bot")
        self.stop_btn.clicked.connect(self.stop_bot)
        self.stop_btn.setEnabled(False)
        
        self.dock_btn = QPushButton("Dock Now")
        self.dock_btn.clicked.connect(self.dock_now)
        self.dock_btn.setEnabled(False)
        
        self.setup_btn = QPushButton("Run Setup")
        self.setup_btn.clicked.connect(self.run_setup)
        
        self.btn_layout.addWidget(self.start_btn)
        self.btn_layout.addWidget(self.stop_btn)
        self.btn_layout.addWidget(self.dock_btn)
        self.btn_layout.addWidget(self.setup_btn)
        self.layout.addLayout(self.btn_layout)

        # Log Output
        self.log_label = QLabel("Logs:")
        self.layout.addWidget(self.log_label)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.layout.addWidget(self.log_output)

        self.bot_thread = None

    def start_bot(self):
        self.log_output.append("Starting bot thread...")
        self.bot_thread = BotThread()
        self.bot_thread.log_signal.connect(self.append_log)
        self.bot_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.dock_btn.setEnabled(True)
        
        # Minimize window to unblock game view
        self.showMinimized()

    def stop_bot(self):
        if self.bot_thread:
            self.log_output.append("Stopping bot thread...")
            self.bot_thread.stop()
            self.bot_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.dock_btn.setEnabled(False)

    def dock_now(self):
        if self.bot_thread and self.bot_thread.running:
            self.log_output.append("Manual Docking Requested...")
            self.bot_thread.bot.state = BotState.DOCKING
            self.bot_thread.bot.logger.info("User requested manual docking. Switching state to DOCKING.")

    def run_setup(self):
        self.log_output.append("Launching Setup Wizard...")
        try:
            # Run setup directly in this process
            self.setup_window = RegionSelector()
            self.setup_window.show()
            # Minimize main window
            self.showMinimized()
        except Exception as e:
            self.log_output.append(f"Failed to launch setup: {e}")

    def append_log(self, text):
        self.log_output.append(text)
        # Auto scroll
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    # Fix for High DPI issues
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    try:
        app = QApplication(sys.argv)
        
        # Force Fusion style which is always available and reliable
        if "Fusion" in QStyleFactory.keys():
            app.setStyle("Fusion")
            
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
