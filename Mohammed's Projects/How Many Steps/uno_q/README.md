# 👣 Step Recorder

The UNO Q app for recording counted ankle trials. Same wiring as HW6: an MPU-6050 on the
right lower leg, near the ankle, with the board running from a power bank and controlled
from a phone on port 7000.

- `sketch/sketch.ino` is a copy of HW6's sketch. It samples the MPU-6050 at 100 Hz
  (±16 g, ±2000 °/s) and hands batches to Python. It also draws on the LED matrix.
- `python/main.py` serves the phone page and saves the trials. Each trial is one CSV,
  `Person_Activity_Tnn.csv`, in `python/recordings/`. After Stop, the board waits for
  the real step count and distance from the phone, then adds a row to
  `python/recordings/trials.csv`. Every row of a CSV is one sample:
  `time` (UTC), `ax ay az` (g), `gx gy gz` (°/s), `activity`, `person`.
- `assets/` is the phone page: name, activity, Start/Stop, the count form, and the last
  saved trials, with buttons to delete the last trial or download everything as a zip.
- The LED matrix shows the state when the phone is in a pocket: a dot = ready,
  **R** = recording, **?** = stopped, waiting for the step count.

Deploy from the ArduinoApps kit (its `step-recorder` folder is a symlink to this folder):
`python3 tools/deploy.py step-recorder`. It's the board's default app, so it starts on
power-up. To get the recordings onto the laptop, run `../data/sync_from_board.py`.

Recordings stay on the board after syncing. Don't delete them there: the trial numbers
come from the files on the board, so deleting them would reuse numbers.
