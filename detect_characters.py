import os
import glob
import re
import requests

USER = os.getlogin()
EVE_LOGS = os.path.expandvars(r"C:/Users/%s/Documents/EVE/logs/Gamelogs/" % USER)
PORTRAIT_DIR = os.path.join(os.path.dirname(__file__), 'portraits')
os.makedirs(PORTRAIT_DIR, exist_ok=True)

# Map character IDs to names using log filenames and Listener lines
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

def download_portrait(char_id, char_name, size=256):
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

if __name__ == "__main__":
    char_map = get_log_character_map()
    if char_map:
        for char_id, char_name in char_map.items():
            portrait_path = download_portrait(char_id, char_name)
            if portrait_path:
                print(f"Character ID: {char_id} | Name: {char_name} | Portrait: {portrait_path}")
            else:
                print(f"Character ID: {char_id} | Name: {char_name} | Portrait: [Download failed]")
    else:
        print("No character names found in logs.")
