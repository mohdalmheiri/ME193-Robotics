# 🏓 Ping Pong Scoreboard (UNO Q)

A physical scoreboard for the AR ping-pong game: an Arduino UNO Q app that listens
to the game's MQTT messages and shows the score on the UNO Q's 8 x 13 LED matrix.
It is separate from `game.py` and needs nothing from it except the MQTT messages.

| Topic (broker.hivemq.com) | Message | LED matrix |
| --- | --- | --- |
| `ME193/Rogers/Mohammed/game` | `0-0` (new match) | growing box + flashing "GO", then `0-0` |
| | `7-5` (after each point) | the score (scrolls if it's too wide) |
| | `11-7 WIN` | sparkles + blinking smiley, then scrolls "WIN 11-7" |
| | `9-11 LOSS` | sad face, then the score |
| | `7-0 WIN (SKUNK)` | a stripe sweeping across + 3 flashes, then "SKUNK", then the score |
| `ME193/Rogers/Mohammed` | the record, e.g. `23.0` | after 20 s with no game message: scrolls "REC 23" |

Both topics are **retained**, so the board shows the latest score even if it starts
after the game. If the Wi-Fi or the broker drops, paho reconnects by itself
and subscribes again.

Same structure as the HW4 `mqtt-led-matrix` app: `python/main.py` (MQTT + drawing,
runs on the board's Linux side) sends each frame to `sketch/sketch.ino` (draws it
on the matrix) with `Bridge.notify("draw_frame", bits)`. The sketch is unchanged
from HW4.

## Deploy to the UNO Q

The board must be on Wi-Fi with internet access (it needs to reach broker.hivemq.com).

**Option A - VS Code deploy kit** (your `~/Documents/GitHub/ArduinoApps` repo, which
has `tools/deploy.py`). `deploy.py` only deploys apps that are inside that folder,
so copy this app there first:

```bash
cp -R ~/Documents/GitHub/ME193-Robotics/"Mohammed's Projects/A Little Ping Pong/unoq_scoreboard" \
      ~/Documents/GitHub/ArduinoApps/
cd ~/Documents/GitHub/ArduinoApps
python3 tools/deploy.py unoq_scoreboard
```

(or open `unoq_scoreboard/python/main.py` in VS Code and press Cmd+Shift+B).
It stops the app if it's running, copies the files to `/home/arduino/ArduinoApps/unoq_scoreboard`,
and starts it. After changing the code, copy it again and redeploy.

**Option B - Arduino App Lab:** create a new app named `unoq_scoreboard`, then
replace its `python/main.py`, `sketch/sketch.ino` and `sketch/sketch.yaml` with the
files from this folder, and press Run.

When it starts, the matrix shows `WAIT` for a moment, then the latest retained score
(or "REC ..." if no match has been played recently). The app's log prints
`MQTT connected ...` and every message it receives. See it in the App Lab console, or
from the laptop (the running app is the Docker container whose name ends in `-main-1`):

```bash
python3 tools/deploy.py --cmd "docker logs --tail 30 \$(docker ps --format '{{.Names}}' | grep -- '-main-1\$')"
```

## Test without playing

Use the MQTT debugger in this repo, `Public stuff/Debugging/index.html` (open it in a
browser):

1. **Broker:** Host `broker.hivemq.com`, WebSocket port `8884`, Secure (wss). Connect.
2. **Publish** to topic `ME193/Rogers/Mohammed/game`, one message at a time, watching the matrix:
   `0-0`, `3-2`, `10-9`, `11-7 WIN`, `9-11 LOSS`, `7-0 WIN (SKUNK)`, `0-7 LOSS (SKUNK)`.
3. **Idle:** stop publishing for 20 s; the matrix starts scrolling "REC" with the record.
4. **Reconnect:** turn the board's Wi-Fi off and on again (or unplug the router for a
   moment); after it's back, publish another score - it shows up without restarting the app.

**Careful with the record topic** `ME193/Rogers/Mohammed`: it's the one the class reads
for your record. Don't publish test values to it with **Retain** checked, or they replace
your real record for everyone until the game publishes again (the game re-publishes the
real record every time it starts). Test messages on `.../game` are fine: the next match
overwrites them.

If the board shows nothing new: check the log for `MQTT connection refused (Not authorized)`.
The public HiveMQ broker sometimes refuses connections for a short while; the app keeps
retrying and connects on its own.
