"""List nearby LEGO Education Bluetooth devices, so you can read off the
exact card_color/card_serial to put into single_motor.py / arm_control_car.py
instead of guessing from the printed card.

Power on the hardware and tap it with its Connection Card (pairing mode)
before running this.
"""

import legoeducation as le

TIMEOUT_SECONDS = 5

print(f"Scanning for {TIMEOUT_SECONDS}s...")
devices = le.SingleMotor().search(timeout=TIMEOUT_SECONDS)

if not devices:
    print("No LEGO devices found. Check that the hardware is powered on, "
          "in range, and was just tapped with its Connection Card.")
else:
    print(f"Found {len(devices)} device(s):")
    for d in devices:
        name = getattr(d, "name", None) or getattr(d, "device_name", None)
        mac = getattr(d, "mac", None) or getattr(d, "device_mac", None)
        color = getattr(d, "card_color", None)
        serial = getattr(d, "card_serial", None)
        print(f"  name={name!r} mac={mac!r} card_color={color!r} card_serial={serial!r}")
        print(f"    raw: {d!r}")
