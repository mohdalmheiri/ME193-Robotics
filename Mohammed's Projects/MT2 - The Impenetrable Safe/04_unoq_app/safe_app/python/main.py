# main.py: the Linux side of the safe app on the UNO Q.
#
# For now (the laptop stage) the laptop does the seeing and the code
# checking, and this program only passes its commands on to the latch:
#
#   laptop_lock.py --(web request through the USB cable)--> this program
#                  --(Bridge)--> sketch.ino --> motor
#
# It runs a small web server on port 7000 (App Lab's "web_ui" brick) with
# three addresses:
#   POST /unlock?secret=...   swing the latch open
#   POST /lock?secret=...     swing it shut
#   GET  /status              is it locked, unlocked or busy?
#
# Why a secret word: the same port is also reachable over Wi-Fi, and on
# campus anyone on the network could otherwise send "unlock". Moves are
# only done when the request carries the word in link_secret.txt, a file
# kept out of Git that exists only on the laptop and on this board.
#
# Later the camera and the network will move here too, and the laptop
# won't be needed.

import hmac
import time
from pathlib import Path

from arduino.app_utils import App, Bridge   # only exist on the board; laptop warnings are normal
from arduino.app_bricks.web_ui import WebUI

SECRET_FILE = Path(__file__).resolve().parent / "link_secret.txt"
SECRET = SECRET_FILE.read_text().strip() if SECRET_FILE.exists() else ""
if not SECRET:
    print("No link_secret.txt: every UNLOCK / LOCK request will be refused.")

STATES = {0: "locked", 1: "unlocked", 2: "busy"}   # the sketch's answer codes
CMD_STATUS, CMD_UNLOCK, CMD_LOCK = 0, 1, 2

ui = WebUI()


def ask_sketch(cmd):
    """Send one request over the Bridge; return the latch state as a word."""
    try:
        return STATES.get(Bridge.call("latch", cmd), "unknown")
    except Exception as e:                    # sketch not running, or still starting
        print(f"Bridge call failed: {e}")
        return "no sketch"


def move(cmd, name, secret):
    """Check the secret word, then pass the move on to the sketch."""
    # compare_digest takes the same time whether the word is nearly right or
    # completely wrong, so timing can't be used to guess it letter by letter.
    if not SECRET or not hmac.compare_digest(secret.encode(), SECRET.encode()):
        print(f"{name} refused: wrong or missing secret")
        return {"ok": False, "error": "wrong secret"}
    state = ask_sketch(cmd)
    print(f"{name} requested (latch was {state})")
    return {"ok": state != "no sketch", "state": state}


def http_unlock(secret: str = ""):
    return move(CMD_UNLOCK, "UNLOCK", secret)


def http_lock(secret: str = ""):
    return move(CMD_LOCK, "LOCK", secret)


def http_status():
    return {"ok": True, "state": ask_sketch(CMD_STATUS)}


ui.expose_api("POST", "/unlock", http_unlock)
ui.expose_api("POST", "/lock", http_lock)
ui.expose_api("GET", "/status", http_status)


def loop():
    # The web server runs by itself; nothing else to do here yet.
    time.sleep(1)


App.run(user_loop=loop)
