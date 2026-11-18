"""Nolop Navigator: the board side of HW9 (Linux side of the UNO Q).

Built in the order of uno_q/README.md:
- Step 1: the App Lab web_ui brick serves ../assets/ (the phone page) on port 7000 and will
  answer the page's API requests.
- Step 3: read the ankle sensor (sensor.py) 10 times a second and check every reading.
- Step 4 (now): count steps with Raph's counter (stride_counter.py, his 5 trained nets in
  plain numpy). Every reading, including the "not real" placeholders for lost ones, goes to
  the counter; every 0.25 s it runs the nets on the last 4 s. The log shows the steps each
  time they change, and every 10 s a summary with how long the nets took on the board.
Next: /api/state, /api/reset, /api/rows (steps 5-7). Until /api/state exists, the page's
Live mode shows its "can't reach the board" warning; Mock mode works.
"""
import os
import time
import traceback

import numpy as np
from arduino.app_utils import App, Logger
from arduino.app_bricks.web_ui import WebUI

from sensor import Sensor
from stride_counter import StrideNets, LiveStrideCounter

logger = Logger("nolop-navigator")
HERE = os.path.dirname(os.path.abspath(__file__))

ui = WebUI()            # serves ../assets/ on port 7000 (the port is set in ../app.yaml)
sensor = Sensor(logger)
counter = LiveStrideCounter(StrideNets(os.path.join(HERE, "raph_step_model.npz")))

SUMMARY_S = 10          # log a summary this often
summary = {"time": time.time(), "received": 0, "gaps": 0, "bad": 0}
run_ms = []             # how long each run of the 5 nets took since the last summary
last_steps = 0          # to log the steps only when they change


def count_readings(readings):
    """Feed the readings to the step counter, timing each call that ran the nets."""
    global last_steps
    for values, ok in readings:
        start = time.perf_counter()
        ran = counter.add(values, ok)
        if ran and ok:
            run_ms.append((time.perf_counter() - start) * 1000)
    if counter.steps != last_steps:
        last_steps = counter.steps
        t = counter.totals()
        logger.info(f"Steps {t['steps']} (± {t['steps_unc']:.1f}), {t['distance_m']:.1f} m")


def log_summary():
    """Every SUMMARY_S seconds: what arrived since the last summary, the count, and how long
    the nets took (typical and slowest; one run every 250 ms is the budget)."""
    global run_ms
    now = time.time()
    if now - summary["time"] < SUMMARY_S:
        return
    got = sensor.received - summary["received"]
    lost = sensor.gaps - summary["gaps"]
    bad = sensor.bad - summary["bad"]
    timing = (f"nets ran {len(run_ms)} times, median {np.median(run_ms):.0f} ms, slowest {max(run_ms):.0f} ms"
              if run_ms else "nets didn't run")
    logger.info(f"Sensor: {got} readings in {now - summary['time']:.1f} s, {lost} lost, {bad} bad, "
                f"status {sensor.status()} | steps {counter.steps}, {counter.distance:.1f} m | {timing}")
    summary.update(time=now, received=sensor.received, gaps=sensor.gaps, bad=sensor.bad)
    run_ms = []


def loop():
    """Runs over and over (App.run): collect the sensor's readings, count, then wait 0.1 s."""
    try:
        count_readings(sensor.poll())
        log_summary()
    except Exception:
        # On a power bank nobody would restart a crashed app, so log and carry on (as HW7)
        logger.error(f"Error in loop, continuing:\n{traceback.format_exc()}")
    time.sleep(0.1)            # 10 polls a second -> about 10 readings per batch


logger.info("Nolop Navigator started (build step 4: page + sensor + step counter)")
App.run(user_loop=loop)
