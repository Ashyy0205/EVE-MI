import sys
import logging
import subprocess
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTextEdit, QLabel, QStyleFactory, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QGridLayout, QMessageBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QPixmap
import glob
import re

import requests

from vision import VisionSystem
from input_controller import InputController
# from background_input import BackgroundInputController
from bot_logic import MiningBot, BotState
from setup import RegionSelector

# --- Character detection logic (from detect_characters.py) ---
USER = os.getlogin()
EVE_LOGS = os.path.expandvars(r"C:/Users/%s/Documents/EVE/logs/Gamelogs/" % USER)
PORTRAIT_DIR = os.path.join(os.path.dirname(__file__), 'portraits')
os.makedirs(PORTRAIT_DIR, exist_ok=True)

def get_log_character_map():
    log_files = glob.glob(os.path.join(EVE_LOGS, '*.txt'))
    char_map = {}
    for log in log_files:
        match = re.match(r'.*_(\d+)\.txt$', os.path.basename(log))
        char_id = match.group(1) if match else None
        char_name = None
        try:
            with open(log, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    listener = re.search(r'Listener: ([^\r\n]+)', line)
                    if listener:
                        char_name = listener.group(1).strip()
                        break
        except Exception:
            continue
        if char_id and char_name:
            char_map[char_id] = char_name
    return char_map

def download_portrait(char_id, char_name, size=128):
    url = f"https://images.evetech.net/characters/{char_id}/portrait?size={size}"
    out_path = os.path.join(PORTRAIT_DIR, f"{char_id}_{char_name.replace(' ', '_')}.jpg")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return out_path
    except Exception as e:
        pass
    return None

class CharacterSelectorDialog(QDialog):
    def __init__(self, char_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select EVE Character")
        self.selected_id = None
        layout = QVBoxLayout()
        self.list_widget = QListWidget()
        for char_id, char_name in char_map.items():
            portrait_path = download_portrait(char_id, char_name)
            item = QListWidgetItem(f"{char_name} (ID: {char_id})")
            if portrait_path and os.path.exists(portrait_path):
                icon = QIcon(portrait_path)
                item.setIcon(icon)
            self.list_widget.addItem(item)
        layout.addWidget(QLabel("Select the character to use for this bot session:"))
        layout.addWidget(self.list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.list_widget.itemDoubleClicked.connect(self.accept)

    def accept(self):
        current = self.list_widget.currentRow()
        if current >= 0:
            text = self.list_widget.currentItem().text()
            match = re.search(r'ID: (\d+)', text)
            if match:
                self.selected_id = match.group(1)
        super().accept()

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
    start_signal = pyqtSignal()
    stop_signal = pyqtSignal()

    def __init__(self):
        print("[DIAG] BotThread.__init__ called")
        super().__init__()
        self.vision = VisionSystem()
        self.input_ctrl = InputController()
        self.bot = MiningBot(self.vision, self.input_ctrl)
        self.running = False
        self.should_run = False
        self.start_signal.connect(self._start_bot)
        self.stop_signal.connect(self._stop_bot)
        print("[DIAG] BotThread.__init__ finished")

    def run(self):
        print("[DIAG] BotThread.run called")
        logger = logging.getLogger("BotLogger")
        logger.setLevel(logging.INFO)
        handler = SignallingLogHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        while True:
            if self.should_run:
                if not self.running:
                    self.bot.start()
                    self.running = True
                self.bot.update()
            else:
                if self.running:
                    self.bot.stop()
                    self.running = False
            self.msleep(100)

    def _start_bot(self):
        print("[DIAG] BotThread._start_bot called")
        self.should_run = True

    def _stop_bot(self):
        print("[DIAG] BotThread._stop_bot called")
        self.should_run = False

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

        self.bot_thread = BotThread()
        self.bot_thread.log_signal.connect(self.append_log)
        self.bot_thread.start()

        # Character selection
        self.char_map = get_log_character_map()
        if not self.char_map:
            self.log_output.append("No characters found in logs. Please run the setup.")
            self.setup_btn.setEnabled(True)
        else:
            self.log_output.append("Characters found in logs. Please select a character.")
            self.select_character()

    def select_character(self):
        dialog = CharacterSelectorDialog(self.char_map, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_id = dialog.selected_id
            if selected_id:
                self.log_output.append(f"Selected character ID: {selected_id}")
                # TODO: Store or use the selected character ID as needed
            else:
                self.log_output.append("No character ID was selected.")
        else:
            self.log_output.append("Character selection was canceled.")

    def start_bot(self):
        print("[DIAG] ENTER start_bot")
        self.log_output.append("Starting bot...")
        self.bot_thread.start_signal.emit()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.dock_btn.setEnabled(True)
        self.showMinimized()
        print("[DIAG] start_bot finished")

    def stop_bot(self):
        print("[DIAG] stop_bot called")
        self.log_output.append("Stopping bot...")
        self.bot_thread.stop_signal.emit()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self._enable_start_btn)
        print("[DIAG] stop_bot finished")

    def _enable_start_btn(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.dock_btn.setEnabled(False)

    def on_bot_thread_finished(self):
        self.log_output.append("Bot thread has finished.")
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
