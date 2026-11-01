# 👣 Step Recorder

The UNO Q app for recording counted ankle trials. Same wiring as HW6: an MPU-6050 on the
right lower leg, near the ankle, with the board running from a power bank and controlled
from a phone on port 7000.

- `sketch/sketch.ino` is HW6's sketch. It samples the MPU-6050 at 100 Hz
  (±16 g, ±2000 °/s) and hands batches to Python. It also draws on the LED matrix.
  One addition: if the sensor loses power for a moment (a loose VCC or GND wire), it
  restarts asleep and reads exactly 0 on every channel. After 0.1 s of that, the sketch
  sets it up again (wake, ±16 g, ±2000 °/s), retrying every 0.5 s until it reads.
  The setup is three short I2C writes inside one 10 ms sample slot, so the sampling
  timing doesn't change.
- `python/main.py` serves the phone page and saves the trials. Each trial is one CSV,
  `Person_Activity_Tnn.csv`, in `python/recordings/`. After Stop, the board waits for
  the real step count and distance from the phone, then adds a row to
  `python/recordings/trials.csv`. Every row of a CSV is one sample:
  `time` (UTC), `ax ay az` (g), `gx gy gz` (°/s), `activity`, `person`.
- `python/step_counter.py` counts steps live, all the time: every 0.5 s it computes the
  22 training features of the last 2 s and runs the 5-net committee in
  `python/step_model.npz` (plain numpy; `training/train_steps.py` writes this copy), then
  adds rate × 0.5 s to the steps and speed × 0.5 s to the distance, with the per-pace ±.
  A half-second that holds a sample that isn't a real reading counts nothing.
  `training/check_live_math.py` checks it gives the same numbers as training.
- The live count goes to the LED matrix, the phone page (with a Reset button) and the
  dashboard: `main.py` publishes the message in `dashboard/README.md` to
  `ME193/Mohammed/steps` on `broker.hivemq.com` after every clip, in the background, so
  no internet never holds up recording. `python/requirements.txt` pins numpy and
  paho-mqtt.
- Each saved trial also gets its live count (from Start to Stop) in
  `python/recordings/live_counts.csv`: `file, live_steps, live_steps_unc,
  live_distance_m, live_distance_unc`. It's a separate file so `trials.csv` keeps its
  columns. The page shows it in the saved-trials table, never in the count form, so it
  can't sway the count you type in.
- `assets/` is the phone page: name, activity, Start/Stop, the count form, the live
  count, and the last saved trials, with buttons to delete the last trial or download
  everything as a zip.
- If the sensor stops reading (every channel 0 = it lost power; every channel −1 = it
  doesn't answer, a wire is off; or no samples at all), the page shows a red **Sensor
  isn't reading** banner at the top, recording or not, until it reads again. After a
  trial with unread samples, the count form says how many seconds and suggests
  Discard. The check runs on every sample in `main.py`, which also logs each change.
- The LED matrix shows the live step count (its last 3 digits; a dot in the bottom-right
  corner from 1000 on). While recording, the top row is lit across. **?** = stopped,
  waiting for the step count.
- While idle, the matrix scrolls the board's address (e.g. `172.20.10.2:7000`, or
  `NO WIFI`) until a phone opens the page, and again whenever the address changes. The
  address comes from `board_setup/address_watcher.sh`, a small service on the board
  itself that writes it to `board_address.txt` every time it changes. The app can't look
  it up alone: it runs in a container that only gets the address once, at start-up.

## Wi-Fi: home or phone hotspot

The board has two saved networks and joins whichever it finds, at boot or when it loses
its connection: home Wi-Fi (`Mohammed`, priority 10) and Phone 2's Personal Hotspot
(`iPhone hotspot`, priority 5), so home wins when both are around. The hotspot's real name
is `Mohammed’s iPhone` with a curly apostrophe (’), as iPhones name it; a straight `'`
would never match. The password is only in the board's network settings (a root-only
file), not in this repo.

On the hotspot, keep Phone 2's Settings → Personal Hotspot screen open while the board
starts: iPhones hide the hotspot from Wi-Fi scans otherwise. The board gets a
`172.20.10.x` address, and Phone 2 opens the page at the address on the matrix.

## Setting up a board (once)

From the ArduinoApps kit, after deploying:

```
python3 tools/deploy.py --cmd "systemctl --user enable --now /home/arduino/ArduinoApps/step-recorder/board_setup/board-address.service"
python3 tools/deploy.py --cmd 'nmcli connection add type wifi con-name "iPhone hotspot" ifname wlan0 ssid "Mohammed’s iPhone" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "<password>" connection.autoconnect-priority 5'
python3 tools/deploy.py --cmd "nmcli connection modify Mohammed connection.autoconnect-priority 10"
python3 tools/deploy.py --cmd "arduino-app-cli properties set default /home/arduino/ArduinoApps/step-recorder"
```

Check the hotspot's exact name first with
`nmcli -t -f SSID device wifi list` while it is on.

Deploy from the ArduinoApps kit (its `step-recorder` folder is a symlink to this folder):
`python3 tools/deploy.py step-recorder`. It's the board's default app, so it starts on
power-up. To get the recordings onto the laptop, run `../data/sync_from_board.py`.

Recordings stay on the board after syncing. Don't delete them there: the trial numbers
come from the files on the board, so deleting them would reuse numbers.
