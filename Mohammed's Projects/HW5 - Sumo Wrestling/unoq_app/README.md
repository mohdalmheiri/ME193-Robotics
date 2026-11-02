# 📏 Sumo Distance

Measures how far away the opponent is with an HC-SR04 ultrasonic sensor on
the Arduino UNO Q, and publishes it over MQTT so the sumo robot's behavior
tree on the laptop knows when to boost.

- `sketch/sketch.ino` reads the HC-SR04 (Trig on D2, Echo on D3 through a
  voltage divider) and returns the distance in cm, or -1 if nothing echoes back.
- `python/main.py` asks the sketch for a reading 20 times a second and
  publishes it as plain text (for example `23.4`) to
  `ME193/Mohammed/sumo/distance` on `test.mosquitto.org`.

Wiring and deploy steps are in the [Sumo Wrestling README](../README.md).
