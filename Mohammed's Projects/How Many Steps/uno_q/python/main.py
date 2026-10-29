"""Step Recorder: records counted ankle trials for HW7, controlled from a phone.

The sketch (sketch/sketch.ino, same as HW6) reads the MPU-6050 100 times a
second and queues the samples. This file runs on the board's Linux side:

- It serves the phone page (assets/) on port 7000.
- About 10 times a second it pulls every queued sample from the sketch.
- While a trial is recording, each sample becomes one row of a CSV named
  Person_Activity_Tnn.csv (e.g. Mohammed_Walk_normal_T03.csv) in
  python/recordings/. The trial number counts up per person and activity.
- After Stop, the board waits for you to type in the real step count and
  distance on the phone, then adds one row to recordings/trials.csv:
  file, person, activity, steps, distance_m, duration_s.

A trial goes through three states:
    idle --Start--> recording --Stop--> waiting for count --Save--> idle
                                                         --Discard--> idle (file deleted)
The board won't start a new trial while one is waiting for its count, so a
recording can't be left without its step count by accident.
"""
import csv
import io
import os
import re
import socket
import time
import traceback
import zipfile
from datetime import datetime, timezone

from fastapi import Response

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
TRIALS_CSV = os.path.join(RECORDINGS_DIR, "trials.csv")
TRIAL_COLUMNS = ["file", "person", "activity", "steps", "distance_m", "duration_s"]
SAMPLE_COLUMNS = ["time", "ax", "ay", "az", "gx", "gy", "gz", "activity", "person"]  # same as HW6
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# ---- Trial state (one trial at a time) ----------------------------------------
mode = "idle"            # "idle", "recording" or "pending" (stopped, waiting for the count)
trial = {}               # the current trial: file, person, activity, start_time
csv_file = None
csv_writer = None
samples_saved = 0
last_counter = None      # the sketch numbers every sample; a jump means samples were lost
gap_count = 0
shown_on_matrix = None


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


# ---- Start, stop, save, discard -------------------------------------------------
def start_trial(person, activity):
    global mode, trial, csv_file, csv_writer, samples_saved, last_counter, gap_count
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

    trial = {"file": name, "person": person, "activity": activity, "start_time": time.time()}
    samples_saved = 0
    last_counter = None
    gap_count = 0
    mode = "recording"
    logger.info(f"Started {name}")
    return {"ok": True, "file": name}


def stop_trial():
    global mode, csv_file, csv_writer
    if mode != "recording":
        return {"ok": False, "error": "Not recording"}
    csv_file.close()
    csv_file = csv_writer = None
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
    logger.info(f"Deleted trial {last['file']}")
    return {"ok": True, "row": last}


# ---- Sensor data ------------------------------------------------------------------
def poll_sensor():
    """Pull every sample the sketch queued since the last call. While
    recording, write each one to the trial's CSV; otherwise just drop them
    (the sketch's queue still has to be emptied)."""
    global samples_saved, last_counter, gap_count
    batch = Bridge.call("get_batch")  # flat list: [counter, ax, ay, az, gx, gy, gz, counter, ...]
    if not batch or mode != "recording":
        return
    if len(batch) % 7 != 0:
        # A partial sample shouldn't happen (the sketch uses provide_safe), but
        # skip the batch rather than crash, as in HW6.
        logger.warning(f"Skipped a batch of {len(batch)} values (not whole samples)")
        last_counter = None
        return

    for i in range(0, len(batch), 7):
        counter, ax, ay, az, gx, gy, gz = batch[i:i + 7]
        if last_counter is not None and counter != last_counter + 1:
            gap_count += int(counter - last_counter - 1)
        last_counter = counter
        # Batches arrive in bursts, so each row gets an evenly spaced time
        # (start + n x 10 ms) rather than the burst's arrival time. The time
        # is UTC with its "+00:00" marker (the board's clock runs on UTC), so
        # it can't be mistaken for local time when lining up with the phone.
        t = datetime.fromtimestamp(trial["start_time"] + samples_saved / SAMPLE_RATE_HZ, timezone.utc)
        csv_writer.writerow([t.isoformat(), ax, ay, az, gx, gy, gz, trial["activity"], trial["person"]])
        samples_saved += 1
    csv_file.flush()   # so a power cut loses at most the last fraction of a second


# ---- LED matrix: shows the state when the phone is in a pocket ---------------------
# 5x7 letters drawn in the middle of the 8x13 matrix.
LETTERS = {
    "idle":      [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],  # one dot: ready
    "recording": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],  # R
    "pending":   [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],  # ? (enter the count)
}


def show_on_matrix(key):
    global shown_on_matrix
    if key == shown_on_matrix:
        return
    rows = ["0" * 13 for _ in range(8)]
    for r, pattern in enumerate(LETTERS[key]):
        rows[r] = "0000" + pattern.replace("#", "1").replace(".", "0") + "0000"
    try:
        Bridge.call("draw_frame", "".join(rows))
        shown_on_matrix = key
    except Exception as e:  # the display is a nice-to-have; never crash over it
        logger.warning(f"Couldn't draw on the LED matrix: {e}")


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


def http_status():
    elapsed = time.time() - trial["start_time"] if mode == "recording" else 0
    rows = read_trials()
    return {
        "app": "Step Recorder",      # lets scripts check they reached this app
        "mode": mode,
        "trial": {k: trial[k] for k in ("file", "person", "activity")} if trial else None,
        "elapsed": round(elapsed, 1),
        "samples_saved": samples_saved,
        "duration_s": round(samples_saved / SAMPLE_RATE_HZ, 1),
        "samples_per_sec": round(samples_saved / elapsed, 1) if elapsed > 0 else 0,
        "gap_count": gap_count,
        "activities": ACTIVITIES,
        "no_step_activities": NO_STEP_ACTIVITIES,
        "default_distance_m": DEFAULT_DISTANCE_M,
        "trial_count": len(rows),
        "recent_trials": rows[-5:][::-1],   # newest first
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
ui.expose_api("GET", "/download", http_download)


def get_ip():
    # The app runs in a container, so ask App Lab for the board's real address
    host_ip = os.environ.get("HOST_IP")
    if host_ip:
        return host_ip
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


def loop():
    try:
        show_on_matrix(mode)
        poll_sensor()
    except Exception:
        # On a power bank nobody would restart a crashed app, so log and carry on.
        logger.error(f"Error in loop, continuing:\n{traceback.format_exc()}")
    time.sleep(0.1)  # 10 polls a second -> about 10 samples per batch


logger.info(f"Open http://{get_ip()}:7000 on your phone")
App.run(user_loop=loop)
