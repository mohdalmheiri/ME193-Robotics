# Step 1 (Sumo): connect the Double Motor, Color Sensor and Controller,
# then stream the color sensor, IMU and joystick so we can see what everything reports.
# Run:  python connect_test.py      (Ctrl+C to stop)
import math
import time
import legoeducation as le

CARD_COLOR = le.LEGO_COLOR_ORANGE      # same connection card as sumo.py
CARD_SERIAL = "0994"


def connect(device, name):
    print(f"Searching for the {name}... (make sure it's on and blinking)")
    device.connect(card_color=CARD_COLOR, card_serial=CARD_SERIAL,
                   device_notification_delay=50)  # 20 readings per second
    if not device.connected:
        print(f"Could not connect to the {name}. Is it charged, on, and not connected to anything else?")
        raise SystemExit(1)
    print(f"{name} connected!")
    return device


drive = connect(le.DoubleMotor(), "Double Motor")
drive.light_color(le.LEGO_COLOR_GREEN)
drive.beep()

eye = connect(le.ColorSensor(), "Color Sensor")
try:
    eye.set_color_sensor_mode(le.COLOR_SENSOR_MODE_COLOR_DETECTION)
except Exception as e:
    print("Couldn't set color mode (probably fine):", e)

joy = connect(le.Controller(), "Controller")

print("\nAll connected. Hold the color sensor over the floor, then over the blue tape.")
print("Then move both joystick levers all the way forward and back, and press the button.\n")

try:
    while True:
        c = eye.sensor
        imu = drive.imu_device
        acc = math.sqrt(imu.accelerometerX ** 2 + imu.accelerometerY ** 2 + imu.accelerometerZ ** 2)
        j = joy.sensor
        print(f"color={c.color:3}  reflect={c.reflection:4}  hue={c.hue:4}  sat={c.saturation:4}  "
              f"val={c.value:4}  rgb=({c.rawRed},{c.rawGreen},{c.rawBlue})  |  "
              f"IMU acc={acc:6.0f} accX={imu.accelerometerX:6} accY={imu.accelerometerY:6}  |  "
              f"joy L={j.leftPercent:4} R={j.rightPercent:4} button={joy.button.state}")
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    for d in (drive, eye, joy):
        try:
            d.disconnect()
        except Exception:
            pass
    print("Disconnected.")
