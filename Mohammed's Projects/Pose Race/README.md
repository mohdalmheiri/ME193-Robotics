# Pose Race — Propeller Party

Control a LEGO Education robot car with your arms, using a webcam and MediaPipe
Pose. Raising the left hand drives forward, raising the right hand drives
backward, raising both hands spins left, bringing both wrists together spins
right, and lowering both hands stops the car. A separate LEGO Single Motor
spins a propeller on top continuously, purely for style.

Full write-up (build photos, demo video, reflection): see the
[Notion page](#) — *update this link*.

## Requirements

- Python 3.8+
- A webcam
- LEGO Education Double Motor (drivetrain) + a separate Single Motor (propeller)
- Packages: `opencv-python`, `mediapipe`, `legoeducation`, `certifi`

```
pip install --upgrade pip
pip install opencv-python mediapipe legoeducation certifi
```

## Files

| File | Purpose |
|---|---|
| `arm_control_car.py` | Main script — webcam capture, pose detection, gesture → motor mapping |
| `find_devices.py` | One-off helper: scans for nearby LEGO Bluetooth devices and prints their `card_color` / `card_serial`, so you can fill those into `arm_control_car.py` instead of guessing |

## Setup

1. Power on both LEGO hubs and tap each one with its own Connection Card.
2. Run `python find_devices.py` to read off the real `card_color` / `card_serial`
   for each hub.
3. Edit the constants at the top of `arm_control_car.py`:
   - `CARD_COLOR` / `CARD_SERIAL` — the car's Double Motor hub
   - `SINGLE_MOTOR_CARD_COLOR` / `SINGLE_MOTOR_CARD_SERIAL` — the propeller's Single Motor hub
4. Run it:
   ```
   python arm_control_car.py
   ```
5. Press `q` in the video window to stop and disconnect cleanly.

Answers to the assignment questions are on our group Notion site.

## Notes / limitations

- If the car's hub fails to connect, the script still runs in
  camera-preview-only mode so you can debug pose detection without hardware.
- Gesture thresholds (`RAISE_THRESHOLD`, `TOGETHER_DISTANCE`) are tuned for
  our test setup and camera distance — adjust if controls feel off.
