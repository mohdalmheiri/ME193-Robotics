# Step 4: solo ping-pong against a wall.
# A virtual ball flies toward you on the webcam screen; hit it with the real
# paddle (Double Motor with AprilTag 0 on it). Swings come from the motor's IMU,
# paddle position comes from the camera: the AprilTag when it's visible, otherwise
# the wrist of the paddle hand (MediaPipe Pose) plus the learned wrist->tag offset.
#
# Swings are detected by a trained classifier (swing_model.joblib), or by the
# old gyro/acc thresholds with --threshold or when there's no model yet.
#
# Run:  python game.py              (press q in the video window to quit)
#       python game.py --threshold  (old threshold swing detection)
#       python game.py --no-motor   (SPACE = swing, for testing without the motor)
import argparse
import collections
import json
import math
import os
import queue
import random
import ssl
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import certifi
import cv2
import joblib
import mediapipe as mp
import numpy as np
import paho.mqtt.client as mqtt
from mediapipe.tasks.python import BaseOptions, vision

from swing_features import MIN_SAMPLES, WINDOW_S, window_features

# ---------------------------------------------------------------------------
# Tunable numbers
# ---------------------------------------------------------------------------
# Swing detection: trained classifier (swing_model.joblib, from train_swing_classifier.py)
SWING_PROB = 0.6          # model probability above this = a swing
CLASSIFY_EVERY = 3        # run the model every this many new IMU readings (~every 60 ms)
MODEL_POLL = 0.005        # check for a new IMU reading this often in model mode (readings come every 20 ms)
MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swing_model.joblib")
# Fallback threshold detection (--threshold, or when there's no model; from swing_test.py)
GYRO_THRESHOLD = 560      # gyro magnitude above this = a swing (rotating the paddle)...
ACC_THRESHOLD = 500       # ...OR acceleration this far from gravity (1000 milli-g), i.e. acc > 1500
                          # or acc < 500 (pushing the paddle toward the screen)
COOLDOWN = 0.6            # seconds before another swing can count
IMU_POLL = 0.02           # seconds between IMU reads in the background thread
HAPTIC_SETTLE = 0.15      # ignore swings this long after a haptic finishes (motor shake)

# Haptics
KICK_MS = 60              # each jerk of the HIT kick (x2 back and forth, x2)
MISS_BUZZ_MS = 300        # one long buzz on a MISS

# Ball
# Per-level difficulty
FLIGHT_TIME = {"EASY": 1.8, "MEDIUM": 1.2, "HARD": 0.75}   # seconds per ball at the start
HIT_RADIUS = {"EASY": 0.17, "MEDIUM": 0.14, "HARD": 0.10}  # paddle must be within this normalized
                                                           # distance of the landing spot
SPEEDUP = {"EASY": 0.97, "MEDIUM": 0.95, "HARD": 0.92}     # after each hit, flight time x this
                                                           # (3% / 5% / 8% faster)
EARLY_WINDOW = {"EASY": 0.8, "MEDIUM": 0.6, "HARD": 0.45}  # a swing may be this early before the ball
                                                           # arrives (earlier = TOO EARLY)
MIN_FLIGHT = 0.45         # never faster than this
LAND_X = (0.25, 0.75)     # landing spot range, normalized (stays away from the edges)
LAND_Y = (0.3, 0.7)
BALL_MIN_R = 0.015        # ball radius at launch, fraction of frame height
BALL_MAX_R = 0.08         # ball radius on arrival

# Hit rules
WINDOW_AFTER = 0.25       # a swing may be this late after the ball arrives (early limit: EARLY_WINDOW)
PADDLE_MEMORY = 0.7       # use the paddle position last seen within this many seconds
TAG_PREFERENCE = 0.5      # for a swing, use the last TAG position if it's this recent, even if POSE is newer
HIT_PAUSE = 0.8           # pause after a hit before the next ball

# Menus
LEVEL_HOLD = 1.0          # hold a level card this long to start
LEVEL_DROPOUT = 0.25      # a card can vanish for this long (blur/flicker) without resetting the hold
COUNTDOWN = 3             # 3, 2, 1
GAME_OVER_LOCKOUT = 1.0   # seconds on GAME OVER before a level card is accepted

# Camera / tags (same as paddle_tracker.py)
CAMERA_INDEX = 0
TAG_FAMILY = cv2.aruco.DICT_APRILTAG_36h11
PADDLE_ID = 0
LEVELS = {1: "EASY", 2: "MEDIUM", 3: "HARD"}

# Pose (MediaPipe, same setup as Pose Race / HW1)
PADDLE_HAND = "right"     # the hand holding the paddle (YOUR right hand)
WRIST_MIN_VISIBILITY = 0.5  # ignore the wrist when MediaPipe is less sure than this
POSE_MAX_AGE = 0.2        # a pose result older than this (seconds) counts as "wrist not visible"
OFFSET_SMOOTHING = 0.2    # EMA weight of each new wrist->tag offset sample (0..1, higher = faster)
MODEL_PATH = Path(__file__).parent / "models" / "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
POSE_LEFT_WRIST, POSE_RIGHT_WRIST = 15, 16

# MQTT (same broker as HW4)
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "ME193/Rogers/Mohammed"
RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "record.json")

GREEN = (0, 255, 0)   # OpenCV colors are BGR
BLUE = (255, 0, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)
YELLOW = (0, 255, 255)
ORANGE = (0, 140, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------------------
# Motor: IMU polling thread + haptics thread
# ---------------------------------------------------------------------------
class Paddle:
    """Double Motor wrapper. Swing times arrive on self.swings (a queue)."""

    def __init__(self, use_motor, model=None):
        self.model = model         # trained classifier, or None = threshold detection
        self.swings = queue.Queue()
        self.connected = False
        self.dm = None
        self._haptics = queue.Queue()
        self._stop = threading.Event()
        self._quiet_until = 0.0
        self.peak_gyro = 0.0       # highest readings since reset_peaks() (debug)
        self.peak_acc_diff = 0.0
        self.peak_p = 0.0
        if use_motor:
            self._connect()

    def _connect(self):
        import legoeducation as le
        self.le = le
        try:
            self.dm = le.DoubleMotor()
            print("Searching for the Double Motor...")
            self.dm.connect(device_notification_delay=20)
            self.connected = self.dm.connected
        except Exception as exc:
            print(f"Motor connection error: {exc}")
        if not self.connected:
            print("Could not connect to the motor - SPACE = swing instead.")
            return
        print("Motor connected!")
        self.dm.light_color(le.LEGO_COLOR_GREEN)
        threading.Thread(target=self._imu_loop, daemon=True).start()
        threading.Thread(target=self._haptic_loop, daemon=True).start()

    def _imu_loop(self):
        try:
            last_swing = 0.0
            last_error = None
            last_imu = None
            window = collections.deque()   # model mode: (time, [ax, ay, az, gx, gy, gz]) of the last WINDOW_S
            new_readings = 0
            while not self._stop.is_set():
                gyro = acc = float("nan")
                imu = None
                try:
                    imu = self.dm.imu_device
                    gyro = math.sqrt(imu.gyroscopeX ** 2 + imu.gyroscopeY ** 2 + imu.gyroscopeZ ** 2)
                    acc = math.sqrt(imu.accelerometerX ** 2 + imu.accelerometerY ** 2
                                    + imu.accelerometerZ ** 2)
                except Exception as exc:
                    if repr(exc) != last_error:   # print each new error once, don't hide it
                        last_error = repr(exc)
                        print("IMU read error:")
                        traceback.print_exc()
                now = time.time()
                # the haptic buzz shakes the paddle - don't count that as a swing
                quiet = now < self._quiet_until
                acc_diff = abs(acc - 1000)
                if not quiet and not math.isnan(gyro) and not math.isnan(acc):
                    self.peak_gyro = max(self.peak_gyro, gyro)
                    self.peak_acc_diff = max(self.peak_acc_diff, acc_diff)
                if self.model is None:
                    gyro_hit, acc_hit = gyro > GYRO_THRESHOLD, acc_diff > ACC_THRESHOLD
                    if (gyro_hit or acc_hit) and now - last_swing > COOLDOWN and not quiet:
                        last_swing = now
                        trigger = "GYRO+ACC" if gyro_hit and acc_hit else "GYRO" if gyro_hit else "ACC"
                        self.swings.put((now, f"gyro {gyro:.0f}, acc {acc:.0f} -> {trigger}"))
                    time.sleep(IMU_POLL)
                    continue

                # model mode: only NEW readings go into the window (the library
                # swaps in a new object for each one)
                if imu is not None and imu is not last_imu and not math.isnan(gyro):
                    last_imu = imu
                    if quiet:
                        window.clear()   # don't let the haptic buzz linger in the window
                    else:
                        window.append((now, [imu.accelerometerX, imu.accelerometerY, imu.accelerometerZ,
                                             imu.gyroscopeX, imu.gyroscopeY, imu.gyroscopeZ]))
                        new_readings += 1
                    while window and now - window[0][0] > WINDOW_S:
                        window.popleft()
                    if new_readings >= CLASSIFY_EVERY and len(window) >= MIN_SAMPLES:
                        new_readings = 0
                        feats = window_features([r for _, r in window])
                        p = self.model.predict_proba([feats])[0, 1]
                        self.peak_p = max(self.peak_p, p)
                        if p > SWING_PROB and now - last_swing > COOLDOWN:
                            last_swing = now
                            self.swings.put((now, f"p={p:.2f} [MODEL]"))
                time.sleep(MODEL_POLL)
        except BaseException:
            print("IMU thread crashed:")
            traceback.print_exc()

    def _haptic_loop(self):
        le = self.le
        cw, ccw = le.MOTOR_MOVE_DIRECTION_CLOCKWISE, le.MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE
        while True:
            kind = self._haptics.get()
            if kind is None:
                return
            # Pause swing detection for a fixed time that always runs out. (A
            # blocking motor call waits forever if the motor's reply is lost, which
            # used to leave swing detection switched off for the rest of the game.)
            steps = ([(KICK_MS, cw), (KICK_MS, ccw)] * 2 if kind == "hit"
                     else [(MISS_BUZZ_MS, cw)])
            self._quiet_until = time.time() + sum(ms for ms, _ in steps) / 1000 + HAPTIC_SETTLE
            try:
                for ms, direction in steps:
                    self.dm.motor_run_for_time(ms, motor=le.MOTOR_BOTH, speed=100,
                                               direction=direction, blocking=False)
                    time.sleep(ms / 1000)
            except Exception as exc:
                print(f"Haptic error: {exc}")

    def reset_peaks(self):
        self.peak_gyro = 0.0
        self.peak_acc_diff = 0.0
        self.peak_p = 0.0

    def haptic(self, kind):
        """kind = "hit" or "miss". Returns immediately; plays in the background."""
        if self.connected:
            self._haptics.put(kind)

    def close(self):
        self._stop.set()
        if not self.connected:
            return
        self._haptics.put(None)
        try:
            self.dm.motor_stop(motor=self.le.MOTOR_BOTH)
            self.dm.disconnect()
            print("Motor disconnected.")
        except Exception as exc:
            print(f"Error while stopping/disconnecting the motor: {exc}")


def load_swing_model():
    """The trained swing classifier, or None (then threshold detection is used)."""
    if not os.path.exists(MODEL_FILE):
        print(f"WARNING: {MODEL_FILE} not found - using threshold swing detection. "
              "Run collect_swing_data.py and train_swing_classifier.py to make it.")
        return None
    try:
        saved = joblib.load(MODEL_FILE)
    except Exception as exc:
        print(f"WARNING: could not load {MODEL_FILE} ({exc}) - using threshold swing detection.")
        return None
    if saved.get("window_s") != WINDOW_S:
        print(f"WARNING: model was trained with {saved.get('window_s')} s windows but WINDOW_S is "
              f"{WINDOW_S} - retrain it. Using threshold swing detection.")
        return None
    print(f"Swing detection: trained model ({MODEL_FILE}), swing if p > {SWING_PROB}")
    return saved["model"]


# ---------------------------------------------------------------------------
# Pose: wrist tracking on a background thread
# ---------------------------------------------------------------------------
def ensure_model():
    if not MODEL_PATH.exists():
        print("Downloading pose landmarker model (first run only)...")
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        # certifi's CA bundle: python.org Python on macOS doesn't use the system cert store
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(MODEL_URL, context=ssl_context) as response:
            MODEL_PATH.write_bytes(response.read())


class PoseTracker:
    """Runs MediaPipe Pose on the newest camera frame in a background thread.

    self.latest = (frame_time, paddle_wrist, other_wrist), wrists as mirrored
    normalized (x, y) or None when not visible.

    Left/right: MediaPipe's left/right landmarks are the PERSON's left/right,
    and we feed it the raw (un-mirrored) camera frame like Pose Race did, so
    landmark 16 is your right wrist. Only its x needs mirroring (1 - x) to
    match the flipped video on screen.
    """

    def __init__(self):
        ensure_model()
        self._landmarker = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        ))
        if PADDLE_HAND == "right":
            self._wrist_idx, self._other_idx = POSE_RIGHT_WRIST, POSE_LEFT_WRIST
        else:
            self._wrist_idx, self._other_idx = POSE_LEFT_WRIST, POSE_RIGHT_WRIST
        self.latest = None
        self._pending = None
        self._cond = threading.Condition()
        self._stop = False
        self._t0 = time.time()
        self._last_ms = -1
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame, t):
        """Hand over the newest raw frame; an older one still waiting is dropped."""
        with self._cond:
            self._pending = (frame, t)
            self._cond.notify()

    def _loop(self):
        try:
            while True:
                with self._cond:
                    while self._pending is None and not self._stop:
                        self._cond.wait()
                    if self._stop:
                        return
                    frame, t = self._pending
                    self._pending = None
                ms = int((t - self._t0) * 1000)
                if ms <= self._last_ms:   # VIDEO mode needs increasing timestamps
                    continue
                self._last_ms = ms
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self._landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
                wrist = other = None
                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    wrist, other = self._wrist(lm[self._wrist_idx]), self._wrist(lm[self._other_idx])
                self.latest = (t, wrist, other)
        except Exception:
            print("Pose thread crashed:")
            traceback.print_exc()

    @staticmethod
    def _wrist(p):
        if p.visibility < WRIST_MIN_VISIBILITY or not (0 <= p.x <= 1 and 0 <= p.y <= 1):
            return None
        return (1 - p.x, p.y)   # mirror x to match the flipped video

    def close(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(timeout=1)
        self._landmarker.close()


# ---------------------------------------------------------------------------
# MQTT score
# ---------------------------------------------------------------------------
class Scoreboard:
    def __init__(self):
        self.record = self.load()
        self.client = None
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.client.connect(BROKER, PORT, keepalive=30)
            self.client.loop_start()
            print(f"Connected to {BROKER}. Publishing record to {TOPIC}")
        except Exception as exc:
            print(f"MQTT connection failed ({exc}) - playing without publishing.")
            self.client = None
        self.publish()

    def publish(self):
        msg = str(self.record)
        if self.client is not None:
            self.client.publish(TOPIC, msg)
            print(f"MQTT -> {TOPIC}: {msg}")

    def update(self, streak):
        if streak > self.record:
            self.record = float(streak)
            self.save()
            self.publish()

    @staticmethod
    def load():
        """Best streak from earlier runs (record.json), or 0.0 if there isn't one."""
        try:
            with open(RECORD_FILE) as f:
                record = float(json.load(f)["record"])
            print(f"Loaded record {record} from {RECORD_FILE}")
            return record
        except FileNotFoundError:
            return 0.0
        except Exception as exc:
            print(f"Could not read {RECORD_FILE} ({exc}) - starting from 0.0")
            return 0.0

    def save(self):
        try:
            with open(RECORD_FILE, "w") as f:
                json.dump({"record": self.record}, f)
        except Exception as exc:
            print(f"Could not save record to {RECORD_FILE}: {exc}")

    def close(self):
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def text(frame, msg, org, scale, color, thick=2, center=False):
    """Text with a black outline so it's readable on any background."""
    (tw, th), _ = cv2.getTextSize(msg, FONT, scale, thick)
    x, y = org
    if center:
        x, y = x - tw // 2, y + th // 2
    cv2.putText(frame, msg, (x, y), FONT, scale, (0, 0, 0), thick + 4, cv2.LINE_AA)
    cv2.putText(frame, msg, (x, y), FONT, scale, color, thick, cv2.LINE_AA)
    return tw


def text_right(frame, msg, y, scale, color, thick=2):
    (tw, _), _ = cv2.getTextSize(msg, FONT, scale, thick)
    text(frame, msg, (frame.shape[1] - tw - 15, y), scale, color, thick)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Virtual ping-pong with the LEGO Double Motor paddle.")
    parser.add_argument("--no-motor", action="store_true", help="don't connect the motor; SPACE = swing")
    parser.add_argument("--threshold", action="store_true",
                        help="use the old gyro/acc thresholds instead of the trained swing model")
    args = parser.parse_args()

    pose = PoseTracker()   # first: if MediaPipe fails, nothing else is connected yet
    model = None
    if not args.no_motor:
        if args.threshold:
            print("Swing detection: thresholds (--threshold)")
        else:
            model = load_swing_model()
    paddle = Paddle(use_motor=not args.no_motor, model=model)
    score = Scoreboard()

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        paddle.close()
        score.close()
        pose.close()
        raise RuntimeError("Could not open webcam.")
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(TAG_FAMILY))

    # paddle memory: recent positions (time, x, y, source), normalized; source "TAG" or "POSE"
    paddle_seen = collections.deque(maxlen=120)
    tag_seen = {}            # frame time -> tag (x, y), to pair with the pose result of the same frame
    offset = None            # smoothed wrist -> tag center offset (dx, dy)
    last_pose_t = None
    hand_check = [0, 0]      # [paddle wrist closer to tag, other wrist closer] - PADDLE_HAND sanity check

    def paddle_at(t):
        """Last paddle position (x, y, source) seen at or before time t, within PADDLE_MEMORY."""
        for seen_t, x, y, src in reversed(paddle_seen):
            if seen_t <= t:
                return (x, y, src) if t - seen_t <= PADDLE_MEMORY else None
        return None

    def swing_paddle_at(t):
        """Paddle position for a swing at time t: a recent tag beats a newer pose estimate."""
        for seen_t, x, y, src in reversed(paddle_seen):
            if t - seen_t > TAG_PREFERENCE:
                break
            if src == "TAG" and seen_t <= t:
                return (x, y, src)
        return paddle_at(t)

    state = "WAITING"
    level = None
    streak = 0
    flight = 0.0
    state_start = time.time()
    hold_level, hold_since, hold_last_seen = None, 0.0, 0.0
    ball = None              # dict while a ball is in the air, None during the hit pause
    next_ball_at = 0.0
    flash = None             # (text, color, until)
    miss_reason = ""
    last_swing_shown = 0.0
    fps, last_time = 0.0, time.time()

    def report_ball(result):
        """How close did the swing get? Peak IMU readings during this ball's flight."""
        if paddle.connected:
            model_msg = f", peak p {paddle.peak_p:.2f}" if paddle.model is not None else ""
            print(f"ball ended: {result}, peak gyro {paddle.peak_gyro:.0f}, "
                  f"peak acc diff {paddle.peak_acc_diff:.0f}{model_msg}")
        else:
            print(f"ball ended: {result} (no motor)")

    def new_ball(now):
        paddle.reset_peaks()
        return {"x": random.uniform(*LAND_X), "y": random.uniform(*LAND_Y),
                "start": now, "arrive": now + flight, "swung_wrong": False, "last_swing": None}

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.time()
            h, w = frame.shape[:2]
            S = h / 720   # scale text/shapes to the camera resolution

            # --- camera: detect before mirroring (mirrored tags don't decode) ---
            corners, ids, _ = detector.detectMarkers(frame)
            pose.submit(frame, now)   # raw frame; flip() below returns a new image, so this one isn't drawn on
            frame = cv2.flip(frame, 1)
            levels_seen = []
            tag_pos = None
            if ids is not None:
                for tag_corners, tag_id in zip(corners, ids.flatten()):
                    pts = tag_corners.reshape(4, 2).copy()
                    pts[:, 0] = (w - 1) - pts[:, 0]
                    cx, cy = pts.mean(axis=0)
                    box = [pts.astype(np.int32)]
                    if tag_id == PADDLE_ID:
                        tag_pos = (cx / w, cy / h)
                        cv2.polylines(frame, box, True, GREEN, 3)
                    elif tag_id in LEVELS:
                        levels_seen.append(int(tag_id))
                        if state in ("WAITING", "GAME OVER"):
                            cv2.polylines(frame, box, True, BLUE, 3)
                            text(frame, LEVELS[tag_id], (int(pts[:, 0].max()) + 10, int(cy)),
                                 1.2 * S, BLUE, 3)

            # --- paddle position: fuse tag + wrist ---
            if tag_pos:
                tag_seen[now] = tag_pos
                paddle_seen.append((now, *tag_pos, "TAG"))
            for t in [t for t in tag_seen if now - t > 1.0]:
                del tag_seen[t]
            wrist = None
            latest = pose.latest
            if latest and now - latest[0] <= POSE_MAX_AGE:
                wrist = latest[1]
            if latest and latest[0] != last_pose_t:   # a new pose result
                pose_t, new_wrist, other_wrist = latest
                last_pose_t = pose_t
                tag_then = tag_seen.get(pose_t)          # tag in the SAME frame as this pose result
                if tag_then and new_wrist:
                    sample = (tag_then[0] - new_wrist[0], tag_then[1] - new_wrist[1])
                    offset = sample if offset is None else tuple(
                        (1 - OFFSET_SMOOTHING) * o + OFFSET_SMOOTHING * s for o, s in zip(offset, sample))
                    if other_wrist and sum(hand_check) < 60:
                        closer = math.dist(new_wrist, tag_then) <= math.dist(other_wrist, tag_then)
                        hand_check[0 if closer else 1] += 1
                        if sum(hand_check) == 60:
                            print(f"PADDLE_HAND check: {PADDLE_HAND} wrist closer to the tag in "
                                  f"{hand_check[0]}/60 frames"
                                  + ("" if hand_check[0] >= 30 else " - is PADDLE_HAND wrong?"))
                newer = not paddle_seen or pose_t > paddle_seen[-1][0]
                if not tag_pos and new_wrist and newer and now - pose_t <= POSE_MAX_AGE:
                    dx, dy = offset or (0.0, 0.0)
                    paddle_seen.append((pose_t, new_wrist[0] + dx, new_wrist[1] + dy, "POSE"))
            if wrist:
                wx, wy = int(wrist[0] * w), int(wrist[1] * h)
                cv2.circle(frame, (wx, wy), int(10 * S), YELLOW, 2)
                cv2.drawMarker(frame, (wx, wy), YELLOW, cv2.MARKER_CROSS, int(14 * S), 2)

            # --- keys ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" "):   # SPACE is always a swing (with or without the motor)
                paddle.swings.put((now, "SPACE"))

            # --- swings ---
            while not paddle.swings.empty():
                ts, trigger = paddle.swings.get()
                last_swing_shown = ts
                if state == "PLAYING" and ball is not None:
                    ball["last_swing"] = ts
                    pos = swing_paddle_at(ts)
                    dist = math.dist(pos[:2], (ball["x"], ball["y"])) if pos else None
                    dist_msg = f"{dist:.2f} [{pos[2]}]" if dist is not None else "n/a (paddle lost)"
                    print(f"swing at {ts - ball['arrive']:+.2f} s ({trigger}), paddle dist {dist_msg}")
                    if ball["arrive"] - EARLY_WINDOW[level] <= ts <= ball["arrive"] + WINDOW_AFTER:
                        if dist is not None and dist <= HIT_RADIUS[level]:
                            streak += 1
                            score.update(streak)
                            paddle.haptic("hit")
                            flash = ("HIT!", GREEN, now + HIT_PAUSE)
                            report_ball("HIT")
                            flight = max(MIN_FLIGHT, flight * SPEEDUP[level])
                            ball = None
                            next_ball_at = now + HIT_PAUSE
                        else:
                            ball["swung_wrong"] = True
                else:
                    print(f"swing ignored ({trigger}; no ball in the air, state {state})")

            # --- level card hold (WAITING / GAME OVER) ---
            def check_level_card():
                nonlocal hold_level, hold_since, hold_last_seen
                if hold_level in levels_seen:
                    hold_last_seen = now
                elif hold_level is None or now - hold_last_seen > LEVEL_DROPOUT:
                    hold_level = levels_seen[0] if levels_seen else None
                    hold_since = hold_last_seen = now
                if hold_level is None:
                    return None
                progress = (now - hold_since) / LEVEL_HOLD
                bar_w = int(0.4 * w)
                x0, y0 = (w - bar_w) // 2, int(0.62 * h)
                cv2.rectangle(frame, (x0, y0), (x0 + bar_w, y0 + int(20 * S)), WHITE, 2)
                cv2.rectangle(frame, (x0, y0), (x0 + int(bar_w * min(progress, 1)), y0 + int(20 * S)), BLUE, -1)
                return LEVELS[hold_level] if progress >= 1 else None

            # --- game states ---
            if state == "WAITING":
                text(frame, "Hold up a level card to start", (w // 2, int(0.5 * h)), 1.4 * S, WHITE, 3, center=True)
                chosen = check_level_card()
                if chosen:
                    level, state, state_start, streak = chosen, "COUNTDOWN", now, 0

            elif state == "COUNTDOWN":
                left = COUNTDOWN - (now - state_start)
                if left > 0:
                    text(frame, str(math.ceil(left)), (w // 2, h // 2), 8 * S, YELLOW, 12, center=True)
                    text(frame, level, (w // 2, int(0.75 * h)), 1.5 * S, WHITE, 3, center=True)
                else:
                    state, streak, flight = "PLAYING", 0, FLIGHT_TIME[level]
                    ball = new_ball(now)

            elif state == "PLAYING":
                if ball is None and now >= next_ball_at:
                    ball = new_ball(now)
                if ball is not None:
                    bx, by = int(ball["x"] * w), int(ball["y"] * h)
                    # target ring = the hit zone (this level's HIT_RADIUS in normalized x and y):
                    # faint while waiting, bright green + "NOW!" while the hit window is open
                    rx, ry = int(HIT_RADIUS[level] * w), int(HIT_RADIUS[level] * h)
                    if ball["arrive"] - EARLY_WINDOW[level] <= now <= ball["arrive"] + WINDOW_AFTER:
                        cv2.ellipse(frame, (bx, by), (rx, ry), 0, 0, 360, GREEN, 6)
                        text(frame, "NOW!", (bx + rx + int(10 * S), by), 0.9 * S, GREEN, 2)
                    else:
                        overlay = frame.copy()
                        cv2.ellipse(overlay, (bx, by), (rx, ry), 0, 0, 360, WHITE, 3)
                        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
                    # ball grows as it "flies" toward you
                    p = min(1.0, (now - ball["start"]) / (ball["arrive"] - ball["start"]))
                    r = int((BALL_MIN_R + (BALL_MAX_R - BALL_MIN_R) * p * p) * h)
                    cv2.circle(frame, (bx, by), r, ORANGE, -1)
                    cv2.circle(frame, (bx, by), r, WHITE, 2)

                    if now > ball["arrive"] + WINDOW_AFTER + IMU_POLL:
                        if ball["last_swing"] is not None and ball["last_swing"] < ball["arrive"] - EARLY_WINDOW[level]:
                            miss_reason = "TOO EARLY"
                        else:
                            miss_reason = "WRONG SPOT" if ball["swung_wrong"] else "TOO LATE"
                        report_ball(f"MISS {miss_reason}")
                        paddle.haptic("miss")
                        ball = None
                        state, state_start = "GAME OVER", now
                        hold_level = None

            elif state == "GAME OVER":
                text(frame, f"MISS - {miss_reason}", (w // 2, int(0.25 * h)), 2.5 * S, RED, 6, center=True)
                text(frame, f"Streak: {streak}    Record: {score.record:.0f}",
                     (w // 2, int(0.45 * h)), 1.5 * S, WHITE, 3, center=True)
                text(frame, "Hold up a level card to play again", (w // 2, int(0.56 * h)),
                     1.1 * S, WHITE, 2, center=True)
                if now - state_start > GAME_OVER_LOCKOUT:
                    chosen = check_level_card()
                    if chosen:
                        level, state, state_start, streak = chosen, "COUNTDOWN", now, 0

            # --- "HIT!" flash ---
            if flash and now < flash[2]:
                text(frame, flash[0], (w // 2, int(0.2 * h)), 3 * S, flash[1], 8, center=True)

            # --- HUD (always) ---
            text(frame, f"Level: {level or '-'}", (15, int(40 * S)), 1.1 * S, WHITE, 2)
            text(frame, f"Streak: {streak}", (15, int(85 * S)), 1.1 * S, WHITE, 2)
            text(frame, f"Record: {score.record:.0f}", (15, int(130 * S)), 1.1 * S, WHITE, 2)

            pos = paddle_at(now)
            if pos:
                color = GREEN if pos[2] == "TAG" else YELLOW
                cv2.circle(frame, (int(pos[0] * w), int(pos[1] * h)), int(12 * S), color, -1)
                text(frame, f"Paddle: {pos[2]}", (15, h - int(20 * S)), 1.1 * S, color, 3)
            else:
                text(frame, "PADDLE LOST", (15, h - int(20 * S)), 1.1 * S, RED, 3)

            if now - last_swing_shown < 0.3:
                text_right(frame, "SWING", h - int(20 * S), 1.3 * S, YELLOW, 3)

            dt = now - last_time
            last_time = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
            text_right(frame, f"FPS {fps:.0f}", int(40 * S), 1.0 * S, WHITE, 2)
            mode = "MODEL" if paddle.model is not None else "THRESHOLD"
            motor_msg = f"Motor: YES ({mode})" if paddle.connected else "Motor: NO (SPACE = swing)"
            text_right(frame, motor_msg, int(85 * S), 1.0 * S, GREEN if paddle.connected else RED, 2)

            cv2.imshow("Ping Pong (press q to quit)", frame)
    finally:
        paddle.close()
        score.close()
        pose.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
