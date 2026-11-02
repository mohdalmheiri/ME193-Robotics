import csv
import io
import os
import socket
import time
import traceback
import zipfile
from collections import Counter, deque
from datetime import datetime

import numpy as np
from fastapi import Response

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

# gait_model.py and the two model JSONs are symlinks to training/ and models/
# in the repo; deploying copies the real files, so the board computes features
# exactly like training did.
import gait_model as gm

logger = Logger("gait-recorder")
ui = WebUI()

ACTIVITIES = ["Standing", "Walking", "Running", "Biking"]

# Where CSV recordings are saved on the board, next to this file.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# --- Recording state (one recording active at a time) ---
recording = False
person = ""
activity = ACTIVITIES[0]
csv_file = None
csv_writer = None
samples_saved = 0
start_time = None
last_counter = None
gap_count = 0

# --- Live mode: guess the activity from the last 2 s, every 0.5 s ---
MODEL1 = gm.load_model(os.path.join(BASE_DIR, "model1_thresholds.json"))
MODEL2 = gm.load_model(os.path.join(BASE_DIR, "model2_tree_v2.json"))
SMOOTH_OVER = 3  # show the most common of the last 3 guesses

live_window = deque(maxlen=gm.WINDOW_SAMPLES)  # newest 200 samples (2 s), always kept
samples_since_guess = 0
recent = {"model1": deque(maxlen=SMOOTH_OVER), "model2": deque(maxlen=SMOOTH_OVER)}
live = {"ready": False}  # latest guesses and numbers, served at /live

# LED matrix (8 rows x 13 columns): one letter for Model 2's guess, so the
# wearable works without the phone. 5x7 letters, drawn in the middle columns.
LETTERS = {
    "Standing": [".###.", "#...#", "#....", ".###.", "....#", "#...#", ".###."],
    "Walking":  ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "Running":  ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "Biking":   ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "waiting":  [".....", ".....", ".....", ".....", ".....", ".....", "#.#.#"],  # first 2 s
}
shown_on_matrix = None


def get_ip():
    # The app container runs on its own Docker network, so its own socket's
    # address isn't the board's LAN IP; App Lab exposes the real one here.
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


def safe_name(text):
    """Keep filenames simple: letters, numbers, dash and underscore only."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in text.strip())
    return cleaned or "unknown"


def start_recording(new_person, new_activity):
    global recording, person, activity, csv_file, csv_writer
    global samples_saved, start_time, last_counter, gap_count

    if recording:
        return {"ok": False, "error": "already recording"}
    if new_activity not in ACTIVITIES:
        return {"ok": False, "error": "unknown activity"}

    person = (new_person or "").strip() or "anonymous"
    activity = new_activity

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name(person)}_{safe_name(activity)}_{timestamp}.csv"
    csv_file = open(os.path.join(RECORDINGS_DIR, filename), "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["time", "ax", "ay", "az", "gx", "gy", "gz", "activity", "person"])

    samples_saved = 0
    start_time = time.time()
    last_counter = None
    gap_count = 0
    recording = True
    logger.info(f"Started recording -> {filename}")
    return {"ok": True, "file": filename}


def stop_recording():
    global recording, csv_file, csv_writer

    if not recording:
        return {"ok": False, "error": "not recording"}

    recording = False
    csv_file.close()
    csv_file = None
    csv_writer = None
    logger.info(f"Stopped recording, {samples_saved} samples saved")
    return {"ok": True}


def most_common(guesses):
    """The most common guess; if there's a tie, the newest of the tied guesses wins."""
    counts = Counter(guesses)
    best = max(counts.values())
    for guess in reversed(guesses):
        if counts[guess] == best:
            return guess


def show_on_matrix(key):
    """Draw a letter from LETTERS on the LED matrix (only when it changes)."""
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


def guess_activity():
    """Run both models on the last 2 s, smooth, and update /live and the matrix."""
    global live
    window = np.array(live_window)
    recent["model1"].append(gm.predict_threshold_model(MODEL1, window))
    recent["model2"].append(gm.predict_tree_model(MODEL2, window))
    features = dict(zip(MODEL2["features"], gm.magnitude_features(window)))

    live = {
        "ready": True,
        "model1": {
            "guess": most_common(recent["model1"]),
            "recent": list(recent["model1"]),
            "axis": MODEL1["axis"],
            "peak": round(gm.peak_abs(window, MODEL1["axis"]), 2),         # g
            "thresholds": [round(t, 2) for t in MODEL1["thresholds"]],
            "classes": MODEL1["classes"],
        },
        "model2": {
            "guess": most_common(recent["model2"]),
            "recent": list(recent["model2"]),
            "rotation": round(features["gyro_mag_mean"], 1),    # deg/s, ~0 when still
            "bumpiness": round(features["acc_mag_std"], 2),     # g, how much the jolts vary
            "smoothness": round(features["gyro_mag_std"], 1),   # deg/s, lower = smoother
        },
    }
    show_on_matrix(live["model2"]["guess"])


def restart_live_window():
    """Throw away the last 2 s (after a gap they'd join two separate moments)."""
    global samples_since_guess
    live_window.clear()
    samples_since_guess = 0


def poll_sensor():
    """Pulls every sample the sketch has buffered since the last call, writes
    it to the current CSV (if recording), detects gaps via the counter, and
    every 0.5 s of new samples guesses the activity from the last 2 s."""
    global samples_saved, last_counter, gap_count, samples_since_guess

    batch = Bridge.call("get_batch")  # flat list: [counter, ax, ay, az, gx, gy, gz, counter, ...]
    if not batch:
        return
    if len(batch) % 7 != 0:
        # A partial sample: shouldn't happen since the sketch uses provide_safe,
        # but skip the batch rather than crash (this once stopped the app).
        logger.warning(f"Skipped a batch of {len(batch)} values (not whole samples)")
        last_counter = None
        restart_live_window()
        return

    for i in range(0, len(batch), 7):
        counter, ax, ay, az, gx, gy, gz = batch[i:i + 7]

        if last_counter is not None and counter != last_counter + 1:
            missed = int(counter - last_counter - 1)
            gap_count += missed
            logger.warning(f"Sample gap: expected counter {int(last_counter) + 1}, got {int(counter)} ({missed} missed)")
            restart_live_window()
        last_counter = counter

        live_window.append([ax, ay, az, gx, gy, gz])
        samples_since_guess += 1

        if recording:
            # The sketch samples at a fixed 100 Hz, but batches arrive in
            # bursts, so stamp each row with an evenly-spaced synthetic clock
            # instead of the batch's single arrival time (which would give
            # several rows the same timestamp).
            sample_time = datetime.fromtimestamp(start_time + samples_saved * 0.01).isoformat()
            csv_writer.writerow([sample_time, ax, ay, az, gx, gy, gz, activity, person])
            samples_saved += 1

    if recording:
        csv_file.flush()

    # Same windows as training: 200 samples, a new one every 50 samples (0.5 s)
    if len(live_window) == gm.WINDOW_SAMPLES and samples_since_guess >= gm.STEP_SAMPLES:
        samples_since_guess = 0
        guess_activity()


def http_start(person: str, activity: str):
    return start_recording(person, activity)


def http_stop():
    return stop_recording()


def http_status():
    elapsed = (time.time() - start_time) if (recording and start_time) else 0
    samples_per_sec = (samples_saved / elapsed) if elapsed > 0 else 0
    return {
        "recording": recording,
        "person": person,
        "activity": activity,
        "elapsed": round(elapsed, 1),
        "samples_saved": samples_saved,
        "samples_per_sec": round(samples_per_sec, 1),
        "gap_count": gap_count,
        "activities": ACTIVITIES,
    }


def http_download():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(RECORDINGS_DIR)):
            if fname.endswith(".csv"):
                zf.write(os.path.join(RECORDINGS_DIR, fname), arcname=fname)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=recordings.zip"},
    )


ui.expose_api("GET", "/start", http_start)
ui.expose_api("GET", "/stop", http_stop)
ui.expose_api("GET", "/status", http_status)
def http_live():
    return live


ui.expose_api("GET", "/download", http_download)
ui.expose_api("GET", "/live", http_live)


def loop():
    try:
        if shown_on_matrix is None:
            show_on_matrix("waiting")
        poll_sensor()
    except Exception:
        # On a power bank nobody would restart a crashed app, so log and carry on.
        logger.error(f"Error in loop, continuing:\n{traceback.format_exc()}")
    time.sleep(0.1)  # poll 10x/sec -> ~10 samples per fetch at 100 Hz


logger.info(f"Open http://{get_ip()}:7000 on your phone")
App.run(user_loop=loop)
