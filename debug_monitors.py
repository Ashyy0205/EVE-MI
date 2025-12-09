import mss
import json

def debug_monitors():
    with mss.mss() as sct:
        print("MSS Monitor Configuration:")
        for i, monitor in enumerate(sct.monitors):
            print(f"Monitor {i}: {monitor}")

    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            print("\nCurrent Config Regions:")
            print(f"Overview: {config.get('overview_region')}")
    except:
        print("No config found.")

if __name__ == "__main__":
    debug_monitors()
