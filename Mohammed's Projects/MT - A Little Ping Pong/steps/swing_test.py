# Step 2: detect swings with the Double Motor's IMU and give a haptic "kick".
# Run:  python swing_test.py      (Ctrl+C to stop)
import math
import time
import legoeducation as le

GYRO_THRESHOLD = 560  # gyro magnitude above this = a swing
COOLDOWN = 0.6         # seconds to wait before counting another swing

dm = le.DoubleMotor()
print("Searching for the Double Motor...")
dm.connect(device_notification_delay=20)
if not dm.connected:
    print("Could not connect.")
    exit(1)
print("Connected! Swing the paddle.")
dm.light_color(le.LEGO_COLOR_GREEN)


def haptic_kick():
    """Jerk both motors back and forth quickly so the paddle buzzes in your hand."""
    for _ in range(2):
        dm.motor_run_for_time(60, motor=le.MOTOR_BOTH, speed=100,
                              direction=le.MOTOR_MOVE_DIRECTION_CLOCKWISE)
        dm.motor_run_for_time(60, motor=le.MOTOR_BOTH, speed=100,
                              direction=le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE)


swings = 0
last_swing = 0.0
last_tuning_print = 0.0
try:
    while True:
        imu = dm.imu_device
        gyro = math.sqrt(imu.gyroscopeX ** 2 + imu.gyroscopeY ** 2 + imu.gyroscopeZ ** 2)
        now = time.time()
        if gyro > GYRO_THRESHOLD and now - last_swing > COOLDOWN:
            swings += 1
            print(f"SWING #{swings}!  (gyro={gyro:.0f})")
            dm.light_color(le.LEGO_COLOR_RED)
            haptic_kick()
            dm.light_color(le.LEGO_COLOR_GREEN)
            last_swing = time.time()
        elif 150 < gyro < GYRO_THRESHOLD and now - last_tuning_print > 0.3:
            # tuning output: how close do gentle moves get to the threshold?
            print(f"  (moving, gyro={gyro:.0f} - not a swing)")
            last_tuning_print = now
        time.sleep(0.02)
except KeyboardInterrupt:
    pass
finally:
    dm.motor_stop()
    dm.disconnect()
    print(f"Disconnected. Total swings: {swings}")
