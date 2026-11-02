"""Sumo wrestler: main program (runs on the laptop).

Connects the Double Motor, Color Sensor and Controller over Bluetooth,
listens to the UNO Q's HC-SR04 distance over MQTT, and runs the behavior tree
20 times a second.

Run:  python sumo.py        (Ctrl+C to stop)
"""
import math
import sys
import threading
import time

import legoeducation as le
import paho.mqtt.client as mqtt

from behavior_tree import Inputs, SumoBrain
from sad_song import play_sad_song

# ---- MQTT ------------------------------------------------------------------
BROKER = "test.mosquitto.org"
PORT = 1883
DISTANCE_TOPIC = "ME193/Mohammed/sumo/distance"   # UNO Q publishes here
STATE_TOPIC = "ME193/Mohammed/sumo/state"         # we publish the active branch here

# ---- Connection card (only connect to LEGO parts paired with our card) ------
CARD_COLOR = le.LEGO_COLOR_ORANGE
CARD_SERIAL = "0994"                   # string, so the leading zero is kept

# ---- Edge detection (set these after running connect_test.py on the real tape) --
# measured: floor hue ~13-23 sat ~29-41; old tape hue ~206 sat 62-77; new tape hue ~208 sat 52-56
TAPE_MODE = "hue"                      # "color" uses LEGO's color id, "hue" uses hue/saturation
TAPE_COLORS = {le.LEGO_COLOR_BLUE, le.LEGO_COLOR_AZURE}
TAPE_HUE_RANGE = (180, 240)            # only used when TAPE_MODE = "hue"
TAPE_MIN_SATURATION = 45               # only used when TAPE_MODE = "hue"

# ---- Driving setup (flip these if the robot drives the wrong way) ------------
LEFT_SIGN = -1       # set to -1 if the left wheel spins backward when it should go forward
RIGHT_SIGN = -1      # same for the right wheel
LEVER_SIGN = -1      # set to -1 if pushing the levers forward reads negative
SWAP_LEVERS = False  # True if the left lever moves the right wheel

LOOP_HZ = 20
RESEND_S = 0.5       # resend the motor command at least this often (keep-alive)

BRANCH_LIGHT = {
    "DRIVE": le.LEGO_COLOR_GREEN,
    "EDGE": le.LEGO_COLOR_YELLOW,
    "EDGE_PUSH": le.LEGO_COLOR_PURPLE,
    "BOOST": le.LEGO_COLOR_MAGENTA,
    "OUT": le.LEGO_COLOR_RED,
    "NO_EDGE": le.LEGO_COLOR_ORANGE,
}


# ---- Latest HC-SR04 reading, updated by the MQTT thread ----------------------
_distance = {"cm": None, "t": -math.inf}
_lock = threading.Lock()


# ---- Enter key as a backup "out" button (counted by a background thread) -----
_enter_presses = [0]


def _watch_enter():
    for _ in sys.stdin:
        _enter_presses[0] += 1


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"MQTT connected ({reason_code}), listening on {DISTANCE_TOPIC}")
    client.subscribe(DISTANCE_TOPIC)


def on_message(client, userdata, msg):
    try:
        cm = float(msg.payload.decode().strip())
    except ValueError:
        return
    with _lock:
        _distance["cm"] = cm if cm > 0 else None   # -1 means "no echo"
        _distance["t"] = time.monotonic()


def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"sumo-laptop-{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_start()
    return client


# ---- Hardware helpers ------------------------------------------------------------
def connect(device, name):
    print(f"Searching for the {name}... (make sure it's on and blinking)")
    device.connect(card_color=CARD_COLOR, card_serial=CARD_SERIAL,
                   device_notification_delay=50)
    if not device.connected:
        raise SystemExit(f"Could not connect to the {name}. Is it charged, on, and not connected to anything else?")
    print(f"{name} connected!")
    return device


def ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def is_tape(c):
    if TAPE_MODE == "hue":
        return (ok(c.hue) and ok(c.saturation)
                and TAPE_HUE_RANGE[0] <= c.hue <= TAPE_HUE_RANGE[1]
                and c.saturation >= TAPE_MIN_SATURATION)
    return ok(c.color) and c.color in TAPE_COLORS


def read_inputs(joy, eye, now):
    j, c = joy.sensor, eye.sensor
    left, right = (j.rightPercent, j.leftPercent) if SWAP_LEVERS else (j.leftPercent, j.rightPercent)
    left, right = (v * LEVER_SIGN if ok(v) else v for v in (left, right))   # skip None
    with _lock:
        cm, t = _distance["cm"], _distance["t"]
    return Inputs(
        left=left if ok(left) else 0,
        right=right if ok(right) else 0,
        button=joy.button.state == le.BUTTON_STATE_PRESSED,
        on_tape=is_tape(c),
        color_ok=eye.connected and ok(c.color),
        distance_cm=cm,
        distance_age_s=now - t,
    )


def main():
    drive = connect(le.DoubleMotor(), "Double Motor")
    eye = connect(le.ColorSensor(), "Color Sensor")
    joy = connect(le.Controller(), "Controller")
    try:
        eye.set_color_sensor_mode(le.COLOR_SENSOR_MODE_COLOR_DETECTION)
    except Exception as e:
        print("Couldn't set color mode (probably fine):", e)

    client = start_mqtt()
    brain = SumoBrain()
    last_cmd, last_send, last_branch = None, 0.0, None
    last_enter_count = 0
    last_status = 0.0
    status_every = 0.25  # seconds between live status line updates
    period = 1.0 / LOOP_HZ
    threading.Thread(target=_watch_enter, daemon=True).start()
    print("\nReady! Drive with the levers. Press Enter (or the controller button) when "
          "you're out; press again to reset for the next round. Ctrl+C to quit.\n")

    try:
        while True:
            now = time.monotonic()
            inp = read_inputs(joy, eye, now)
            enter_pressed = _enter_presses[0] != last_enter_count
            last_enter_count = _enter_presses[0]
            inp.button = inp.button or enter_pressed
            d = brain.tick(inp, now)

            cmd = (d.left * LEFT_SIGN, d.right * RIGHT_SIGN)
            if cmd != last_cmd or now - last_send > RESEND_S:
                if cmd == (0, 0):
                    drive.movement_stop(blocking=False)
                else:
                    drive.movement_move_tank(cmd[0], cmd[1], blocking=False)
                last_cmd, last_send = cmd, now

            if d.branch != last_branch:
                dist = f"{inp.distance_cm:.0f} cm" if inp.distance_cm else "none"
                print()   # move off the live status line
                print(f"[{d.branch:7}] levers=({inp.left:4.0f},{inp.right:4.0f})  "
                      f"tape={inp.on_tape}  opponent={dist} ({inp.distance_age_s:.2f}s old)  "
                      f"-> wheels {d.left},{d.right}")
                try:
                    drive.light_color(BRANCH_LIGHT[d.branch], blocking=False)
                except Exception:
                    pass
                client.publish(STATE_TOPIC, d.branch)
                last_branch = d.branch

            # Live status line, overwritten in place (padded so a shorter line covers a longer one)
            if now - last_status >= status_every:
                opp = f"{inp.distance_cm:4.0f} cm" if inp.distance_cm else "none"
                status = (f"{d.branch:7} levers=({inp.left:4.0f},{inp.right:4.0f})  "
                          f"tape={str(inp.on_tape):5}  opp={opp:>7}  wheels=({d.left:4},{d.right:4})")
                print(status.ljust(80), end="\r", flush=True)
                last_status = now

            if d.play_sad_song:
                drive.movement_stop(blocking=False)
                threading.Thread(target=play_sad_song, args=(drive,), daemon=True).start()

            time.sleep(max(0.0, period - (time.monotonic() - now)))
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        try:
            drive.movement_stop()
        except Exception:
            pass
        client.loop_stop()
        for dev in (drive, eye, joy):
            try:
                dev.disconnect()
            except Exception:
                pass
        print("Disconnected.")


if __name__ == "__main__":
    main()
