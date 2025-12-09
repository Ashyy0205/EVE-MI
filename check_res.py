import pyautogui
import tkinter as tk

root = tk.Tk()
dpi = root.winfo_fpixels('1i')
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

print(f"--- Screen Diagnostics ---")
print(f"Tkinter Detected Resolution: {screen_width}x{screen_height}")
print(f"Tkinter Detected DPI: {dpi}")
print(f"PyAutoGUI Detected Size: {pyautogui.size()}")

try:
    import ctypes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    print(f"Native (DPI Aware) Resolution: {w}x{h}")
except:
    pass
