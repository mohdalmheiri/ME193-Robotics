"""Measures the floor and the ring tape with the Color Sensor, then suggests
TAPE_HUE_RANGE and TAPE_MIN_SATURATION for sumo.py (and can write them in).

Run:  python tests/calibrate_tape.py      (only the Color Sensor needs to be on)
"""
import os
import re
import statistics
import time

import legoeducation as le

CARD_COLOR = le.LEGO_COLOR_ORANGE      # same connection card as sumo.py
CARD_SERIAL = "0994"
SAMPLE_S = 3.0                         # seconds of readings per spot
HUE_MARGIN = 25                        # widen the tape's measured hue range by this much on each side
SUMO_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sumo.py")


def sample(eye, label):
    input(f"\nHold the sensor over the {label} (same height as on the robot), then press Enter...")
    hues, sats = [], []
    end = time.monotonic() + SAMPLE_S
    while time.monotonic() < end:
        c = eye.sensor
        if c.hue is not None and c.saturation is not None:
            hues.append(c.hue)
            sats.append(c.saturation)
        time.sleep(0.05)
    if not hues:
        raise SystemExit("No readings came back from the Color Sensor.")
    print(f"  {label}: hue {min(hues)}-{max(hues)} (median {statistics.median(hues):.0f}), "
          f"saturation {min(sats)}-{max(sats)} (median {statistics.median(sats):.0f})")
    return hues, sats


def spots(eye, name, count):
    hues, sats = [], []
    for i in range(count):
        h, s = sample(eye, f"{name}, spot {i + 1} of {count}")
        hues += h
        sats += s
    return hues, sats


eye = le.ColorSensor()
print("Searching for the Color Sensor... (make sure it's on and blinking)")
eye.connect(card_color=CARD_COLOR, card_serial=CARD_SERIAL, device_notification_delay=50)
if not eye.connected:
    raise SystemExit("Could not connect. Is it charged, on, and not connected to another laptop?")
try:
    eye.set_color_sensor_mode(le.COLOR_SENSOR_MODE_COLOR_DETECTION)
except Exception as e:
    print("Couldn't set color mode (probably fine):", e)
print("Color Sensor connected. Measuring 3 floor spots and 3 tape spots.")

try:
    floor_h, floor_s = spots(eye, "FLOOR", 3)
    tape_h, tape_s = spots(eye, "TAPE", 3)
finally:
    eye.disconnect()

hue_lo = max(0, min(tape_h) - HUE_MARGIN)
hue_hi = min(360, max(tape_h) + HUE_MARGIN)
floor_in_hue = sum(hue_lo <= h <= hue_hi for h in floor_h) / len(floor_h)
# Saturation cutoff halfway between the most saturated floor reading and the least saturated tape reading.
min_sat = round((max(floor_s) + min(tape_s)) / 2)

print("\nResults")
print(f"  floor: hue {min(floor_h)}-{max(floor_h)}, saturation {min(floor_s)}-{max(floor_s)}")
print(f"  tape:  hue {min(tape_h)}-{max(tape_h)}, saturation {min(tape_s)}-{max(tape_s)}")
print(f"\nSuggested settings:\n  TAPE_HUE_RANGE = ({hue_lo}, {hue_hi})\n  TAPE_MIN_SATURATION = {min_sat}")

if max(floor_s) >= min(tape_s):
    print("\nWarning: some floor readings are as saturated as the tape, so saturation alone can't separate them.")
if floor_in_hue > 0:
    print(f"\nWarning: {floor_in_hue:.0%} of floor readings fall inside the suggested hue range.")
if max(floor_s) >= min(tape_s) and floor_in_hue > 0:
    print("The floor and tape overlap on both checks; try darker or more colorful tape. Not writing anything.")
    raise SystemExit(1)

if input("\nWrite these into sumo.py? [y/N] ").strip().lower() == "y":
    src = open(SUMO_PY).read()
    measured = (f"# measured: floor hue ~{min(floor_h)}-{max(floor_h)} sat ~{min(floor_s)}-{max(floor_s)}; "
                f"tape hue ~{min(tape_h)}-{max(tape_h)} sat {min(tape_s)}-{max(tape_s)} (tests/calibrate_tape.py)")
    src, n1 = re.subn(r"(?m)^# measured: .*$", lambda _: measured, src)
    src, n2 = re.subn(r"(?m)^TAPE_HUE_RANGE = \([^)]*\)", f"TAPE_HUE_RANGE = ({hue_lo}, {hue_hi})", src)
    src, n3 = re.subn(r"(?m)^TAPE_MIN_SATURATION = \d+", f"TAPE_MIN_SATURATION = {min_sat}", src)
    if (n1, n2, n3) != (1, 1, 1):
        raise SystemExit("Couldn't find the tape settings in sumo.py; set them by hand.")
    open(SUMO_PY, "w").write(src)
    print("Saved to sumo.py. TAPE_MODE needs to be \"hue\" for these to be used.")
