"""Fake step-counter data for the dashboard, until the real wearable exists.

    python fake_publisher.py          (Ctrl+C to stop)

Publishes one JSON message twice a second to ME193/Mohammed/steps on
broker.hivemq.com, in the format written down in README.md (the UNO Q will
send the same thing later). The numbers are made up but behave like the real
thing:

- It loops through four activities: standing, walking, running, and sitting
  while swinging a leg. Steps only go up while walking or running; swinging
  a leg moves the ankle but isn't a step, which is exactly what the real net
  will have to learn.
- Distance grows by speed x time, and speed = cadence x step length.
- The +/- uncertainties grow as the walk goes on, since small errors add up.
- The 32 "neuron" values follow a different pattern for each activity, pulse
  at the step rhythm, and fade from one pattern to the next when the activity
  changes, so the dashboard looks like a real net working.
"""
import json
import math
import random
import time

import numpy as np
import paho.mqtt.client as mqtt

# ---- Settings ------------------------------------------------------------
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "ME193/Mohammed/steps"
RATE_HZ = 2                  # messages per second
NEURONS = 16                 # neurons in each hidden layer

# The activities in the order they repeat. For each one:
#   seconds: how long it lasts
#   cadence: steps per second (0 = steps don't go up)
#   step_m:  meters per step
#   swing:   how fast the leg moves (Hz), even when it isn't stepping
ACTIVITIES = [
    {"name": "standing", "seconds": 15, "cadence": 0.0, "step_m": 0.0, "swing": 0.0},
    {"name": "walking",  "seconds": 30, "cadence": 1.8, "step_m": 0.75, "swing": 0.9},
    {"name": "running",  "seconds": 20, "cadence": 2.7, "step_m": 1.1, "swing": 1.35},
    {"name": "swinging leg (sitting)", "seconds": 15, "cadence": 0.0, "step_m": 0.0, "swing": 1.2},
]

STEPS_UNC_FRACTION = 0.02    # +/- 2% of the steps counted
DISTANCE_UNC_FRACTION = 0.05 # +/- 5% of the distance (step length is the big unknown)
BLEND = 0.25                 # how fast the neurons fade to a new pattern (0..1 per message)

# Each activity gets its own fixed "pattern" for both layers: a typical value
# for every neuron. About a third of the neurons are 0 for each activity, like
# real ReLU neurons that only fire for some inputs. The seed keeps the
# patterns the same every run.
rng = np.random.default_rng(7)


def make_pattern():
    values = rng.uniform(0.1, 1.0, NEURONS)
    values[rng.random(NEURONS) < 0.35] = 0.0
    return values


for activity in ACTIVITIES:
    activity["layer1"] = make_pattern()
    activity["layer2"] = make_pattern()
# Standing is the quiet case: shrink its patterns so the dashboard looks calm.
ACTIVITIES[0]["layer1"] *= 0.3
ACTIVITIES[0]["layer2"] *= 0.3


def current_activity(t):
    """Which activity is happening at time t (seconds), looping forever."""
    cycle = sum(a["seconds"] for a in ACTIVITIES)
    t = t % cycle
    for activity in ACTIVITIES:
        if t < activity["seconds"]:
            return activity
        t -= activity["seconds"]


def neuron_values(pattern, previous, swing_hz, t, phase_offsets):
    """One layer's 16 values for this message: fade from the previous values
    toward the activity's pattern, add a pulse at the leg's rhythm (each
    neuron slightly out of step with the others) and a little noise. ReLU
    outputs are never negative, so clip at 0."""
    blended = previous + BLEND * (pattern - previous)
    pulse = 0.35 * pattern * np.sin(2 * math.pi * swing_hz * t + phase_offsets) if swing_hz else 0
    noise = rng.normal(0, 0.03, NEURONS)
    return blended, np.clip(blended + pulse + noise, 0, None)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"howmanysteps-fake-{int(time.time())}")
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_start()     # paho handles the network in the background
    print(f"Connected to {BROKER}. Publishing to {TOPIC} {RATE_HZ}x a second (Ctrl+C to stop)")

    steps = 0.0             # kept as a float so fractions of a step add up between messages
    distance = 0.0
    layer1 = np.zeros(NEURONS)  # smoothed values, before the pulse and noise
    layer2 = np.zeros(NEURONS)
    phases1 = rng.uniform(0, 2 * math.pi, NEURONS)
    phases2 = rng.uniform(0, 2 * math.pi, NEURONS)
    dt = 1 / RATE_HZ
    start = time.monotonic()
    last_name = None

    try:
        while True:
            t = time.monotonic() - start
            activity = current_activity(t)
            if activity["name"] != last_name:
                print(f"  t = {t:5.1f} s  now {activity['name']}")
                last_name = activity["name"]

            # Cadence wobbles a little around the activity's typical value, as
            # nobody walks at a perfectly steady pace.
            cadence = activity["cadence"] * random.uniform(0.95, 1.05)
            speed = cadence * activity["step_m"]
            steps += cadence * dt
            distance += speed * dt

            layer1, out1 = neuron_values(activity["layer1"], layer1, activity["swing"], t, phases1)
            layer2, out2 = neuron_values(activity["layer2"], layer2, activity["swing"], t, phases2)

            message = {
                "t": round(t, 2),
                "steps": int(steps),
                "steps_unc": math.ceil(STEPS_UNC_FRACTION * steps),
                "distance_m": round(distance, 2),
                "distance_unc": round(DISTANCE_UNC_FRACTION * distance, 2),
                "cadence": round(cadence, 2),
                "speed": round(speed, 2),
                "layer1": [round(float(v), 3) for v in out1],
                "layer2": [round(float(v), 3) for v in out2],
            }
            client.publish(TOPIC, json.dumps(message))

            # Sleep until the next half-second mark (not just 0.5 s, so the
            # time spent working doesn't slowly add up and drift)
            time.sleep(max(0, start + (math.floor(t / dt) + 1) * dt - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
