import csv
import io
import os
import socket
import time
import zipfile
from datetime import datetime

from fastapi import Response

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

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


def poll_sensor():
    """Pulls every sample the sketch has buffered since the last call, writes
    it to the current CSV (if recording), and detects gaps via the counter."""
    global samples_saved, last_counter, gap_count

    batch = Bridge.call("get_batch")  # flat list: [counter, ax, ay, az, gx, gy, gz, counter, ...]
    if not batch:
        return

    for i in range(0, len(batch), 7):
        counter, ax, ay, az, gx, gy, gz = batch[i:i + 7]

        if last_counter is not None and counter != last_counter + 1:
            missed = int(counter - last_counter - 1)
            gap_count += missed
            logger.warning(f"Sample gap: expected counter {int(last_counter) + 1}, got {int(counter)} ({missed} missed)")
        last_counter = counter

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
ui.expose_api("GET", "/download", http_download)


def loop():
    poll_sensor()
    time.sleep(0.1)  # poll 10x/sec -> ~10 samples per fetch at 100 Hz


logger.info(f"Open http://{get_ip()}:7000 on your phone")
App.run(user_loop=loop)
