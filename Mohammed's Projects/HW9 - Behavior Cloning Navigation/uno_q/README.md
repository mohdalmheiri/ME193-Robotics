# 🧭 Nolop Navigator (board app)

The UNO Q app for HW9. It reads both sensors, counts steps and turns, runs the
navigation policy and serves the phone page, all on the board. No laptop or internet is
needed on the walk.

**Status:** only `app.yaml` exists so far. The rest is planned:

- `sketch/`: reads both MPU-6050s at 100 Hz on one I2C bus (ankle at 0x68, waist at
  0x69) and hands batches to Python, as HW7's sketch does for one sensor.
- `python/`: the step counter (starting from HW7's `step_counter.py` and
  `step_model.npz`), turn detection from the waist gyro, the policy table, saving walks,
  and the `GET /api/state` answer the page reads.
- `assets/`: the phone page (Record / Navigate / Correct), served on port 7000 by the
  `web_ui` brick.

Deploying will work like HW7: a symlink in the ArduinoApps kit points to this folder, then
`python3 tools/deploy.py <app name>`. Only one app runs at a time, so sharing port 7000
with HW7's Step Recorder is fine.
