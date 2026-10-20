# Pose Race — Propeller Party (HW1)

Control a LEGO Education robot car with your arms, using a webcam and
MediaPipe Pose: arm gestures drive the car forward, backward and around, and
lowering both hands stops it. A separate LEGO Single Motor spins a propeller
on top the whole time, purely for style.

## How it works

1. The webcam feed goes through MediaPipe's pretrained `pose_landmarker_lite`
   model, which finds your shoulders and wrists in every frame.
2. `compute_speeds()` turns those landmarks into a left and right wheel speed:

   | Gesture | Car |
   |---|---|
   | Left hand raised | Drive forward |
   | Right hand raised | Drive backward |
   | Both hands raised | Spin left |
   | Wrists together | Spin right |
   | Both hands down | Stop |

3. The speeds are sent over Bluetooth to the Double Motor. A new command is
   only sent when the speed changes by more than `SEND_THRESHOLD`.

## Hardware

- A webcam
- LEGO Education Double Motor (the car's drivetrain)
- LEGO Education Single Motor (the propeller)
- A Connection Card for each hub

## Files

| File | What it does |
|---|---|
| `arm_control_car.py` | Main script: webcam capture, pose detection, gesture → motor mapping |
| `find_devices.py` | One-off helper: scans for nearby LEGO Bluetooth devices and prints their `card_color` / `card_serial`, so you can fill those into `arm_control_car.py` instead of guessing |
| `models/pose_landmarker_lite.task` | The MediaPipe pose model (downloaded automatically if it's missing) |

## Setup and run

1. Install the packages (from the repo root, with `.venv` active):
   ```
   pip install -r "Mohammed's Projects/requirements.txt"
   ```
2. Power on both LEGO hubs and tap each one with its own Connection Card.
3. Run `python find_devices.py` to read off the real `card_color` / `card_serial`
   for each hub.
4. Edit the constants at the top of `arm_control_car.py`:
   - `CARD_COLOR` / `CARD_SERIAL` — the car's Double Motor hub
   - `SINGLE_MOTOR_CARD_COLOR` / `SINGLE_MOTOR_CARD_SERIAL` — the propeller's Single Motor hub
5. Run it:
   ```
   python arm_control_car.py
   ```
6. Press `q` in the video window to stop and disconnect cleanly.

## Tuning and notes

- Gesture thresholds (`RAISE_THRESHOLD`, `TOGETHER_DISTANCE`) are tuned for
  our test setup and camera distance — adjust if controls feel off.
- Speeds are set by `FORWARD_SPEED`, `BACKWARD_SPEED`, `BOTH_UP_SPIN_SPEED`,
  `STEER_SPIN_SPEED` and `SINGLE_MOTOR_SPEED` at the top of
  `arm_control_car.py`.
- If the car's hub fails to connect, the script still runs in
  camera-preview-only mode so you can debug pose detection without hardware.
