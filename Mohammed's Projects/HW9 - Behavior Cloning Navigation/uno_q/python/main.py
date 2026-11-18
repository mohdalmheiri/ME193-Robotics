"""Nolop Navigator: the board side of HW9 (Linux side of the UNO Q).

Build step 1 of uno_q/README.md: serve the phone page, nothing else yet.

The App Lab web_ui brick is a small web server: it serves everything in ../assets/ on port
7000 (so a phone on the same network opens http://<board address>:7000 and gets
assets/index.html), and lets this program answer API requests such as GET /api/state.
Later build steps add here: the sensor samples from the sketch (step 3), the step counter
(step 4, stride_counter.py), and the page's API (/api/state, /api/reset, /api/rows,
steps 5-7). Until /api/state exists, the page's Live mode shows its "can't reach the
board" warning; Mock mode works.
"""
from arduino.app_utils import App, Logger
from arduino.app_bricks.web_ui import WebUI

logger = Logger("nolop-navigator")

ui = WebUI()            # serves ../assets/ on port 7000 (the port is set in ../app.yaml)
logger.info("Nolop Navigator started (build step 1: page only)")

App.run()               # keep the app (and the web server) running
