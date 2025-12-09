# Automated Mining Bot Design Document

## 1. Overview
This document outlines the logic flow and technical architecture for an educational automated mining bot. The bot is designed to interact with a space simulation game interface, specifically targeting asteroids in an "Overview" window.

## 2. Logic Flow

The bot operates on a continuous loop state machine with the following phases:

### Phase 1: IDLE / SCANNING
*   **Objective**: Locate a valid asteroid to mine.
*   **Action**: 
    1.  Capture a screenshot of the game's "Overview" window.
    2.  Perform OCR (Optical Character Recognition) on the text rows.
*   **Decision Logic**:
    *   **IF** text contains "Player" or "Hostile" -> **STOP/ALERT** (Safety mechanism).
    *   **IF** text contains "Asteroid" -> **SELECT** this row as the `Target`.

### Phase 2: APPROACHING
*   **Objective**: Get within mining range (< 15 km).
*   **Action**:
    1.  Move mouse to the `Target` coordinates (from Phase 1).
    2.  **Hold `Q`** key (Approach command).
    3.  **Click Left Mouse Button** on the target.
    4.  **Release `Q`** key.
*   **Monitoring**:
    *   Continuously capture the "Distance" column of the target row.
    *   Parse distance text (e.g., "24 km", "1200 m").
*   **Transition**:
    *   **IF** Distance < 15 km -> Proceed to **Phase 3**.

### Phase 3: LOCKING
*   **Objective**: Lock the target to enable weapon/mining modules.
*   **Action**:
    1.  **Hold `Ctrl`** key.
    2.  **Click Left Mouse Button** on the `Target`.
    3.  **Release `Ctrl`** key.
    4.  Wait 2.0 seconds for the game to register the lock.

### Phase 4: MINING START
*   **Objective**: Activate mining lasers and stabilize the ship.
*   **Action**:
    1.  Press **`F1`** (Activate Laser 1).
    2.  Press **`F2`** (Activate Laser 2).
    3.  Press **`Ctrl` + `Spacebar`** (Stop ship momentum/engines).

### Phase 5: MINING LOOP
*   **Objective**: Wait for the asteroid to be depleted.
*   **Action**:
    *   Monitor the "Overview" window.
*   **Transition**:
    *   **IF** the `Target` text disappears from the Overview (Asteroid depleted) -> Return to **Phase 1**.
    *   **IF** Cargo is full (Optional future state) -> Trigger Docking sequence.

---

## 3. Technical Architecture

### Dependencies
*   **Python 3.x**
*   **OpenCV (`opencv-python`)**: For image processing and finding the Overview window.
*   **Tesseract (`pytesseract`)**: For reading text (OCR) from the game UI.
*   **PyDirectInput (`pydirectinput`)**: For sending DirectX-compatible keyboard and mouse commands.
*   **PyQt6**: For the bot's control interface.

### Module Structure
1.  **`vision.py`**: Handles screen capture and OCR text analysis.
2.  **`input_controller.py`**: Wrapper for keyboard/mouse actions with failsafes.
3.  **`bot_logic.py`**: Implements the state machine described above.
4.  **`main.py`**: The GUI entry point.
5.  **`mock_game.py`**: A simulation window to test the bot without the real game.
