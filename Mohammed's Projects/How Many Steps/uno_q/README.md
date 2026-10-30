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
