# Step 1: connect to the LEGO Double Motor and watch its IMU live.
# Run:  python imu_test.py      (Ctrl+C to stop)
import math
import time
import legoeducation as le

dm = le.DoubleMotor()
print("Searching for the Double Motor... (make sure it's on and blinking)")
# 20 ms between updates = 50 readings per second (default is only 10/s,
# too slow to catch a fast swing)
dm.connect(device_notification_delay=20)

if not dm.connected:
    print("Could not connect. Is it charged, turned on, and not connected to anything else?")
    exit(1)

print("Connected!")
dm.light_color(le.LEGO_COLOR_GREEN)
dm.beep()

try:
    while True:
        imu = dm.imu_device
        ax, ay, az = imu.accelerometerX, imu.accelerometerY, imu.accelerometerZ
        gx, gy, gz = imu.gyroscopeX, imu.gyroscopeY, imu.gyroscopeZ
        acc = math.sqrt(ax * ax + ay * ay + az * az)   # total acceleration
        gyro = math.sqrt(gx * gx + gy * gy + gz * gz)  # total spin speed
        print(f"acc={acc:8.0f}   gyro={gyro:8.0f}   "
              f"pitch={imu.pitch:6.1f} roll={imu.roll:6.1f} yaw={imu.yaw:6.1f}")
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    dm.disconnect()
    print("Disconnected.")
