"""UNO Q - Linux side. Asks the sketch for the HC-SR04 distance and publishes it over MQTT.

Publishes the distance in cm as plain text (e.g. "23.4"), or "-1" when nothing echoes back.
"""
import time

import paho.mqtt.client as mqtt
from arduino.app_utils import App, Bridge

BROKER = "test.mosquitto.org"
PORT = 1883
TOPIC = "ME193/Mohammed/sumo/distance"
PUBLISH_EVERY = 0.05   # seconds (20 readings per second)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id=f"sumo-unoq-{int(time.time())}")
client.connect(BROKER, PORT, keepalive=30)
client.loop_start()
print(f"Publishing HC-SR04 distance to {TOPIC}")

last_print = 0.0


def loop():
    global last_print
    start = time.time()
    try:
        cm = float(Bridge.call("read_distance"))
    except Exception as e:
        print("Bridge error:", e)
        time.sleep(0.5)
        return
    client.publish(TOPIC, f"{cm:.1f}")
    if start - last_print > 1.0:           # print once a second so the log stays readable
        print(f"distance: {cm:.1f} cm")
        last_print = start
    time.sleep(max(0.0, PUBLISH_EVERY - (time.time() - start)))


App.run(user_loop=loop)
