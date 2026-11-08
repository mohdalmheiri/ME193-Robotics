# main.py: the Linux side of the safe app. The UNO Q runs the whole lock by itself:
#
#   webcam (via the USB-C hub) -> hand_crop (forced 640x480, every frame
#   checked, the saved box, 128x128) -> finger_net (the trained network,
#   in numpy) -> lock_logic (the rules) -> Bridge -> sketch: latch motor
#                                                    and LED matrix
#
# The same rules run on the laptop (laptop_lock.py), from the same file.
#
# Also served on port 7000 (the web_ui brick):
#   /              a demo page: camera view, guess, state (no buttons)
#   GET  /status   the latch's state, as before
#   GET  /guesses?secret=...  the last 10 minutes of guesses, for tuning the
#        rules (protected: it would reveal the code as it is entered)
#   POST /unlock?secret=...  and  POST /lock?secret=...   emergency
#        controls from the laptop, protected by the secret word in
#        link_secret.txt (that is how the box was opened from the laptop
#        while it was locked).
#
# Files read at start-up (all next to this file):
#   safe_code.txt     the code, e.g. "3 1 4" (kept out of Git)
#   link_secret.txt   the secret word for /unlock and /lock (kept out of Git)
#   crop_config.json, hand_crop.py, finger_net.npz: copies made by
#                     prepare_board_files.py on the laptop

import os
# One processor core for the maths. By default numpy spreads every guess over
# all 4 cores, which kept the board at full load (389% CPU): more heat and,
# worse, more current from the power bank while the motor also needs it.
# (Must be set before numpy is imported.)
for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import hmac
import threading
import time
from collections import deque
from pathlib import Path

import cv2
from fastapi import Response

from arduino.app_utils import App, Bridge   # only exist on the board; laptop warnings are normal
from arduino.app_bricks.web_ui import WebUI

import hand_crop as hc
import matrix_patterns as mp
from finger_net import FingerNet
from lock_logic import LockLogic, read_code, SURE

HERE = Path(__file__).resolve().parent
CAMERA_INDEX = 0          # the webcam on the hub is /dev/video0
STATUS_EVERY_S = 0.5      # how often to ask the sketch for the latch's real state
WEB_FRAME_EVERY_S = 0.2   # how often to refresh the demo page's picture (keeps the board's work low)
CAMERA_RETRY_S = 2.0      # wait this long before trying the camera again after a problem
GUESSES_PER_S = 10        # run the network at most this often: a 1 s hold is still 10 guesses in a row,
                          # at a fraction of the work. (Every camera frame is still read, so the
                          # picture is always the newest one and never lags behind.)

cv2.setNumThreads(1)      # OpenCV: one core too

SECRET_FILE = HERE / "link_secret.txt"
SECRET = SECRET_FILE.read_text().strip() if SECRET_FILE.exists() else ""
STATES = {0: "locked", 1: "unlocked", 2: "busy"}   # the sketch's answer codes
CMD_STATUS, CMD_UNLOCK, CMD_LOCK = 0, 1, 2


# ---- The latch, through the Bridge -------------------------------------------

class BoardLatch:
    """The same unlock()/lock() as the laptop's Latch, but talking to the sketch directly."""

    def __init__(self):
        self.board_state = None       # locked / unlocked / busy, or None if the sketch doesn't answer
        self.last_check = 0.0

    def ask(self, cmd):
        try:
            self.board_state = STATES.get(Bridge.call("latch", cmd), None)
        except Exception as e:                      # sketch not running yet
            print(f"Bridge call failed: {e}")
            self.board_state = None
        return self.board_state

    def refresh(self, now):
        """Ask for the real state every STATUS_EVERY_S seconds."""
        if now - self.last_check >= STATUS_EVERY_S:
            self.last_check = now
            self.ask(CMD_STATUS)

    def unlock(self):
        print("UNLOCK")
        return self.ask(CMD_UNLOCK) in ("busy", "unlocked")   # busy = the move was accepted and started

    def lock(self):
        print("LOCK")
        return self.ask(CMD_LOCK) in ("busy", "locked")


# ---- Set-up ------------------------------------------------------------------------

net = FingerNet()
box = hc.box_from_config(hc.load_config())          # refuses a box saved for another picture size
latch = BoardLatch()
lock = LockLogic(read_code(HERE / "safe_code.txt"), latch)
print(f"Safe ready: code of {len(lock.code)} digits, box {box}")

camera = None
camera_problem = "starting"     # None when frames are fine, else a short reason (shown on the page)
camera_retry_at = 0.0
last_bits = None                # the last picture sent to the LED matrix (only send changes)
last_guess_at = 0.0             # when the network last ran
# Every guess, for tuning: (seconds since start, guess, its confidence, the chance
# it gave "5", the lock's state). 6000 guesses at 10 per second = the last 10 minutes.
guess_log = deque(maxlen=6000)
started_at = time.monotonic()
web = {"jpeg": None, "at": 0.0, "status": {}}       # what the demo page shows
web_lock = threading.Lock()                          # the web server reads it from another thread


def show_on_matrix(now):
    global last_bits
    bits = mp.to_bits(mp.pattern_for(lock, now, latch.board_state, camera_problem is None))
    if bits != last_bits:
        try:
            Bridge.notify("draw_frame", bits)
            last_bits = bits
        except Exception as e:
            print(f"matrix: {e}")


def camera_failed(reason, now):
    """Close the camera and try again later; the matrix shows "!" meanwhile."""
    global camera, camera_problem, camera_retry_at
    if camera_problem != reason:
        print(f"Camera problem: {reason}")
    camera_problem = reason
    if camera is not None:
        camera.release()
        camera = None
    camera_retry_at = now + CAMERA_RETRY_S


def update_web(frame, best, conf, now):
    """A small marked-up picture and the numbers for the demo page."""
    status = {
        "state": lock.state, "digits": len(lock.digits), "strikes": lock.strikes,
        "guess": best, "confidence": round(conf, 3), "sure": conf >= SURE,
        "latch": latch.board_state, "camera": camera_problem or "ok",
        "message": lock.message, "hold": round(lock.hold_progress(now), 2),
        "lockout_left": max(0, round(lock.lockout_until - now)) if lock.state == "LOCKOUT" else 0,
    }
    jpeg = None
    if frame is not None and now - web["at"] >= WEB_FRAME_EVERY_S:
        x, y, s = box
        view = frame.copy()
        cv2.rectangle(view, (x, y), (x + s, y + s), (80, 200, 80), 2)
        ok, buf = cv2.imencode(".jpg", cv2.resize(view, (320, 240)), [cv2.IMWRITE_JPEG_QUALITY, 70])
        jpeg = buf.tobytes() if ok else None
    with web_lock:
        web["status"] = status
        if jpeg is not None:
            web["jpeg"], web["at"] = jpeg, now


# ---- The main loop: one camera frame per call --------------------------------------

def loop():
    global camera, camera_problem, last_guess_at
    now = time.monotonic()
    latch.refresh(now)
    lock.follow_board(latch.board_state)

    if camera is None:
        if now < camera_retry_at:
            show_on_matrix(now)
            update_web(None, 0, 0.0, now)
            time.sleep(0.05)
            return
        camera = hc.open_camera(CAMERA_INDEX)       # forces 640x480
        if not camera.isOpened():
            camera_failed("the webcam didn't open (unplugged?)", now)
            return

    ok, frame = camera.read()                      # waits for the next frame (about 30 per second)
    if not ok or frame is None:
        camera_failed("no picture from the webcam (unplugged?)", now)
        return
    if frame.mean() < 5:                           # black frames while the camera wakes up: skip
        return
    now = time.monotonic()
    if now - last_guess_at < 1.0 / GUESSES_PER_S:  # too soon for another guess: just keep the frame fresh
        return
    last_guess_at = now
    try:
        x = hc.frame_to_network_input(frame, box)  # checks EVERY frame is 640x480
    except hc.FrameSizeError as e:
        camera_failed(str(e), now)
        return
    if camera_problem is not None:
        print("Camera OK")
        camera_problem = None

    best, conf, probs = net.guess(x)
    guess_log.append((round(now - started_at, 2), best, round(conf, 3), round(float(probs[5]), 3), lock.state))
    lock.update(best, conf, now)
    show_on_matrix(now)
    update_web(frame, best, conf, now)


# ---- Web: demo page data, and the laptop's emergency controls ---------------------------

ui = WebUI()


def http_status():
    # "state" is the LATCH (locked / unlocked / busy), as the laptop expects;
    # "lock" holds the safe's own state for the demo page.
    with web_lock:
        return {"ok": True, "state": latch.board_state, "lock": dict(web["status"])}


def http_frame():
    with web_lock:
        jpeg = web["jpeg"]
    return Response(content=jpeg or b"", media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


def move(cmd, name, secret):
    """Laptop commands: check the secret word, then pass the move to the sketch."""
    if not SECRET or not hmac.compare_digest(secret.encode(), SECRET.encode()):
        print(f"{name} refused: wrong or missing secret")
        return {"ok": False, "error": "wrong secret"}
    state = latch.ask(cmd)
    print(f"{name} from the laptop (latch now {state})")
    return {"ok": state is not None, "state": state}


def http_guesses(secret: str = ""):
    if not SECRET or not hmac.compare_digest(secret.encode(), SECRET.encode()):
        return {"ok": False, "error": "wrong secret"}
    return {"ok": True, "columns": ["t", "guess", "confidence", "p5", "state"], "rows": list(guess_log)}


def http_unlock(secret: str = ""):
    return move(CMD_UNLOCK, "UNLOCK", secret)


def http_lock(secret: str = ""):
    return move(CMD_LOCK, "LOCK", secret)


ui.expose_api("GET", "/status", http_status)
ui.expose_api("GET", "/frame", http_frame)
ui.expose_api("GET", "/guesses", http_guesses)
ui.expose_api("POST", "/unlock", http_unlock)
ui.expose_api("POST", "/lock", http_lock)

App.run(user_loop=loop)
