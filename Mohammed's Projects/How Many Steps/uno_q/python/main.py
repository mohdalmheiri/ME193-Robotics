"""Step Recorder: records counted ankle trials for HW7, controlled from a phone.

The sketch (sketch/sketch.ino, HW6's, plus setting the sensor up again if it
restarts asleep) reads the MPU-6050 100 times a second and queues the
samples. This file runs on the board's Linux side:

- It serves the phone page (assets/) on port 7000.
- About 10 times a second it pulls every queued sample from the sketch.
- While a trial is recording, each sample becomes one row of a CSV named
  Person_Activity_Tnn.csv (e.g. Mohammed_Walk_normal_T03.csv) in
  python/recordings/. The trial number counts up per person and activity.
- After Stop, the board waits for you to type in the real step count and
  distance on the phone, then adds one row to recordings/trials.csv:
  file, person, activity, steps, distance_m, duration_s.
- It checks every sample, recording or not. If the sensor stops reading
  (all channels 0 or -1, or no samples at all), /status says so and the
  phone page shows a red banner until it reads again.
- It counts steps live, all the time: every 0.5 s the trained committee
  (step_counter.py, step_model.npz) estimates the last 2 s, and the running
  steps and distance (with their +/-) go to the LED matrix, the phone page
  and the dashboard over MQTT. Each saved trial also gets the live count from
  its Start to its Stop, in recordings/live_counts.csv, to compare with the
  real count.

A trial goes through three states:
    idle --Start--> recording --Stop--> waiting for count --Save--> idle
                                                         --Discard--> idle (file deleted)
The board won't start a new trial while one is waiting for its count, so a
recording can't be left without its step count by accident.
"""
import csv
import io
import json
import math
import os
import re
import time
import traceback
import zipfile
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from fastapi import Response

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

from step_counter import Committee, LiveCounter

logger = Logger("step-recorder")
ui = WebUI()

# ---- Settings ----------------------------------------------------------------
ACTIVITIES = [
    "Walk_slow", "Walk_normal", "Walk_fast", "Run",
    "Stand",      # standing still
    "Fidget",     # standing and shifting weight
    "LegSwing",   # sitting and swinging a leg
    "Test",       # counted test walks
    "Outdoor",    # the long walk, compared with the phone's step counter
]
NO_STEP_ACTIVITIES = ["Stand", "Fidget", "LegSwing"]  # default 0 steps and 0 m
DEFAULT_DISTANCE_M = 20      # the measured course; Outdoor has no default (it's never 20 m)
SAMPLE_RATE_HZ = 100         # the sketch samples every 10 ms
SENSOR_STALE_S = 0.5         # no good reading for this long = the sensor isn't reading
# What a failed read turns into in the sketch: -1 raw on every channel,
# divided by its scale factors (2048 LSB/g, 16.4 LSB per deg/s)
FAILED_READ = (-1 / 2048, -1 / 16.4)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
TRIALS_CSV = os.path.join(RECORDINGS_DIR, "trials.csv")
TRIAL_COLUMNS = ["file", "person", "activity", "steps", "distance_m", "duration_s"]
SAMPLE_COLUMNS = ["time", "ax", "ay", "az", "gx", "gy", "gz", "activity", "person"]  # same as HW6
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Live step counting (see step_counter.py) and the dashboard
MODEL_PATH = os.path.join(BASE_DIR, "step_model.npz")   # written by training/train_steps.py
LIVE_COUNTS_CSV = os.path.join(RECORDINGS_DIR, "live_counts.csv")
LIVE_COLUMNS = ["file", "live_steps", "live_steps_unc", "live_distance_m", "live_distance_unc"]
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "ME193/Mohammed/steps"   # format in dashboard/README.md

# ---- Trial state (one trial at a time) ----------------------------------------
mode = "idle"            # "idle", "recording" or "pending" (stopped, waiting for the count)
trial = {}               # the current trial: file, person, activity, start_time
csv_file = None
csv_writer = None
samples_saved = 0
last_counter = None      # the sketch numbers every sample; a jump means samples were lost
gap_count = 0
bad_samples = 0          # samples in the current trial with no real reading (0 or -1)
shown_on_matrix = None

# ---- Sensor health (checked all the time, not only while recording) ----------
last_good_time = time.time()   # starts as "now" so the page doesn't warn while the app starts
last_batch_time = time.time()
last_problem = None            # "zeros" or "no_answer", from the latest bad sample

# ---- Live step count ------------------------------------------------------------
live = LiveCounter(Committee(MODEL_PATH))
live_reset_time = time.time()  # the dashboard's "t" counts from here


def mqtt_connected(client, userdata, flags, reason_code, properties):
    logger.info(f"Dashboard broker: connected ({reason_code})")


# The dashboard connection runs in the background (loop_start) and reconnects
# by itself, so no internet (or a slow hotspot) never holds up recording.
dashboard = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
dashboard.on_connect = mqtt_connected
dashboard.reconnect_delay_set(min_delay=1, max_delay=30)
dashboard.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
dashboard.loop_start()


def publish_live():
    """One dashboard message (the format in dashboard/README.md), after every
    clip, i.e. twice a second. Skipped while not connected."""
    if not dashboard.is_connected():
        return
    layer1, layer2 = live.hidden
    message = {
        "t": round(time.time() - live_reset_time, 2),
        "steps": int(live.steps),
        "steps_unc": math.ceil(live.steps_unc),
        "distance_m": round(live.distance, 2),
        "distance_unc": round(live.distance_unc, 2),
        "cadence": round(live.rate, 2),
        "speed": round(live.speed, 2),
        "layer1": [round(float(v), 3) for v in layer1],   # net 1's hidden layers, after ReLU
        "layer2": [round(float(v), 3) for v in layer2],
    }
    dashboard.publish(MQTT_TOPIC, json.dumps(message))


def reset_count():
    """Back to 0 steps (the Reset button). Not during a recording, since the
    trial's live count is the difference between its Start and its Stop."""
    global live_reset_time
    if mode == "recording":
        return {"ok": False, "error": "Stop the recording first"}
    live.reset()
    live_reset_time = time.time()
    logger.info("Live count reset")
    return {"ok": True}


# ---- File names and trial numbers ---------------------------------------------
def safe_person(text):
    """Person names may only use letters, numbers and dashes. Underscores are
    turned into dashes too, because "_" separates the parts of a file name:
    Person_Activity_Tnn.csv (activities like Walk_slow contain one)."""
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", (text or "").strip()).strip("-")
    return cleaned or "anonymous"


def next_trial_number(person, activity):
    """1 + the highest trial number already on the board for this person and
    activity, so files are never overwritten. Numbers can skip (after a
    discard) but never repeat while the files stay on the board."""
    pattern = re.compile(rf"^{re.escape(person)}_{re.escape(activity)}_T(\d+)\.csv$")
    numbers = [int(m.group(1)) for f in os.listdir(RECORDINGS_DIR) if (m := pattern.match(f))]
    return max(numbers, default=0) + 1


def file_name(person, activity, number):
    return f"{person}_{activity}_T{number:02d}.csv"


# ---- trials.csv -------------------------------------------------------------------
def read_trials():
    if not os.path.exists(TRIALS_CSV):
        return []
    with open(TRIALS_CSV, newline="") as f:
        return list(csv.DictReader(f))


def write_trials(rows):
    """Rewrite trials.csv in full (used when the last row is deleted). Write
    to a temporary file first and then swap it in, so a power cut halfway
    can't leave a half-written trials.csv."""
    temp = TRIALS_CSV + ".tmp"
    with open(temp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRIAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, TRIALS_CSV)


def append_trial(row):
    new_file = not os.path.exists(TRIALS_CSV)
    with open(TRIALS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRIAL_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


# ---- live_counts.csv: the live count of each saved trial ----------------------------
# A separate file, so trials.csv keeps its columns.
def read_live_counts():
    if not os.path.exists(LIVE_COUNTS_CSV):
        return {}
    with open(LIVE_COUNTS_CSV, newline="") as f:
        return {r["file"]: r for r in csv.DictReader(f)}


def append_live_count(row):
    new_file = not os.path.exists(LIVE_COUNTS_CSV)
    with open(LIVE_COUNTS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LIVE_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def remove_live_count(file):
    """Drop a deleted trial's row (rewritten whole, via a temporary file)."""
    rows = [r for r in read_live_counts().values() if r["file"] != file]
    temp = LIVE_COUNTS_CSV + ".tmp"
    with open(temp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LIVE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, LIVE_COUNTS_CSV)


# ---- Start, stop, save, discard -------------------------------------------------
def start_trial(person, activity):
    global mode, trial, csv_file, csv_writer, samples_saved, last_counter, gap_count, bad_samples
    if mode == "recording":
        return {"ok": False, "error": "Already recording"}
    if mode == "pending":
        return {"ok": False, "error": "Save or discard the last trial first"}
    if activity not in ACTIVITIES:
        return {"ok": False, "error": f"Unknown activity {activity}"}

    person = safe_person(person)
    name = file_name(person, activity, next_trial_number(person, activity))
    csv_file = open(os.path.join(RECORDINGS_DIR, name), "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(SAMPLE_COLUMNS)

    trial = {"file": name, "person": person, "activity": activity, "start_time": time.time(),
             "live_start": live.totals()}   # the live count at Start; the trial's is Stop minus this
    samples_saved = 0
    last_counter = None
    gap_count = 0
    bad_samples = 0
    mode = "recording"
    logger.info(f"Started {name}")
    return {"ok": True, "file": name}


def stop_trial():
    global mode, csv_file, csv_writer
    if mode != "recording":
        return {"ok": False, "error": "Not recording"}
    csv_file.close()
    csv_file = csv_writer = None
    trial["live_stop"] = live.totals()
    mode = "pending"
    logger.info(f"Stopped {trial['file']}: {samples_saved} samples, waiting for the step count")
    return {"ok": True, "file": trial["file"]}


def save_trial(steps, distance_m):
    """Add the trial's row to trials.csv with the counts typed on the phone."""
    global mode
    if mode != "pending":
        return {"ok": False, "error": "No trial is waiting for a count"}
    if steps < 0 or distance_m < 0:
        return {"ok": False, "error": "Steps and distance can't be negative"}
    row = {
        "file": trial["file"],
        "person": trial["person"],
        "activity": trial["activity"],
        "steps": steps,
        "distance_m": round(distance_m, 2),
        # From the number of samples, not the clock: 100 samples = 1 s
        "duration_s": round(samples_saved / SAMPLE_RATE_HZ, 2),
    }
    append_trial(row)
    # The live count during the trial: its totals at Stop minus those at Start
    start, stop = trial["live_start"], trial["live_stop"]
    append_live_count({
        "file": trial["file"],
        "live_steps": round(stop["steps"] - start["steps"], 1),
        "live_steps_unc": round(stop["steps_unc"] - start["steps_unc"], 1),
        "live_distance_m": round(stop["distance_m"] - start["distance_m"], 2),
        "live_distance_unc": round(stop["distance_unc"] - start["distance_unc"], 2),
    })
    mode = "idle"
    logger.info(f"Saved {row}")
    return {"ok": True, "row": row}


def discard_trial():
    """Throw away a stopped trial (false start, miscount): delete its file."""
    global mode
    if mode != "pending":
        return {"ok": False, "error": "No trial is waiting for a count"}
    os.remove(os.path.join(RECORDINGS_DIR, trial["file"]))
    mode = "idle"
    logger.info(f"Discarded {trial['file']}")
    return {"ok": True, "file": trial["file"]}


def delete_last_trial():
    """Undo the last saved trial: remove its row from trials.csv and its file."""
    if mode != "idle":
        return {"ok": False, "error": "Finish the current trial first"}
    rows = read_trials()
    if not rows:
        return {"ok": False, "error": "No saved trials"}
    last = rows.pop()
    write_trials(rows)
    path = os.path.join(RECORDINGS_DIR, last["file"])
    if os.path.exists(path):
        os.remove(path)
    if last["file"] in read_live_counts():
        remove_live_count(last["file"])
    logger.info(f"Deleted trial {last['file']}")
    return {"ok": True, "row": last}


# ---- Sensor data ------------------------------------------------------------------
def sample_kind(values):
    """'ok', 'zeros' (all six exactly 0: the sensor restarted asleep, e.g. a
    loose VCC/GND wire) or 'no_answer' (all six -1 raw: the sensor didn't
    answer, e.g. a wire off). A real reading is never either: gravity is
    always there."""
    if all(v == 0 for v in values):
        return "zeros"
    acc, gyro = values[:3], values[3:]
    if all(abs(v - FAILED_READ[0]) < 1e-4 for v in acc) and all(abs(v - FAILED_READ[1]) < 1e-3 for v in gyro):
        return "no_answer"
    return "ok"


def sensor_status():
    """{"ok": True}, or {"ok": False, "problem": "zeros" / "no_answer" / "no_data"}."""
    now = time.time()
    if now - last_good_time < SENSOR_STALE_S:
        return {"ok": True}
    if now - last_batch_time > SENSOR_STALE_S:
        return {"ok": False, "problem": "no_data"}    # the sketch sent nothing at all
    return {"ok": False, "problem": last_problem}


def poll_sensor():
    """Pull every sample the sketch queued since the last call, check that
    the sensor is really reading, and feed the live step count (recording or
    not). While recording, also write each one to the trial's CSV."""
    global samples_saved, last_counter, gap_count, bad_samples, last_good_time, last_batch_time, last_problem
    was_ok = sensor_status()["ok"]
    batch = Bridge.call("get_batch")  # flat list: [counter, ax, ay, az, gx, gy, gz, counter, ...]
    if batch and len(batch) % 7 != 0:
        # A partial sample shouldn't happen (the sketch uses provide_safe), but
        # skip the batch rather than crash, as in HW6.
        logger.warning(f"Skipped a batch of {len(batch)} values (not whole samples)")
        last_counter = None
        return
    samples = [batch[i:i + 7] for i in range(0, len(batch or []), 7)]
    kinds = [sample_kind(s[1:]) for s in samples]
    if samples:
        last_batch_time = time.time()
    for kind in kinds:
        if kind == "ok":
            last_good_time = time.time()
        else:
            last_problem = kind
    # Note each change in the app's log, for working out later what happened
    is_ok = sensor_status()
    if is_ok["ok"] != was_ok:
        if is_ok["ok"]:
            logger.info("Sensor reading again")
        else:
            logger.warning(f"Sensor isn't reading: {is_ok['problem']}")

    # Live step count: every sample, recording or not. A sample that isn't a
    # real reading is marked, so the clip it's in counts nothing. Each
    # finished clip (every 0.5 s) goes to the dashboard.
    for sample, kind in zip(samples, kinds):
        if live.add(sample[1:], ok=(kind == "ok")):
            publish_live()

    if mode != "recording":
        return

    for (counter, ax, ay, az, gx, gy, gz), kind in zip(samples, kinds):
        if last_counter is not None and counter != last_counter + 1:
            gap_count += int(counter - last_counter - 1)
        last_counter = counter
        bad_samples += kind != "ok"
        # Batches arrive in bursts, so each row gets an evenly spaced time
        # (start + n x 10 ms) rather than the burst's arrival time. The time
        # is UTC with its "+00:00" marker (the board's clock runs on UTC), so
        # it can't be mistaken for local time when lining up with the phone.
        t = datetime.fromtimestamp(trial["start_time"] + samples_saved / SAMPLE_RATE_HZ, timezone.utc)
        csv_writer.writerow([t.isoformat(), ax, ay, az, gx, gy, gz, trial["activity"], trial["person"]])
        samples_saved += 1
    if samples:
        csv_file.flush()   # so a power cut loses at most the last fraction of a second


# ---- LED matrix: the live step count, and the state when the phone is in a pocket --
# Idle: the running step count in 3x5 digits. Recording: the same, with the
# top row lit across. Stopped, waiting for the count: a "?" (5x7, below).
# The count's last 3 digits fit on the 13 columns; from 1000 on, a dot in the
# bottom-right corner says there are more.
LETTERS = {
    "pending":   [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],  # ? (enter the count)
}
DIGITS_TOP_ROW = 2       # the count's digits sit in rows 2-6, below the recording bar


def draw(bits, key):
    """Send one frame (104 '0'/'1' characters, row by row) to the sketch."""
    global shown_on_matrix
    try:
        Bridge.call("draw_frame", bits)
        shown_on_matrix = key
    except Exception as e:  # the display is a nice-to-have; never crash over it
        logger.warning(f"Couldn't draw on the LED matrix: {e}")


def show_count(recording):
    """Draw the live step count (only when what's shown changes)."""
    steps = int(live.steps)
    text = str(steps)[-3:]
    key = ("count", text, recording, steps >= 1000)
    if key == shown_on_matrix:
        return
    columns = []
    for ch in text:                      # each digit 3 columns wide, 1 blank between
        columns += [[FONT[ch][r][c] == "#" for r in range(5)] for c in range(3)] + [[False] * 5]
    columns = columns[:-1]
    left = (13 - len(columns)) // 2      # centered
    rows = [["0"] * 13 for _ in range(8)]
    for c, column in enumerate(columns):
        for r, lit in enumerate(column):
            if lit:
                rows[DIGITS_TOP_ROW + r][left + c] = "1"
    if recording:
        rows[0] = ["1"] * 13
    if steps >= 1000:
        rows[7][12] = "1"
    draw("".join("".join(r) for r in rows), key)


def show_on_matrix(key):
    """Draw a letter from LETTERS (only when it changes)."""
    if key == shown_on_matrix:
        return
    rows = ["0" * 13 for _ in range(8)]
    for r, pattern in enumerate(LETTERS[key]):
        rows[r] = "0000" + pattern.replace("#", "1").replace(".", "0") + "0000"
    draw("".join(rows), key)


# ---- LED matrix: scrolling the board's address ----------------------------------------
# On a phone hotspot nobody knows the board's address in advance, so while the
# board is idle it scrolls e.g. "172.20.10.3:7000" until a phone opens the page
# (then it shows the ready dot). It scrolls again whenever the address changes.
#
# The address comes from board_address.txt in the app folder, written by
# board_setup/address_watcher.sh running on the board itself. The app can't
# look it up on its own: it runs in a container, and App Lab's HOST_IP is
# only set once, when the app starts. HOST_IP is the fallback if the watcher
# isn't installed.
ADDRESS_FILE = os.path.join(os.path.dirname(BASE_DIR), "board_address.txt")
PORT = 7000

# 3x5 pixel font (from the ip-and-temp-scroller app), plus ":" and the
# letters of "NO WIFI"
FONT = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", "###", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", "..#", "..#"],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
    ".": ["...", "...", "...", "...", ".#."], ":": ["...", ".#.", "...", ".#.", "..."],
    " ": ["...", "...", "...", "...", "..."], "N": ["#.#", "###", "###", "###", "#.#"],
    "O": ["###", "#.#", "#.#", "#.#", "###"], "W": ["#.#", "#.#", "###", "###", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "F": ["###", "#..", "###", "#..", "#.."],
}
TOP_ROW = 1              # the 5-row letters sit in rows 1-5 of the 8
scroll = {"columns": [], "position": 0}
address = None           # last address read (None = not read yet)
page_opened = False      # set by /status: a phone has the page open


def read_address():
    """The board's Wi-Fi address, or "" when it has none."""
    try:
        with open(ADDRESS_FILE) as f:
            return f.read().strip()
    except OSError:
        return os.environ.get("HOST_IP", "")


def text_columns(text):
    """Turn text into matrix columns (lists of 8 pixels, top to bottom), with
    one blank column between letters and a screen's width of space after,
    so each pass starts on an empty matrix."""
    columns = []
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for c in range(3):
            column = [0] * 8
            for r in range(5):
                column[TOP_ROW + r] = 1 if glyph[r][c] == "#" else 0
            columns.append(column)
        columns.append([0] * 8)
    return columns + [[0] * 8] * 13


def check_address():
    """Notice a new address: log it and start scrolling it."""
    global address, page_opened
    new = read_address()
    if new == address:
        return
    address = new
    page_opened = False
    text = f"{address}:{PORT}" if address else "NO WIFI"
    scroll["columns"] = text_columns(text)
    scroll["position"] = 0
    logger.info(f"Board address: open http://{address}:{PORT}" if address else "No Wi-Fi address yet")


def scroll_step():
    """Move the scrolling text one column left (called 10 times a second)."""
    columns, start = scroll["columns"], scroll["position"]
    window = [columns[(start + c) % len(columns)] for c in range(13)]
    bits = "".join(str(window[c][r]) for r in range(8) for c in range(13))
    draw(bits, "scrolling")
    scroll["position"] = (start + 1) % len(columns)


# ---- Web API for the phone page ----------------------------------------------------
def http_start(person: str, activity: str):
    return start_trial(person, activity)


def http_stop():
    return stop_trial()


def http_save(steps: int, distance_m: float):
    return save_trial(steps, distance_m)


def http_discard():
    return discard_trial()


def http_delete_last():
    return delete_last_trial()


def http_next(person: str, activity: str):
    """The file name the next trial would get (shown on the page before Start)."""
    person = safe_person(person)
    if activity not in ACTIVITIES:
        return {"file": ""}
    return {"file": file_name(person, activity, next_trial_number(person, activity))}


def http_reset_count():
    return reset_count()


def http_status():
    global page_opened
    if not page_opened:
        page_opened = True   # a phone found the board: stop scrolling the address
        logger.info("A phone opened the page")
    elapsed = time.time() - trial["start_time"] if mode == "recording" else 0
    rows = read_trials()
    live_counts = read_live_counts()
    return {
        "app": "Step Recorder",      # lets scripts check they reached this app
        "address": address,
        "mode": mode,
        "trial": {k: trial[k] for k in ("file", "person", "activity")} if trial else None,
        "elapsed": round(elapsed, 1),
        "samples_saved": samples_saved,
        "duration_s": round(samples_saved / SAMPLE_RATE_HZ, 1),
        "samples_per_sec": round(samples_saved / elapsed, 1) if elapsed > 0 else 0,
        "gap_count": gap_count,
        "sensor": sensor_status(),
        "bad_samples": bad_samples,   # in the current (or just stopped) trial
        "activities": ACTIVITIES,
        "no_step_activities": NO_STEP_ACTIVITIES,
        "default_distance_m": DEFAULT_DISTANCE_M,
        "trial_count": len(rows),
        # newest first, each with its live count if it has one (live_counts.csv)
        "recent_trials": [dict(r, live_steps=live_counts.get(r["file"], {}).get("live_steps", ""))
                          for r in rows[-5:][::-1]],
        "live": {
            "steps": round(live.steps, 1), "steps_unc": round(live.steps_unc, 1),
            "distance_m": round(live.distance, 1), "distance_unc": round(live.distance_unc, 1),
            "cadence": round(live.rate, 2), "speed": round(live.speed, 2),
            "dashboard": dashboard.is_connected(),
        },
    }


def http_download():
    """Every recording plus trials.csv, as one zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(RECORDINGS_DIR)):
            if name.endswith(".csv"):
                zf.write(os.path.join(RECORDINGS_DIR, name), arcname=name)
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=step_recordings.zip"})


ui.expose_api("GET", "/start", http_start)
ui.expose_api("GET", "/stop", http_stop)
ui.expose_api("GET", "/save", http_save)
ui.expose_api("GET", "/discard", http_discard)
ui.expose_api("GET", "/delete_last", http_delete_last)
ui.expose_api("GET", "/next", http_next)
ui.expose_api("GET", "/status", http_status)
ui.expose_api("GET", "/reset_count", http_reset_count)
ui.expose_api("GET", "/download", http_download)


def loop():
    try:
        check_address()
        # Idle and no phone connected yet: scroll the address. Otherwise show
        # the live step count, or "?" while a trial waits for its count (a
        # trial always wins over the address).
        if mode == "idle" and not page_opened:
            scroll_step()
        elif mode == "pending":
            show_on_matrix("pending")
        else:
            show_count(recording=(mode == "recording"))
        poll_sensor()
    except Exception:
        # On a power bank nobody would restart a crashed app, so log and carry on.
        logger.error(f"Error in loop, continuing:\n{traceback.format_exc()}")
    time.sleep(0.1)  # 10 polls a second -> about 10 samples per batch


App.run(user_loop=loop)
