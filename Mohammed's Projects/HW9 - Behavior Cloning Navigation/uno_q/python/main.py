"""Nolop Navigator: the board side of HW9 (Linux side of the UNO Q).

Built in the order of uno_q/README.md:
- Step 1: the App Lab web_ui brick serves ../assets/ (the phone page) on port 7000 and will
  answer the page's API requests.
- Step 3 (now): read the ankle sensor (sensor.py) 10 times a second, check every reading,
  and log a summary every 10 s: readings received (about 1,000 expected), lost and bad
  readings, the sensor's status and the latest reading.
Next: the step counter (step 4, stride_counter.py), then /api/state, /api/reset, /api/rows
(steps 5-7). Until /api/state exists, the page's Live mode shows its "can't reach the
board" warning; Mock mode works.
"""
import time
import traceback

from arduino.app_utils import App, Logger
from arduino.app_bricks.web_ui import WebUI

from sensor import Sensor

logger = Logger("nolop-navigator")

ui = WebUI()            # serves ../assets/ on port 7000 (the port is set in ../app.yaml)
sensor = Sensor(logger)

SUMMARY_S = 10          # log a summary this often
summary = {"time": time.time(), "received": 0, "gaps": 0, "bad": 0}


def log_summary():
    """Every SUMMARY_S seconds: what arrived since the last summary."""
    now = time.time()
    if now - summary["time"] < SUMMARY_S:
        return
    got = sensor.received - summary["received"]
    lost = sensor.gaps - summary["gaps"]
    bad = sensor.bad - summary["bad"]
    latest = [round(v, 2) for v in sensor.last_values] if sensor.last_values else None
    logger.info(f"Sensor: {got} readings in {now - summary['time']:.1f} s, {lost} lost, {bad} bad, "
                f"status {sensor.status()}; latest ax ay az gx gy gz = {latest}")
    summary.update(time=now, received=sensor.received, gaps=sensor.gaps, bad=sensor.bad)


def loop():
    """Runs over and over (App.run): collect the sensor's readings, then wait 0.1 s."""
    try:
        sensor.poll()          # step 4 will feed these to the step counter
        log_summary()
    except Exception:
        # On a power bank nobody would restart a crashed app, so log and carry on (as HW7)
        logger.error(f"Error in loop, continuing:\n{traceback.format_exc()}")
    time.sleep(0.1)            # 10 polls a second -> about 10 readings per batch


logger.info("Nolop Navigator started (build step 3: page + sensor)")
App.run(user_loop=loop)
