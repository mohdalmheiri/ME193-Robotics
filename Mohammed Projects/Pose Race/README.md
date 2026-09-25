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

## Assignment questions

**How is Python talking to the LEGO hardware?**
Through the `legoeducation` library, which wraps Bluetooth Low Energy (BLE).
Each hub (the Double Motor for driving, the Single Motor for the propeller) is
identified by a Connection Card (a `card_color` + `card_serial` pair) rather
than a device name, since the same physical hub can be reused across
projects. Once `device.connect()` succeeds, `motor_run(speed=...)` /
`motor_stop()` calls are sent over BLE to that specific hub.

**Is it synchronous or asynchronous?**
Both, in different parts of the pipeline. The camera/pose loop is
synchronous: each frame is read, converted, and run through
`landmarker.detect_for_video()` one at a time, in order, using a running
timestamp. But the motor commands are sent with `blocking=False`
("fire-and-forget"), so the BLE write doesn't stall the loop while it waits
for the hub to acknowledge it — this keeps the video feed responsive even if
a BLE command takes a moment to land. A `SEND_THRESHOLD` also avoids spamming
BLE writes for tiny speed changes.

**How did you train it, and what are its limitations?**
We didn't train a new model — `arm_control_car.py` uses MediaPipe's
pretrained `pose_landmarker_lite` model (downloaded on first run) for pose
detection, and layered our own hand-written gesture logic (`compute_speeds`)
on top of its shoulder/wrist landmark output. The gesture logic itself was
"trained" empirically: `RAISE_THRESHOLD` and `TOGETHER_DISTANCE` were tuned
by testing on the actual robot until the controls felt reliable.
Limitations: it only tracks one person (`num_poses=1`) and can misread poses
in poor lighting, at odd camera angles, or when the driver is partially out
of frame; the wrist/shoulder thresholds are tuned for roughly one body size
and camera distance, so they may need re-tuning for a very different setup.

## Notes / limitations

- If the car's hub fails to connect, the script still runs in
  camera-preview-only mode so you can debug pose detection without hardware.
- Gesture thresholds (`RAISE_THRESHOLD`, `TOGETHER_DISTANCE`) are tuned for
  our test setup and camera distance — adjust if controls feel off.
