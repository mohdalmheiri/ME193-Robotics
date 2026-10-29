# 🏃 Gait Recorder

Wearable MPU-6050 on the Arduino UNO Q. Records labelled IMU data and guesses the
activity (standing, walking, running, biking) live.

- `sketch/sketch.ino` samples the MPU-6050 at 100 Hz (±16 g, ±2000 °/s) and hands
  batches to Python. It also draws on the LED matrix.
- `python/main.py` serves the phone page on port 7000:
  - **Record**: saves labelled CSVs to `python/recordings/` (download them as a zip).
  - **Live**: every 0.5 s, runs Model 1 and Model 2 v2 on the last 2 s and shows the most
    common of the last 3 guesses. The LED matrix shows Model 2's letter (S, W, R, B),
    so it works without the phone.
- `python/gait_model.py`, `model1_thresholds.json` and `model2_tree_v2.json` are symlinks to
  `../training/` and `../models/`, so the board uses exactly the training code and models.
  Deploying copies the real files.

Deploy from the ArduinoApps kit (its `mpu6050-check` folder is a symlink to this folder):
`python3 tools/deploy.py mpu6050-check`. It was the board's power-up app during HW6; HW7's Step Recorder is now. To switch back:
`arduino-app-cli properties set default /home/arduino/ArduinoApps/mpu6050-check` on the board.
