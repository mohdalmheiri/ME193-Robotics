"""Prints the UNO Q's HC-SR04 readings as they arrive over MQTT (no LEGO needed).
Run:  python tests/watch_distance.py      (Ctrl+C to stop)"""
import time
import paho.mqtt.client as mqtt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sumo.py is one folder up

from sumo import BROKER, PORT, DISTANCE_TOPIC

last = [time.monotonic()]


def on_connect(c, u, f, rc, p=None):
    print(f"Connected. Waiting for messages on {DISTANCE_TOPIC} ...")
    c.subscribe(DISTANCE_TOPIC)


def on_message(c, u, msg):
    now = time.monotonic()
    print(f"{msg.payload.decode():>7} cm   ({(now - last[0]) * 1000:4.0f} ms since last)")
    last[0] = now


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sumo-watch-{int(time.time())}")
client.on_connect, client.on_message = on_connect, on_message
client.connect(BROKER, PORT, keepalive=30)
try:
    client.loop_forever()
except KeyboardInterrupt:
    pass
