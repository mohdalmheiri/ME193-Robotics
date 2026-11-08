"""
laptop_lock.py - the finger-code safe, running on the COMPUTER first.

Run:  python laptop_lock.py            (camera 0)
      python laptop_lock.py --camera 1 (if the webcam has another number)
Keys (click the window first):
      SPACE  the "button": wake the lock up and start entering a code
      L      lock the latch again (only while UNLOCKED)
      q/Esc  quit

The camera, the crop box and the network are exactly the ones from
data collection and training (hand_crop.py, crop_config.json, model.py,
finger_cnn.pt), so this tests the real lock, not a copy of it. Later the
same LockLogic class moves to the UNO Q unchanged; only the camera window
and the motor link around it change.

The motor: when the code is right, the laptop sends UNLOCK to the UNO Q app
(safe_app/) as a web request, and the board runs the tuned latch move (see
the Latch class). It tries the USB cable first, then Wi-Fi (WIFI_HOST). The
board must be running safe_app; without it the lock still runs, but nothing
moves.

THE LOCK POLICY: the rules live in safe_app/python/lock_logic.py, shared
with the board app, so the laptop and the UNO Q always follow the same
rules (read that file's notes for them in plain words). The laptop adds
two keys: SPACE wakes the lock (like holding an open palm), and L locks it
again while open (like holding an open palm while UNLOCKED).

The digits are shown as dots, not numbers, like a PIN pad. (The current
guess IS shown, as asked, so for now someone watching the screen can read
the code. On the finished safe that line can be hidden; see SHOW_GUESS.)
"""
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "02_data_collection"))   # hand_crop.py: camera checks + photo preparation
sys.path.insert(0, str(PROJECT / "03_training"))          # model.py: the network
sys.path.insert(0, str(HERE / "safe_app" / "python"))     # lock_logic.py: the rules, shared with the board
import hand_crop as hc                        # noqa: E402
from model import CLASSES, load_trained       # noqa: E402
from lock_logic import (LockLogic, read_code, SURE, MAX_STRIKES, IDLE_TIMEOUT_S,   # noqa: E402
                        IDLE, READY, WAIT_ZERO, UNLOCKED, LOCKOUT)

# ---- Settings (change these freely) ------------------------------------------
# The rule settings (85%, 1 s, 0.5 s, 2 s palm, 3 strikes, 30 s, 15 s) are at the top of
# safe_app/python/lock_logic.py, shared with the board.
CODE_FILE = HERE / "safe_code.txt"   # the secret code, e.g. "3 1 4": 3 digits, each 1-5 (kept out of Git)
SHOW_GUESS = True         # show the network's live guess on screen (handy now; hides the code poorly)

# How the laptop reaches the UNO Q: USB first, then Wi-Fi (see the Latch class)
WIFI_HOST = "Mohammed.local"   # the board's Wi-Fi name (or its address, e.g. "10.0.0.242")
BOARD_PORT = 7000         # the safe app's web server on the board
LOCAL_PORT = 7007         # laptop end of the USB tunnel to the board's port 7000
LINK_TIMEOUT_S = 2.0      # give up on a board request after this long
POLL_S = 1.0              # ask the board for the latch's real state this often (in the background)



MODEL_PATH = PROJECT / "03_training" / "finger_cnn.pt"
SECRET_FILE = HERE / "safe_app" / "python" / "link_secret.txt"
WINDOW = "finger-code safe (SPACE start, L lock, q quit)"

# ---- The motor: a web request to the UNO Q, by USB cable or Wi-Fi ------------

class Latch:
    """Tells the UNO Q app (safe_app) to swing the latch.

    How the message travels:
      * The UNO Q app runs a small web server on the board's port 7000.
      * USB, tried first: "adb forward" (adb is the USB tool App Lab
        installed) makes the laptop's port 7007 lead through the USB cable
        to that port. So http://localhost:7007 can only mean "MY board": no
        Wi-Fi, and no address that can change. (7007, not 7000, because
        macOS uses 7000 for AirPlay.)
      * Wi-Fi, the fallback: http://Mohammed.local:7000 (WIFI_HOST). It works
        on home Wi-Fi; on campus, ".local" names often don't work and
        addresses get reused by classmates' boards.
      * Either way, each command carries the secret word from
        safe_app/python/link_secret.txt (deployed to the board too), so no
        one else can send "unlock", and a classmate's board would just
        refuse it. Over Wi-Fi the word travels unencrypted, so someone
        listening on the same open network could copy it: fine at home
        (password-protected Wi-Fi), weaker on shared networks.

    The link that last worked is tried first next time, and the other one
    only if it gets no answer. If a command reaches the board but its answer
    is lost, the retry over the other link can deliver it twice; that is
    harmless, because the sketch ignores an UNLOCK when already unlocked,
    and a LOCK when already locked.

    unlock() and lock() return True only when the board confirms it got the
    command; the lock uses that to avoid showing UNLOCKED when nothing moved.

    The real state: the screen shows only what the board itself reports
    (board_state), never what the laptop assumes. A background thread asks
    the board every POLL_S seconds, so if the board is unplugged, restarted
    or out of Wi-Fi range, the screen switches to UNKNOWN within a few
    seconds instead of showing a LOCKED that may not be true. (The thread
    runs separately so a slow or missing board never freezes the camera
    window; a lock makes sure only one request is sent at a time.)
    """
    ADB_FALLBACK = Path.home() / "Library/Arduino15/packages/arduino/tools/adb/32.0.0/adb"
    USB, WIFI = "USB", "Wi-Fi"

    def __init__(self):
        self.secret = SECRET_FILE.read_text().strip() if SECRET_FILE.exists() else ""
        if not self.secret:
            sys.exit(f"No {SECRET_FILE.name}: it is made once and deployed to the board "
                     "(see the README, 'The lock on the laptop').")
        self.adb = shutil.which("adb") or (str(self.ADB_FALLBACK) if self.ADB_FALLBACK.exists() else None)
        self.board_state = None     # what the board last said: locked / unlocked / busy / None
        self.link = None            # the link that last got an answer: "USB", "Wi-Fi" or None
        self._one_at_a_time = threading.Lock()   # the poll thread and the keys share the link

    def _tunnel(self):
        """(Re)make the USB tunnel. Needed again whenever the cable is re-plugged."""
        if self.adb is None:
            return False
        try:
            r = subprocess.run([self.adb, "forward", f"tcp:{LOCAL_PORT}", f"tcp:{BOARD_PORT}"],
                               capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0    # fails at once when no board is on USB

    def _send(self, base, method, path):
        """One web request. Returns the board's answer (a dict), or None if nothing answered."""
        url = base + path
        if method == "POST":
            url += "?" + urllib.parse.urlencode({"secret": self.secret})
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=LINK_TIMEOUT_S) as r:
                return json.loads(r.read())
        except (OSError, ValueError):   # no tunnel, no board, app not running, bad reply
            return None

    def _via(self, link, method, path):
        """Try one link. USB gets a second try after (re)making the tunnel."""
        if link == self.USB:
            base = f"http://localhost:{LOCAL_PORT}"
            answer = self._send(base, method, path)
            if answer is None and self._tunnel():
                answer = self._send(base, method, path)
            return answer
        return self._send(f"http://{WIFI_HOST}:{BOARD_PORT}", method, path)

    def _request(self, method, path):
        """Send to the board by the last working link first, then the other. True if the board agreed."""
        with self._one_at_a_time:
            was = self.link
            order = [self.USB, self.WIFI] if self.link != self.WIFI else [self.WIFI, self.USB]
            for link in order:
                answer = self._via(link, method, path)
                if answer is not None:            # the board answered (even if it said no)
                    self.link = link
                    self.board_state = answer.get("state")
                    if link != was:
                        print(f"UNO Q connected by {link}: latch is {self.board_state}")
                    if not answer.get("ok", False):
                        print(f"UNO Q ({link}) refused: {answer.get('error', answer)}")
                    return answer.get("ok", False)
            if was is not None or method == "POST":   # say it once, not every second
                print(f"UNO Q link: no answer over USB or Wi-Fi ({WIFI_HOST})")
            self.link = None
            self.board_state = None
            return False

    def start_polling(self):
        """Keep board_state fresh in the background (see the class notes)."""
        def poll():
            while True:
                self.status()
                time.sleep(POLL_S)
        threading.Thread(target=poll, daemon=True).start()   # daemon: ends when the program quits

    def status(self):
        """Ask the board whether the latch is locked. Returns True if the board answered."""
        return self._request("GET", "/status")

    def unlock(self):
        print(">>> sending UNLOCK to the UNO Q")
        return self._request("POST", "/unlock")

    def lock(self):
        print(">>> sending LOCK to the UNO Q")
        return self._request("POST", "/lock")


# ---- The network ---------------------------------------------------------------

def guess(model, frame, box):
    """One camera frame -> (best answer 0..5, its confidence 0..1). Also checks the frame is 640x480."""
    x = torch.from_numpy(hc.frame_to_network_input(frame, box)).unsqueeze(0)   # a batch of one photo
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)[0].numpy()    # six scores -> confidences adding up to 1
    best = int(probs.argmax())
    return best, float(probs[best])


# ---- The screen ------------------------------------------------------------------

GREEN, RED, ORANGE, GRAY, WHITE = (60, 190, 60), (60, 60, 220), (0, 165, 255), (150, 150, 150), (255, 255, 255)


def text(img, s, xy, scale, color, thick=2):
    cv2.putText(img, s, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw(frame, box, lock, answer, conf, now):
    """Camera picture with the box, plus a side panel: LOCKED/UNLOCKED, state, dots, guess, timers."""
    fh = frame.shape[0]
    panel = np.full((fh, 340, 3), 30, np.uint8)
    x, y, s = box
    cv2.rectangle(frame, (x, y), (x + s, y + s), GRAY, 2)

    # Big LOCKED / UNLOCKED: only what the BOARD confirms, never what the
    # laptop assumes. Without an answer from the board the arm could be
    # anywhere, so it says UNKNOWN.
    board = lock.latch.board_state if lock.latch.link else None
    if board == "locked":
        text(panel, "LOCKED", (15, 60), 1.45, RED, 4)
    elif board == "unlocked":
        text(panel, "UNLOCKED", (15, 60), 1.45, GREEN, 4)
    elif board == "busy":
        text(panel, "MOVING...", (15, 60), 1.45, ORANGE, 4)
    else:
        text(panel, "UNKNOWN", (15, 55), 1.45, ORANGE, 4)
        text(panel, "board not connected", (15, 80), 0.55, ORANGE, 1)

    # State, with a countdown where there is one
    state = lock.state
    if lock.state == LOCKOUT:
        state += f"  {max(0, lock.lockout_until - now):.0f} s"
    elif lock.state in (READY, WAIT_ZERO):
        state += f"  (reset in {max(0, IDLE_TIMEOUT_S - (now - lock.last_progress)):.0f} s)"
    text(panel, state, (15, 110), 0.65, WHITE)

    # Digits entered so far, as dots: filled = entered, hollow = still to come
    for i in range(len(lock.code)):
        center = (60 + i * 90, 160)
        if i < len(lock.digits):
            cv2.circle(panel, center, 22, WHITE, -1)
        else:
            cv2.circle(panel, center, 22, GRAY, 2)

    # Hold progress bar: fills up while a digit (or the fist) is being held
    p = lock.hold_progress(now)
    cv2.rectangle(panel, (15, 205), (325, 225), (70, 70, 70), -1)
    cv2.rectangle(panel, (15, 205), (15 + int(310 * p), 225), GREEN, -1)
    text(panel, "hold", (15, 247), 0.5, GRAY, 1)

    # The network's live guess
    if SHOW_GUESS:
        color = GREEN if conf >= SURE else ORANGE                 # orange = not sure enough to count
        text(panel, CLASSES[answer], (15, 340), 2.6, color, 6)
        text(panel, f"{conf:.0%} sure", (110, 310), 0.75, color)
        text(panel, f"needs {SURE:.0%}", (110, 340), 0.55, GRAY, 1)

    # Strikes, what the board last said, and the message (split over lines if long)
    text(panel, f"strikes: {lock.strikes} of {MAX_STRIKES}", (15, 375), 0.6, WHITE, 1)
    latch = lock.latch
    if latch.link:                                # e.g. "UNO Q by Wi-Fi: locked"
        text(panel, f"UNO Q by {latch.link}: {latch.board_state}", (15, 470), 0.5,
             GREEN if latch.link == Latch.USB else ORANGE, 1)   # orange: the weaker Wi-Fi fallback
    else:
        text(panel, "UNO Q: not connected", (15, 470), 0.5, ORANGE, 1)
    words, lines = lock.message.split(), [""]
    for w in words:
        if len(lines[-1]) + len(w) > 26:
            lines.append("")
        lines[-1] += (" " if lines[-1] else "") + w
    for i, line in enumerate(lines[:3]):
        text(panel, line, (15, 400 + i * 20), 0.5, (220, 220, 220), 1)
    return np.hstack([frame, panel])


# ---- Main loop ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="The finger-code safe, on the laptop.")
    parser.add_argument("--camera", type=int, default=0, help="camera number (default 0)")
    args = parser.parse_args()

    if not MODEL_PATH.exists():
        sys.exit("No finger_cnn.pt. Run  python train.py  in 03_training first.")
    cfg = hc.load_config()
    if cfg is None:
        sys.exit("No crop_config.json. Line up the box with capture.py first (f, then c).")
    model, info = load_trained(MODEL_PATH)
    latch = Latch()
    code = read_code(CODE_FILE)
    lock = LockLogic(code, latch)
    print(f"Loaded finger_cnn.pt (validation accuracy {info['val_accuracy']:.1%}). Code length {len(code)}.")
    # Ask the board how the latch is. Without an answer the lock still runs
    # (handy for testing the camera side), and the screen says "not connected".
    if not latch.status():
        print(f"UNO Q not reachable over USB or Wi-Fi ({WIFI_HOST}): the lock runs, "
              "but the latch won't move, and the screen says UNKNOWN.")
    latch.start_polling()                          # from now on, re-checked every POLL_S seconds

    try:
        box = hc.box_from_config(cfg)              # refuses a box saved for another picture size
        cap = hc.open_camera(args.camera)          # forces 640x480
        if not cap.isOpened():
            sys.exit(f"Camera {args.camera} did not open. Run  python ../02_data_collection/capture.py --list")
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("The camera stopped sending pictures (unplugged?).")
                break
            if frame.mean() < 5:                   # black frames while the camera wakes up: skip
                continue
            now = time.monotonic()                 # a clock that never jumps (unlike the wall clock)
            answer, conf = guess(model, frame, box)    # raises FrameSizeError if the frame isn't 640x480
            lock.follow_board(latch.board_state if latch.link else None)
            lock.update(answer, conf, now)
            cv2.imshow(WINDOW, draw(frame, box, lock, answer, conf, now))
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" "):
                lock.press_button(now)
            elif key in (ord("l"), ord("L")):
                lock.press_lock(now)
            elif key in (ord("q"), 27):            # q or Esc
                break
    except hc.FrameSizeError as e:
        sys.exit(f"STOPPED: {e}")
    finally:
        if "cap" in locals():
            cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
