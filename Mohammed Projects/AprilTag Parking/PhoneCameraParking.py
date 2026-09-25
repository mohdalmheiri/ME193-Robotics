"""Phone-camera AprilTag parking (the "opposite" of AprilTagParking.py).

Here the AprilTag (36h11, id 0, see AprilTagGenerator.py / apriltag_id0.png) is
STATIONARY - taped flat to a wall, monitor, or table - instead of riding on
the car. An iPhone is mounted on the car facing forward and streams its
camera feed back to this computer; this script finds the tag in that feed
and drives the car so the tag centers itself horizontally in the frame,
exactly like AprilTagParking.py does with the roles reversed.

Getting the iPhone's camera into OpenCV (macOS Continuity Camera):
    1. iPhone: Settings > General > AirPlay & Handoff > turn on
       "Continuity Camera Webcam".
    2. Make sure the iPhone and this Mac are signed into the same Apple ID,
       with WiFi + Bluetooth on, and the iPhone is unlocked and nearby.
    3. Mount the iPhone on the car facing the direction the car will drive
       toward/away from the wall-mounted tag.
    4. The Mac's built-in camera is usually index 0, so the iPhone typically
       shows up at index 1 - but this varies. If this script opens the
       wrong camera, just try 0, 1, 2, ... for CAMERA_INDEX below; the
       preview window makes it immediately obvious which one is the phone.

Once the phone's feed shows up, the control loop is identical in spirit to
AprilTagParking.py: horizontal (x) pixel offset between the tag's centroid
and the frame's horizontal center drives a proportional (P) controller ->
motor speed, and both wheels get the same speed/direction so the car drives
straight forward/backward, not turning.

NOTE ON SIGN: the phone faces a different way on the car than the tag-tower
did, so KP's correct sign has to be re-tuned from scratch here - don't
assume it matches AprilTagParking.py's. If the car drives away from the
tag instead of toward it, flip the sign of KP (or SPRING_K).
"""

import time

import cv2
import legoeducation as le
import numpy as np

# --- Configuration ---------------------------------------------------------

# Update these to match the Connection Card plugged into the car's Double Motor
CARD_COLOR = le.LEGO_COLOR_RED
CARD_SERIAL = "0999"

CAMERA_INDEX = 1  # iPhone via Continuity Camera - try 0, 1, 2... if this opens the wrong camera
TAG_FAMILY = cv2.aruco.DICT_APRILTAG_36h11

# Proportional controller: motor_speed = KP * pixel_error, clamped to +-MAX_SPEED.
# Lower than AprilTagParking.py's defaults: the phone is riding on the car itself
# here, so driving fast whips the frame around hard and the tag loses tracking.
KP = 0.12
MAX_SPEED = 30
DEADBAND_PX = 20  # stop once the tag centroid is within this many px of center
SEND_THRESHOLD = 5  # only send a new BLE command if speed changed by more than this (%)

# "Spring loaded" bonus mode: simulate a mass-spring-damper instead of a plain
# P controller with a deadband, so the car overshoots the center and settles
# back onto it instead of just stopping dead the first time it crosses center.
SPRING_LOADED = True
SPRING_K = 0.35  # spring stiffness - how hard the "spring" pulls speed toward the center (sign matches KP)
SPRING_DAMPING = 0.2 # fraction of last frame's velocity kept each frame - closer to 1.0
                        # means the car keeps coasting through center on momentum (more
                        # back-and-forth before it settles); lower brings it to rest faster
SPRING_SETTLE_SPEED = 5  # once inside DEADBAND_PX, treat velocity below this (%) as
                          # "stopped" and snap to 0 instead of endlessly nudging around center

# Search behavior when the tag isn't visible: instead of sitting stopped and
# hoping the tag drifts back into frame on its own, sweep the car back and
# forth in place after a short grace period.
SEARCH_GRACE_S = 0.5  # hold still this long after losing the tag before searching,
                       # so a single dropped frame doesn't trigger a sweep
SEARCH_SPEED = 25  # tank-drive speed (%, per side) during each rotation burst -
                    # can run faster than a continuous spin since the car stops
                    # completely between bursts for the camera to get a sharp look
SEARCH_DIRECTION = 1  # spin this way (1 = right, -1 = left), covering a full 360
                       # instead of oscillating back and forth, since a bounded
                       # sweep can miss a tag that isn't near where it was last seen
SEARCH_BURST_S = 0.18  # seconds to rotate before pausing - short enough that a
                        # blurry mid-turn frame isn't the only chance to spot the tag
SEARCH_PAUSE_S = 0.22  # seconds to sit fully stopped so the detector gets a sharp,
                        # non-blurred frame each cycle instead of a moving one


def try_connect(device, card_color, card_serial, label):
    """Connect a LEGO device, treating any connection-time error the same as
    a failed scan instead of crashing the whole program."""
    try:
        device.connect(card_color=card_color, card_serial=card_serial)
    except Exception as exc:
        print(f"Could not connect to the {label}: {exc}")
        return False
    if not device.connected:
        print(f"Could not connect to the {label} - not found.")
        return False
    return True


def build_detector_params():
    """ArUco detector params tuned to still decode the tag when it's seen at a
    steep angle from the car's phone camera, not just head-on. The defaults are
    tuned for near-frontal views: a tag viewed at an angle projects to a skewed
    quad with less crisp bit sampling, which the defaults are quick to reject."""
    params = cv2.aruco.DetectorParameters()
    # Sample more points per cell when reading bits back out of the corrected
    # (de-skewed) tag image, so an oblique view still yields a clean read.
    params.perspectiveRemovePixelPerCell = 8
    # Tolerate a less-than-perfect quad approximation, since perspective skew
    # rounds off what should be sharp corners.
    params.polygonalApproxAccuracyRate = 0.06
    # Allow more bit errors at the tag border and rely more on the family's
    # built-in error correction - angled views are noisier along the edge.
    params.maxErroneousBitsInBorderRate = 0.5
    params.errorCorrectionRate = 0.8
    # Sub-pixel corner refinement keeps the centroid (and thus steering) stable
    # even when the tag's corners are foreshortened instead of square-on.
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return params


def find_tag_centroid(frame, detector):
    corners, ids, _ = detector.detectMarkers(frame)
    if ids is None or len(corners) == 0:
        return None, None
    tag_corners = corners[0][0]  # first detected tag, 4x2 array of (x, y) corners
    centroid = tag_corners.mean(axis=0)
    return centroid, tag_corners


def p_controller(error_px):
    """Plain proportional control with a deadband so the motors fully stop
    once the tag is centered, instead of jittering around zero error."""
    if abs(error_px) < DEADBAND_PX:
        return 0.0
    return float(np.clip(KP * error_px, -MAX_SPEED, MAX_SPEED))


def spring_controller(error_px, velocity):
    """Mass-spring-damper: treat the car like a mass on a spring anchored at
    the frame center. The spring force pulls it toward center; with light
    damping it overshoots past center before the spring pulls it back, then
    settles - instead of stopping dead the instant it crosses center."""
    if abs(error_px) < DEADBAND_PX and abs(velocity) < SPRING_SETTLE_SPEED:
        # Close to center and already slow - call it landed instead of letting
        # the spring force keep nudging it back and forth forever.
        return 0.0, 0.0
    force = SPRING_K * error_px
    velocity = float(np.clip(SPRING_DAMPING * velocity + force, -MAX_SPEED, MAX_SPEED))
    return velocity, velocity


def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {CAMERA_INDEX}. If the iPhone "
            "isn't showing up, check that Continuity Camera Webcam is on, "
            "the phone is unlocked and nearby, and try a different index."
        )

    dictionary = cv2.aruco.getPredefinedDictionary(TAG_FAMILY)
    detector = cv2.aruco.ArucoDetector(dictionary, build_detector_params())

    car = le.DoubleMotor()
    connected = try_connect(car, CARD_COLOR, CARD_SERIAL, "car")
    if not connected:
        print("Running in camera preview-only mode.")

    last_speed = 0.0
    velocity = 0.0  # only used by the spring controller
    spring_bounced = False  # whether the spring has already carried it past center once
    prev_error_sign = 0  # which side of center the tag was on last frame (-1/0/+1)
    lost_since = None  # time.time() the tag was first lost, or None while tracked
    searching = False  # whether the car is currently in the search state
    last_search_phase = None  # "move" or "pause" - last phase actually sent over BLE

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            h, w = frame.shape[:2]
            frame_center_x = w / 2
            centroid, tag_corners = find_tag_centroid(frame, detector)

            if centroid is None:
                now = time.time()
                if lost_since is None:
                    lost_since = now
                lost_elapsed = now - lost_since
                # Losing the tag means starting a fresh approach once it's found
                # again, so it gets to spring back past center once more.
                spring_bounced = False
                prev_error_sign = 0

                if lost_elapsed < SEARCH_GRACE_S:
                    # Might just be a single dropped frame - hold still briefly
                    # before committing to a search.
                    speed = 0.0
                    velocity = 0.0
                    status_text = "No tag detected - holding"
                else:
                    # Step-and-scan: alternate short rotation bursts with a full
                    # stop, so the detector gets a shot at a sharp, non-blurred
                    # frame every cycle instead of only ever seeing the tag while
                    # the car is mid-spin.
                    searching = True
                    sweep_elapsed = lost_elapsed - SEARCH_GRACE_S
                    cycle_pos = sweep_elapsed % (SEARCH_BURST_S + SEARCH_PAUSE_S)
                    search_phase = "move" if cycle_pos < SEARCH_BURST_S else "pause"
                    speed = 0.0
                    velocity = 0.0
                    status_text = f"No tag detected - searching (360, {search_phase})"

                    if connected and search_phase != last_search_phase:
                        if search_phase == "move":
                            # Drive the two sides in opposite directions to
                            # rotate in place for one short burst.
                            car.movement_move_tank(
                                speed_left=SEARCH_SPEED * SEARCH_DIRECTION,
                                speed_right=-SEARCH_SPEED * SEARCH_DIRECTION,
                                blocking=False,
                            )
                        else:
                            car.motor_stop(motor=le.MOTOR_BOTH)
                        last_search_phase = search_phase

                cv2.putText(
                    frame, status_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2,
                )
            else:
                lost_since = None
                if searching:
                    # Coming out of a search - make sure the in-place turn is
                    # stopped before handing control back to the straight-line
                    # controller (a no-op if we were already in the pause phase).
                    if connected:
                        car.motor_stop(motor=le.MOTOR_BOTH)
                    searching = False
                    last_search_phase = None
                    last_speed = 0.0

                error_px = centroid[0] - frame_center_x
                error_sign = 0 if abs(error_px) < DEADBAND_PX else (1 if error_px > 0 else -1)

                if SPRING_LOADED and not spring_bounced:
                    speed, velocity = spring_controller(error_px, velocity)
                    # Once the tag has actually crossed to the other side of
                    # center, the one allowed spring-back has happened - lock
                    # into the plain controller below so it lands instead of
                    # springing back and forth repeatedly.
                    if prev_error_sign != 0 and error_sign != 0 and error_sign != prev_error_sign:
                        spring_bounced = True
                else:
                    speed = p_controller(error_px)
                    velocity = 0.0

                if error_sign != 0:
                    prev_error_sign = error_sign

                cv2.polylines(frame, [tag_corners.astype(int)], True, (0, 0, 255), 3)
                cx, cy = int(centroid[0]), int(centroid[1])
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                cv2.putText(
                    frame, f"centroid=({cx},{cy})  speed={speed:.0f}%", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2,
                )

            cv2.line(frame, (int(frame_center_x), 0), (int(frame_center_x), h), (0, 255, 0), 1)

            if connected and not searching and abs(speed - last_speed) > SEND_THRESHOLD:
                # movement_move() drives both wheels straight forward/backward from a
                # single signed speed - see AprilTagParking.py for why per-motor
                # motor_run() calls turn this car instead of driving it straight.
                # blocking=False: fire-and-forget, so the camera loop never waits on BLE
                car.movement_move(speed=speed, blocking=False)
                last_speed = speed

            cv2.imshow("Phone Camera AprilTag Parking (press q to quit)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        if connected:
            try:
                car.motor_stop(motor=le.MOTOR_BOTH)
                car.disconnect()
            except Exception as exc:
                print(f"Error while stopping/disconnecting the car: {exc}")
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
