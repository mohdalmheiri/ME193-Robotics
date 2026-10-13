# AR ping-pong: rallies against a virtual opponent, game to 11 (win by 2).
# The bot serves; a virtual ball flies toward you on the webcam screen and you hit it
# with the real paddle (Double Motor with AprilTag 0 on it). Where your paddle center
# is in the ring aims your return, and how hard you swing sets its speed; the bot's
# paddle chases it (opponent.py). Swings come from the motor's IMU,
# paddle position comes from the camera: the AprilTag when it's visible, otherwise
# the wrist of the paddle hand (MediaPipe Pose) plus the learned wrist->tag offset.
#
# Swings are detected by a trained classifier (swing_model.joblib), or by the
# old gyro/acc thresholds with --threshold or when there's no model yet.
#
# Run:  python game.py              (press q in the video window to quit)
#       python game.py --threshold  (old threshold swing detection)
#       python game.py --no-motor   (S = swing, for testing without the motor)
# SPACE pauses a match (and resumes it).
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

from opponent import opponent
from swing_classifier.swing_features import MIN_SAMPLES, WINDOW_S, window_features
from visuals_and_sounds import ar_view, effects, sounds

# ---------------------------------------------------------------------------
# Tunable numbers
# ---------------------------------------------------------------------------
# Swing detection: trained classifier (swing_model.joblib, from train_swing_classifier.py)
SWING_PROB = 0.5          # model probability above this = a swing
CLASSIFY_EVERY = 3        # run the model every this many new IMU readings (~every 60 ms)
MODEL_POLL = 0.005        # check for a new IMU reading this often in model mode (readings come every 20 ms)
MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swing_classifier", "swing_model.joblib")
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
HIT_BEEP_HZ = 1760        # motor beep on a HIT (and the NEW RECORD triple beep)
MISS_BEEP_HZ = 220        # motor beep on a MISS
RECORD_BEEPS_S = 0.6      # how long the NEW RECORD triple beep lasts (swing detection pauses)
MISS_LIGHT_HOLD = 0.8     # red light stays this long after a miss before going blue

# Ball
# Per-level difficulty
FLIGHT_TIME = {"EASY": 1.8, "MEDIUM": 1.2, "HARD": 0.75}   # seconds per ball at the start
HIT_RADIUS = {"EASY": 0.20, "MEDIUM": 0.16, "HARD": 0.11}  # paddle must be within this normalized
                                                           # distance of the landing spot
SPEEDUP = {"EASY": 0.97, "MEDIUM": 0.95, "HARD": 0.92}     # after each hit, flight time x this
                                                           # (3% / 5% / 8% faster)
EARLY_WINDOW = {"EASY": 0.8, "MEDIUM": 0.6, "HARD": 0.45}  # a swing may be this early before the ball
                                                           # arrives (earlier = TOO EARLY)
MIN_FLIGHT = 0.45         # never faster than this
# Opponent (opponent.py) - its paddle chases your return with a PD controller
BOT_NAME = {"EASY": "Rookie Chris", "MEDIUM": "Pro Chris", "HARD": "Champion Chris"}
BOT_COLOR = {"EASY": (60, 200, 60), "MEDIUM": (0, 140, 255), "HARD": (40, 40, 220)}   # BGR
BOT_KP = {"EASY": 15.0, "MEDIUM": 25.0, "HARD": 40.0}       # pull toward the landing point (1/s^2)
BOT_KD = {"EASY": 7.7, "MEDIUM": 10.0, "HARD": 12.6}        # damping (1/s); 2*sqrt(KP) = no overshoot
BOT_MAX_SPEED = {"EASY": 0.2, "MEDIUM": 0.3, "HARD": 0.5}   # table widths per second
BOT_REACTION = {"EASY": 0.45, "MEDIUM": 0.3, "HARD": 0.25}  # seconds before it starts chasing
BOT_CATCH = {"EASY": 0.08, "MEDIUM": 0.08, "HARD": 0.06}    # returns it if this close (table widths)
BOT_MISS_CHANCE = {"EASY": 0.30, "MEDIUM": 0.10, "HARD": 0.03}  # random miss even when in place
LAND_X = (0.25, 0.75)     # FIXED target range, normalized - used when no body is detected
LAND_Y = (0.3, 0.7)
# BODY targets: placed relative to your shoulders (center = shoulder midpoint, unit = shoulder width)
TARGET_X_SW = (-0.8, 1.0)   # shoulder widths sideways; + = toward your PADDLE_HAND side
TARGET_Y_SW = (-0.2, 0.8)   # shoulder widths; - = above the shoulders, + = below
TARGET_CLAMP_X = (0.2, 0.8) # keep targets away from the screen edges (normalized)
TARGET_CLAMP_Y = (0.2, 0.72)
TARGET_MIN_MOVE = 0.15      # each target is at least this far (normalized) from the previous one
PADDLE_HEAD_R = 0.07        # virtual paddle head radius, fraction of screen width (same on every level)
PADDLE_ALPHA = {"TAG": 0.7, "POSE": 0.4}   # paddle opacity by position source
PERSON_MASK_BLUR = 7        # soft edge (pixels at 720p) when drawing you in front of the table

# Performance
POSE_INPUT_W = 640          # pose + person mask run on a copy this wide (MediaPipe works at 256 px anyway)
DETECT_MAX_W = 1280         # tags are detected on a copy at most this wide (no change at 720p)
PERF_REPORT_S = 10          # print the average FPS (and where the time goes) this often
BODY_MAX_AGE = 0.5          # shoulders seen within this many seconds count as "body detected"
# Ball look (table, flight path and sizes are in ar_view.py)
MISS_FX_TIME = 0.6          # seconds the ball keeps going past you and fades after a miss

# Hit rules
WINDOW_AFTER = 0.25       # a swing may be this late after the ball arrives (early limit: EARLY_WINDOW)
PADDLE_MEMORY = 0.7       # use the paddle position last seen within this many seconds
TAG_PREFERENCE = 0.5      # for a swing, use the last TAG position if it's this recent, even if POSE is newer

# Your return shot (opponent.py)
AIM_SPREAD = 0.45         # hitting at the ring's edge sends the ball this far from the center (table widths)
AIM_NOISE = 0.05          # small random scatter on where it lands
POWER_ACC_FULL = 4000     # swing peak acc diff (milli-g) that counts as full power
POWER_GYRO_FULL = 900     # swing peak gyro that counts as full power
POWER_WINDOW = 0.5        # look for the swing's peaks this many seconds before the hit
KEY_SWING_POWER = 0.5     # power of an S-key swing (no IMU)
RETURN_SLOW = 1.4         # seconds for your return to reach the bot at power 0...
RETURN_FAST = 0.7         # ...and at power 1
SMASH_POWER = 0.8         # power above this = SMASH!
SMASH_SPEEDUP = 0.75      # a smash's flight time x this

# Match
POINTS_TO_WIN = 11        # game to 11...
WIN_BY = 2                # ...win by 2
SKUNK_SCORE = 7           # leading 7-0 ends the match right away (skunk)
POINT_PAUSE = 1.6         # seconds between a point and the next serve

# Arcade feedback
COMBO_TIERS = [(10, "UNSTOPPABLE!", (255, 0, 255)),   # streak reached -> label + color (BGR)
               (5, "ON FIRE!", (0, 140, 255)),
               (3, "NICE!", (0, 255, 255))]
COMBO_LABEL_TIME = 1.2    # seconds a combo label stays up
RECORD_BANNER_TIME = 2.0  # seconds the NEW RECORD! banner stays up
GOLD = (0, 215, 255)

# Menus
LEVEL_HOLD = 1.0          # hold a level card this long to start
LEVEL_DROPOUT = 0.25      # a card can vanish for this long (blur/flicker) without resetting the hold
COUNTDOWN = 3             # 3, 2, 1
GAME_OVER_LOCKOUT = 1.0   # seconds on MATCH OVER before a level card is accepted

# Camera / tags (same as paddle_tracker.py)
CAMERA_INDEX = 0
CAMERA_RES = (1280, 720)    # requested from the webcam; frames of any other size are resized to this
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
POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER = 11, 12
# Opponent's face: a head-and-shoulders photo, cut out once with MediaPipe and cached
# (both files are in .gitignore - kept on this laptop only)
OPPONENT_PHOTO = Path(__file__).parent / "opponent" / "chris_photo.png"
OPPONENT_CUTOUT = Path(__file__).parent / "opponent" / "chris_cutout.png"
CUTOUT_EDGE = (0.45, 0.9)  # mask values below/above this range = fully cut out / fully kept (no halo)
CUTOUT_EDGE_BLUR = 1.0    # soft edge of the cutout (pixels of the photo)
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
        self._history = collections.deque(maxlen=600)   # (time, gyro, acc_diff) for swing power
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
            print("Could not connect to the motor - S key = swing instead.")
            return
        print("Motor connected!")
        self.dm.light_color(le.LEGO_COLOR_BLUE)   # blue = waiting
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
                    self._history.append((now, gyro, acc_diff))
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
            # Never wait on the motor (blocking=False everywhere): a blocking call waits
            # forever if the motor's reply is lost. Swing detection pauses for a fixed
            # time that always runs out (the motor's own shaking/beeping isn't a swing).
            try:
                if kind == "idle":                      # WAITING / MATCH OVER
                    self.dm.light_color(le.LEGO_COLOR_BLUE, blocking=False)
                    continue
                if kind in ("victory", "defeat"):       # end of a match
                    self._quiet_until = time.time() + 1.5
                    if kind == "victory":               # cycling colors + rising beeps
                        colors = [le.LEGO_COLOR_RED, le.LEGO_COLOR_YELLOW, le.LEGO_COLOR_GREEN,
                                  le.LEGO_COLOR_AZURE, le.LEGO_COLOR_PURPLE, le.LEGO_COLOR_GREEN]
                        notes = [523, 659, 784, 1047, 1319, 1568]
                    else:                               # red + falling beeps
                        colors = [le.LEGO_COLOR_RED] * 4
                        notes = [784, 622, 523, 392]
                    for color, hz in zip(colors, notes):
                        self.dm.light_color(color, blocking=False)
                        self.dm.beep(frequency=hz, blocking=False)
                        time.sleep(0.18)
                    continue
                if kind == "record":                    # pulsing green + 3 quick beeps
                    self._quiet_until = time.time() + RECORD_BEEPS_S + HAPTIC_SETTLE
                    self.dm.light_color(le.LEGO_COLOR_GREEN, pattern=le.LIGHT_PATTERN_PULSE, blocking=False)
                    self.dm.beep(pattern=le.SOUND_PATTERN_BEEP_TRIPLE, frequency=HIT_BEEP_HZ, blocking=False)
                    time.sleep(RECORD_BEEPS_S)
                    continue
                if kind == "hit":                       # green + short high beep + double kick
                    steps = [(KICK_MS, cw), (KICK_MS, ccw)] * 2
                    color, beep_hz = le.LEGO_COLOR_GREEN, HIT_BEEP_HZ
                else:                                   # miss: red + low beep + long buzz
                    steps = [(MISS_BUZZ_MS, cw)]
                    color, beep_hz = le.LEGO_COLOR_RED, MISS_BEEP_HZ
                self._quiet_until = time.time() + sum(ms for ms, _ in steps) / 1000 + HAPTIC_SETTLE
                self.dm.light_color(color, blocking=False)
                self.dm.beep(frequency=beep_hz, blocking=False)
                for ms, direction in steps:
                    self.dm.motor_run_for_time(ms, motor=le.MOTOR_BOTH, speed=100,
                                               direction=direction, blocking=False)
                    time.sleep(ms / 1000)
                if kind == "miss":
                    time.sleep(MISS_LIGHT_HOLD)         # keep the red light on a moment before blue
            except Exception as exc:
                print(f"Haptic error: {exc}")

    def peaks_since(self, t0):
        """(peak acc diff, peak gyro) of readings since time t0 - how hard the swing was."""
        recent = [(g, a) for t, g, a in list(self._history) if t >= t0]
        if not recent:
            return 0.0, 0.0
        return max(a for _, a in recent), max(g for g, _ in recent)

    def reset_peaks(self):
        self.peak_gyro = 0.0
        self.peak_acc_diff = 0.0
        self.peak_p = 0.0

    def haptic(self, kind):
        """kind = "hit", "miss", "record", "victory", "defeat" or "idle". Returns immediately."""
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


def load_opponent_face():
    """The opponent's photo cut out from its background (BGRA, soft edges, cropped), or None.

    Uses the cached OPPONENT_CUTOUT if it's newer than the photo; otherwise runs MediaPipe's
    person segmentation on the still photo once and saves the result."""
    if not OPPONENT_PHOTO.exists():
        print(f"No {OPPONENT_PHOTO.name} - the opponent is the cartoon robot.")
        return None
    if OPPONENT_CUTOUT.exists() and OPPONENT_CUTOUT.stat().st_mtime >= OPPONENT_PHOTO.stat().st_mtime:
        cut = cv2.imread(str(OPPONENT_CUTOUT), cv2.IMREAD_UNCHANGED)
        if cut is not None and cut.ndim == 3 and cut.shape[2] == 4:
            return cut
    try:
        photo = cv2.imread(str(OPPONENT_PHOTO), cv2.IMREAD_UNCHANGED)
        bgr = photo[:, :, :3]
        alpha0 = photo[:, :, 3].astype(np.float32) / 255 if photo.ndim == 3 and photo.shape[2] == 4 else 1.0
        ensure_model()
        segmenter = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.IMAGE,
            output_segmentation_masks=True,
        ))
        result = segmenter.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                           data=np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))))
        segmenter.close()
        if not result.segmentation_masks:
            print(f"No person found in {OPPONENT_PHOTO.name} - the opponent is the cartoon robot.")
            return None
        m = result.segmentation_masks[0].numpy_view().copy()
        lo, hi = CUTOUT_EDGE
        m = cv2.GaussianBlur(np.clip((m - lo) / (hi - lo), 0, 1), (0, 0), CUTOUT_EDGE_BLUR)
        alpha = (m * alpha0 * 255).astype(np.uint8)
        x, y, w, h = cv2.boundingRect((alpha > 25).astype(np.uint8))
        x0, y0 = max(0, x - 4), max(0, y - 4)
        cut = np.dstack([bgr, alpha])[y0:y + h + 4, x0:x + w + 4]
        cv2.imwrite(str(OPPONENT_CUTOUT), cut)
        print(f"Cut out the opponent from {OPPONENT_PHOTO.name} -> {OPPONENT_CUTOUT.name}")
        return cut
    except Exception as exc:
        print(f"Could not cut out {OPPONENT_PHOTO.name} ({exc}) - the opponent is the cartoon robot.")
        return None


class PoseTracker:
    """Runs MediaPipe Pose on the newest camera frame in a background thread.

    self.latest = (frame_time, paddle_wrist, other_wrist), wrists as mirrored
    normalized (x, y) or None when not visible.
    self.body = (frame_time, left_shoulder, right_shoulder) from the last frame
    where both shoulders were visible (same coordinates).
    self.mask = (frame_time, small mask, scale, box) for drawing you in front of the table:
    a soft 0..1 person mask at POSE_INPUT_W wide (mirrored), scale = small / full width,
    box = (x0, y0, x1, y1) around the person in full-frame pixels.

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
            output_segmentation_masks=True,   # person mask, to draw you in front of the AR table
        ))
        if PADDLE_HAND == "right":
            self._wrist_idx, self._other_idx = POSE_RIGHT_WRIST, POSE_LEFT_WRIST
        else:
            self._wrist_idx, self._other_idx = POSE_LEFT_WRIST, POSE_RIGHT_WRIST
        self.latest = None
        self.body = None
        self.mask = None
        self.results = 0   # how many frames pose has processed (for the FPS report)
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
                full_h, full_w = frame.shape[:2]
                k = min(1.0, POSE_INPUT_W / full_w)
                if k < 1:
                    frame = cv2.resize(frame, (POSE_INPUT_W, round(full_h * k)), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self._landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
                wrist = other = None
                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    wrist, other = self._wrist(lm[self._wrist_idx]), self._wrist(lm[self._other_idx])
                    ls, rs = self._wrist(lm[POSE_LEFT_SHOULDER]), self._wrist(lm[POSE_RIGHT_SHOULDER])
                    if ls and rs:
                        self.body = (t, ls, rs)
                if result.segmentation_masks:
                    m = cv2.flip(result.segmentation_masks[0].numpy_view(), 1)   # also copies it
                    m = cv2.GaussianBlur(m, (0, 0), max(1.0, PERSON_MASK_BLUR * full_h / 720 * k))
                    bx, by, bw, bh = cv2.boundingRect((m > 0.02).astype(np.uint8))
                    box = (int(bx / k) - 2, int(by / k) - 2, int((bx + bw) / k) + 3, int((by + bh) / k) + 3)
                    self.mask = (t, m, k, box) if bw and bh else None
                self.latest = (t, wrist, other)
                self.results += 1
        except Exception:
            print("Pose thread crashed:")
            traceback.print_exc()

    @staticmethod
    def _wrist(p):
        """Mirrored normalized (x, y) of a landmark (wrist or shoulder), or None if not visible."""
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
    """Records per level, saved in record.json and published over MQTT (retained).

    TOPIC gets the best record across all levels (what the assignment reads);
    TOPIC/easy, /medium and /hard get each level's record.
    """

    def __init__(self):
        self.records = self.load()
        self.client = None
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.client.connect(BROKER, PORT, keepalive=30)
            self.client.loop_start()
            print(f"Connected to {BROKER}. Publishing records to {TOPIC} (+ /easy /medium /hard)")
        except Exception as exc:
            print(f"MQTT connection failed ({exc}) - playing without publishing.")
            self.client = None
        self.publish(TOPIC, self.best)
        for level in LEVELS.values():
            self.publish(f"{TOPIC}/{level.lower()}", self.records[level])

    @property
    def best(self):
        return max(self.records.values())

    def publish(self, topic, value):
        msg = str(float(value))
        if self.client is not None:
            self.client.publish(topic, msg, retain=True)   # retained: new subscribers get it at once
            print(f"MQTT -> {topic}: {msg}")

    def publish_game(self, msg):
        """Live match score for the physical scoreboard, e.g. "7-5" or "11-7 WIN"."""
        if self.client is not None:
            self.client.publish(f"{TOPIC}/game", msg, retain=True)
            print(f"MQTT -> {TOPIC}/game: {msg}")

    def update(self, level, streak):
        if streak > self.records[level]:
            old_best = self.best
            self.records[level] = float(streak)
            self.save()
            self.publish(f"{TOPIC}/{level.lower()}", self.records[level])
            if self.best > old_best:
                self.publish(TOPIC, self.best)

    @staticmethod
    def load():
        """Per-level records from record.json. An old single {"record": x} file becomes EASY = x."""
        records = {level: 0.0 for level in LEVELS.values()}
        try:
            with open(RECORD_FILE) as f:
                saved = json.load(f)
            if "record" in saved:   # old format, from before per-level records
                records["EASY"] = float(saved["record"])
                print(f"Moved the old record {records['EASY']} to EASY")
            for level in records:
                records[level] = float(saved.get(level, records[level]))
            print(f"Loaded records from {RECORD_FILE}: {records}")
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"Could not read {RECORD_FILE} ({exc}) - starting from 0")
        return records

    def save(self):
        try:
            with open(RECORD_FILE, "w") as f:
                json.dump(self.records, f)
        except Exception as exc:
            print(f"Could not save records to {RECORD_FILE}: {exc}")

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
    parser.add_argument("--no-motor", action="store_true", help="don't connect the motor; S key = swing")
    parser.add_argument("--threshold", action="store_true",
                        help="use the old gyro/acc thresholds instead of the trained swing model")
    args = parser.parse_args()

    pose = PoseTracker()   # first: if MediaPipe fails, nothing else is connected yet
    opponent_face = load_opponent_face()
    model = None
    if not args.no_motor:
        if args.threshold:
            print("Swing detection: thresholds (--threshold)")
        else:
            model = load_swing_model()
    paddle = Paddle(use_motor=not args.no_motor, model=model)
    score = Scoreboard()
    sound = sounds.Sounds()
    fxv = effects.Effects()

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        paddle.close()
        score.close()
        pose.close()
        sound.close()
        raise RuntimeError("Could not open webcam.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RES[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RES[1])
    print(f"Camera: requested {CAMERA_RES[0]}x{CAMERA_RES[1]}, "
          f"camera reports {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
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
    table = None             # ar_view.TableView, built on the first frame
    fx = None                # a ball you missed, flying on past you: {"t0", "ball"}
    ball = None              # the ball coming to you (None while your return flies, and between points)
    ret = None               # your return flying to the bot: {"start", "arrive", "from", "land", "lost"}
    bot = None               # opponent.Opponent for the current match
    me_pts = bot_pts = 0
    serve_at = None          # time of the next serve (between points)
    point_msg = None         # (text, subtext, color, until) shown after a point
    smash_until = 0.0        # "SMASH!" shown until
    match_best = 0           # longest streak this match
    match_won = False
    skunk = False            # did the match end by the skunk rule?
    prev_now = time.time()
    # Game clock: `now` below is wall time minus all paused time, and it stands still while
    # paused - so the ball, hit window, serve delay, opponent, countdown and effects all freeze.
    paused = False
    paused_total = 0.0       # seconds spent paused so far
    paused_at = 0.0          # wall time the current pause started
    record_at_start = 0.0    # the record when this game started (beating it = NEW RECORD)
    new_record = False       # did this game beat it?
    combo_label = None       # (text, color, until)
    banner_until = 0.0       # NEW RECORD! banner
    last_count = None        # last countdown number beeped
    go_until = 0.0           # "GO!" shown until
    miss_reason = ""
    last_swing_shown = 0.0
    fps, last_time = 0.0, time.time()
    perf = {"start": time.time(), "frames": 0, "read": 0.0, "tags": 0.0, "total": 0.0, "pose": 0}

    def report_ball(result):
        """How close did the swing get? Peak IMU readings during this ball's flight."""
        if paddle.connected:
            model_msg = f", peak p {paddle.peak_p:.2f}" if paddle.model is not None else ""
            print(f"ball ended: {result}, peak gyro {paddle.peak_gyro:.0f}, "
                  f"peak acc diff {paddle.peak_acc_diff:.0f}{model_msg}")
        else:
            print(f"ball ended: {result} (no motor)")

    last_target = None

    def candidate_target(now):
        """One random target (x, y, source): relative to your shoulders if visible, else the fixed area."""
        body = pose.body
        if body and now - body[0] <= BODY_MAX_AGE:
            (lx, ly), (rx, ry) = body[1], body[2]
            cx, cy = (lx + rx) / 2 * w, (ly + ry) / 2 * h          # pixels, so x and y share one scale
            sw = math.dist((lx * w, ly * h), (rx * w, ry * h))
            if sw > 0.03 * w:
                # mirrored video: your right hand is on the right of the screen, so + x = your right
                side = 1 if PADDLE_HAND == "right" else -1
                x = (cx + side * random.uniform(*TARGET_X_SW) * sw) / w
                y = (cy + random.uniform(*TARGET_Y_SW) * sw) / h
                return (min(max(x, TARGET_CLAMP_X[0]), TARGET_CLAMP_X[1]),
                        min(max(y, TARGET_CLAMP_Y[0]), TARGET_CLAMP_Y[1]), "BODY")
        return random.uniform(*LAND_X), random.uniform(*LAND_Y), "FIXED"

    def pick_target(now):
        """A target at least TARGET_MIN_MOVE away from the previous one (best of 30 tries)."""
        nonlocal last_target
        best, best_d = None, -1.0
        for _ in range(30):
            cand = candidate_target(now)
            d = math.dist(cand[:2], last_target) if last_target else 1.0
            if d > best_d:
                best, best_d = cand, d
            if d >= TARGET_MIN_MOVE:
                break
        last_target = best[:2]
        return best

    def in_ring(pos, ball):
        """Is paddle position pos (x, y, source) inside the ball's target ring (the hit zone)?"""
        return pos is not None and math.dist(pos[:2], (ball["x"], ball["y"])) <= HIT_RADIUS[level]

    ball_no = 0

    def new_ball(now):
        nonlocal ball_no
        paddle.reset_peaks()
        x, y, src = pick_target(now)
        ball_no += 1
        print(f"ball {ball_no}: target ({x:.2f}, {y:.2f}) [{src}]")
        _, zt = table.target_to_table(x, y)
        bounce_s, bounce_d = ar_view.bounce_plan(flight, EARLY_WINDOW[level])   # bounce = hit window opens
        return {"x": x, "y": y, "start": now, "arrive": now + flight, "swung_wrong": False, "last_swing": None,
                "zt": zt, "bounce_s": bounce_s, "bounce_d": bounce_d,   # 3D flight path (ar_view)
                "u0": bot.x}                                            # leaves from the bot's paddle

    try:
        while True:
            t_loop = time.time()
            ok, frame = cap.read()
            if not ok:
                break
            wall_now = time.time()
            now = (paused_at if paused else wall_now) - paused_total   # game time
            if table is None:
                fh, fw = frame.shape[:2]
                print(f"Camera: first frame is {fw}x{fh}"
                      + ("" if (fw, fh) == CAMERA_RES else f" - resizing every frame to {CAMERA_RES[0]}x{CAMERA_RES[1]}"))
            if frame.shape[1::-1] != CAMERA_RES:   # camera ignored the request: shrink before any processing
                frame = cv2.resize(frame, CAMERA_RES, interpolation=cv2.INTER_AREA)
            h, w = frame.shape[:2]
            S = h / 720   # scale text/shapes to the camera resolution
            dt_frame, prev_now = min(now - prev_now, 0.1), now
            if bot is not None:
                bot.update(now, dt_frame)

            # --- camera: detect before mirroring (mirrored tags don't decode) ---
            if w > DETECT_MAX_W:   # big frames: detect on a smaller copy, scale the corners back
                kd = DETECT_MAX_W / w
                corners, ids, _ = detector.detectMarkers(
                    cv2.resize(frame, (DETECT_MAX_W, round(h * kd)), interpolation=cv2.INTER_AREA))
                corners = [c / kd for c in corners]
            else:
                corners, ids, _ = detector.detectMarkers(frame)
            t_tags = time.time()
            pose.submit(frame, now)   # raw frame; flip() below returns a new image, so this one isn't drawn on
            frame = cv2.flip(frame, 1)
            if table is None or (table.w, table.h) != (w, h):
                table = ar_view.TableView(w, h)
            # draw you back on top of the table (person mask from the pose thread, ~1 frame old),
            # only where your bounding box overlaps the table
            mask = pose.mask
            region = None
            if mask and now - mask[0] <= POSE_MAX_AGE:
                bx0, by0, bx1, by1 = mask[3]
                tx0, ty0, tx1, ty1 = table.roi
                x0, y0, x1, y1 = max(bx0, tx0, 0), max(by0, ty0, 0), min(bx1, tx1, w), min(by1, ty1, h)
                if x1 > x0 and y1 > y0:
                    region = (x0, y0, x1, y1)
                    cam = frame[y0:y1, x0:x1].copy()
            table.draw_table(frame)
            if region:
                x0, y0, x1, y1 = region
                k = mask[2]
                small = mask[1][int(y0 * k):max(int(y0 * k) + 1, math.ceil(y1 * k)),
                                int(x0 * k):max(int(x0 * k) + 1, math.ceil(x1 * k))]
                m = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
                frame[y0:y1, x0:x1] = cv2.blendLinear(cam, frame[y0:y1, x0:x1], m, 1 - m)
            # the opponent goes on top of you, so standing in the middle never hides it
            if bot is not None and level:
                ar_view.draw_robot(frame, table, bot.x, BOT_COLOR[level], now, opponent_face)
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
                        if state in ("WAITING", "MATCH OVER"):
                            cv2.polylines(frame, box, True, BLUE, 3)
                            text(frame, LEVELS[tag_id], (int(pts[:, 0].max()) + 10, int(cy)),
                                 1.2 * S, BLUE, 3)

            # --- paddle position: fuse tag + wrist ---
            if tag_pos:
                tag_seen[now] = tag_pos
                paddle_seen.append((now, *tag_pos, "TAG"))
            for t in [t for t in tag_seen if now - t > 1.0]:
                del tag_seen[t]
            latest = pose.latest
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

            # --- keys ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):   # S is always a swing (with or without the motor)
                paddle.swings.put((wall_now, "S KEY"))
            if key == ord("m"):
                sound.toggle_mute()
            if key == ord(" ") and state in ("COUNTDOWN", "PLAYING"):   # pause / resume a match
                if paused:
                    paused = False
                    paused_total += wall_now - paused_at
                    print("Resumed")
                else:
                    paused, paused_at, hold_level = True, wall_now, None
                    paddle.haptic("idle")   # blue while paused
                    print("Paused")

            # --- swings ---
            while not paddle.swings.empty():
                ts_wall, trigger = paddle.swings.get()   # swing times come in wall time
                if paused:
                    print("swing ignored (paused)")
                    continue
                ts = ts_wall - paused_total               # -> game time
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
                            match_best = max(match_best, streak)
                            score.update(level, streak)
                            paddle.haptic("hit")
                            bx, by = ball["x"] * w, ball["y"] * h
                            fxv.burst(now, bx, by, S)
                            fxv.floater(now, "+1", bx, by - HIT_RADIUS[level] * h, GREEN)
                            if not new_record and streak > record_at_start:   # first time this match
                                new_record, banner_until = True, now + RECORD_BANNER_TIME
                                sound.play("record")
                                paddle.haptic("record")
                                fxv.burst(now, w / 2, 0.3 * h, S, n=80, colors=effects.CONFETTI,
                                          speed=500, life=1.6, up=300)
                            for n, label, color in COMBO_TIERS:
                                if streak == n:
                                    combo_label = (label, color, now + COMBO_LABEL_TIME)
                            report_ball("HIT")
                            flight = max(MIN_FLIGHT, flight * SPEEDUP[level])
                            # your return: AIM = where the paddle center is in the ring (left/right),
                            # POWER = how hard the swing was
                            aim = max(-1.0, min(1.0, (pos[0] - ball["x"]) / HIT_RADIUS[level]))
                            if trigger == "S KEY" or not paddle.connected:
                                power = KEY_SWING_POWER
                            else:
                                power = opponent.swing_power(*paddle.peaks_since(ts_wall - POWER_WINDOW),
                                                             POWER_ACC_FULL, POWER_GYRO_FULL)
                            land, ret_time, smash = opponent.plan_return(
                                aim, power, AIM_SPREAD, AIM_NOISE, RETURN_SLOW, RETURN_FAST,
                                SMASH_POWER, SMASH_SPEEDUP)
                            print(f"return: aim {aim:+.2f}, power {power:.2f}{' SMASH!' if smash else ''}"
                                  f" -> lands at {land:.2f} in {ret_time:.2f} s")
                            ret = {"start": now, "arrive": now + ret_time, "land": land, "lost": False,
                                   "from": ar_view.ball_state(ball, now, table)}
                            bot.chase(land, now)
                            if smash:
                                sound.play("smash")
                                smash_until = now + 0.9
                                fxv.burst(now, bx, by, S, n=45, colors=((0, 140, 255), (0, 215, 255),
                                                                         (255, 255, 255)), speed=650)
                            else:
                                sound.play("hit")
                            ball = None
                        else:
                            ball["swung_wrong"] = True
                else:
                    print(f"swing ignored ({trigger}; no ball coming to you, state {state})")

            # --- AR layer (before the state text so text stays on top) ---
            # order: shadows/bounce mark on the table, your return (far away), paddle, target ring, ball
            pos = paddle_at(now)
            if fx and now - fx["t0"] >= MISS_FX_TIME:
                fx = None
            fx_ball = fx_alpha = None
            if fx:   # a ball you missed keeps going past you and fades out
                fx_ball = ar_view.ball_state(fx["ball"], now, table)
                fx_alpha = 1 - (now - fx["t0"]) / MISS_FX_TIME
            if ret and ret["lost"] and now - ret["arrive"] >= MISS_FX_TIME:
                ret = None
            ret_ball = ret_alpha = None
            if ret:   # your return flying to the bot (fades past its end if the bot missed)
                ret_ball = ar_view.return_state(ret, now)
                ret_alpha = max(0.0, 1 - (now - ret["arrive"]) / MISS_FX_TIME) if ret["lost"] else 1.0
                if not ret.get("bounce_heard") and now >= ret["start"] + ar_view.RET_BOUNCE_S * (ret["arrive"] - ret["start"]):
                    ret["bounce_heard"] = True
                    sound.play("bounce")
            playing_ball = ball if state == "PLAYING" and ball is not None else None
            ball_now = ar_view.ball_state(playing_ball, now, table) if playing_ball else None

            if ball_now:
                ar_view.draw_shadow(frame, table, *ball_now)
                bounce_t = ball["start"] + ball["bounce_s"] * (ball["arrive"] - ball["start"])
                if now >= bounce_t:
                    ar_view.draw_bounce_mark(frame, table, ball, now - bounce_t)
                    if not ball.get("bounce_heard"):
                        ball["bounce_heard"] = True
                        sound.play("bounce")
            if fx_ball:
                ar_view.draw_shadow(frame, table, *fx_ball, alpha=fx_alpha)
            if ret_ball:
                ar_view.draw_shadow(frame, table, *ret_ball, alpha=ret_alpha)
                ar_view.draw_ball(frame, table, *ret_ball, alpha=ret_alpha)
            if playing_ball:
                bx, by = int(ball["x"] * w), int(ball["y"] * h)
                rx, ry = int(HIT_RADIUS[level] * w), int(HIT_RADIUS[level] * h)
                window_open = ball["arrive"] - EARLY_WINDOW[level] <= now <= ball["arrive"] + WINDOW_AFTER
                if pos and math.dist(pos[:2], (ball["x"], ball["y"])) <= HIT_RADIUS[level]:
                    # in position (paddle center dot inside the ring): fill the ring
                    fill = (180, 255, 180) if window_open else (255, 255, 255)
                    ar_view.blend(frame, 0.3, (bx - rx - 1, by - ry - 1, bx + rx + 2, by + ry + 2),
                                  lambda img, ox, oy: cv2.ellipse(img, (bx - ox, by - oy), (rx, ry),
                                                                  0, 0, 360, fill, -1))
            if pos:
                # virtual paddle: fixed size; its center dot is the point the hit check uses,
                # so center dot inside the green ring = in position
                ar_view.draw_paddle(frame, pos[0] * w, pos[1] * h, PADDLE_HEAD_R * w,
                                    PADDLE_ALPHA[pos[2]], PADDLE_HAND)
            if playing_ball:
                # target ring = the hit zone (this level's HIT_RADIUS in normalized x and y):
                # faint while waiting, bright green + "NOW!" while the hit window is open
                # (the window opens at the bounce)
                if window_open:
                    cv2.ellipse(frame, (bx, by), (rx, ry), 0, 0, 360, GREEN, 6)
                    text(frame, "NOW!", (bx + rx + int(10 * S), by), 0.9 * S, GREEN, 2)
                else:
                    ar_view.blend(frame, 0.35, (bx - rx - 3, by - ry - 3, bx + rx + 4, by + ry + 4),
                                  lambda img, ox, oy: cv2.ellipse(img, (bx - ox, by - oy), (rx, ry),
                                                                  0, 0, 360, WHITE, 3))
                ar_view.draw_ball(frame, table, *ball_now)
            if fx_ball:
                ar_view.draw_ball(frame, table, *fx_ball, alpha=fx_alpha)
            fxv.draw(frame, now, S, text)

            def start_countdown(chosen):
                """A level card was held: reset everything for a new match."""
                nonlocal level, state, state_start, streak, record_at_start, new_record, last_count
                nonlocal bot, me_pts, bot_pts, ball, ret, fx, serve_at, point_msg, match_best
                level, state, state_start, streak = chosen, "COUNTDOWN", now, 0
                record_at_start, new_record, last_count = score.records[chosen], False, None
                bot = opponent.Opponent(BOT_KP[chosen], BOT_KD[chosen], BOT_MAX_SPEED[chosen],
                                        BOT_REACTION[chosen], BOT_CATCH[chosen], BOT_MISS_CHANCE[chosen])
                me_pts = bot_pts = match_best = 0
                ball = ret = fx = serve_at = point_msg = None
                score.publish_game("0-0")

            def end_point(i_won, msg):
                """Score a point; then the next serve, or the end of the match."""
                nonlocal me_pts, bot_pts, point_msg, serve_at, state, state_start, hold_level, match_won, skunk
                if i_won:
                    me_pts += 1
                    sound.play("point_won")
                else:
                    bot_pts += 1
                    sound.play("point_lost")
                point_msg = (msg, "YOUR POINT" if i_won else f"{BOT_NAME[level].upper()}'S POINT",
                             GREEN if i_won else RED, now + POINT_PAUSE)
                print(f"point: ME {me_pts} - {bot_pts} {BOT_NAME[level]}")
                skunk = max(me_pts, bot_pts) == SKUNK_SCORE and min(me_pts, bot_pts) == 0
                if skunk or (max(me_pts, bot_pts) >= POINTS_TO_WIN and abs(me_pts - bot_pts) >= WIN_BY):
                    match_won = me_pts > bot_pts
                    score.publish_game(f"{me_pts}-{bot_pts} {'WIN' if match_won else 'LOSS'}"
                                       + (" (SKUNK)" if skunk else ""))
                    state, state_start, hold_level, serve_at = "MATCH OVER", now, None, None
                    if match_won:
                        sound.play("win")
                        paddle.haptic("victory")
                        for cx in (0.25, 0.5, 0.75):
                            fxv.burst(now, cx * w, 0.35 * h, S, n=50, colors=effects.CONFETTI,
                                      speed=550, life=2.0, up=350)
                    else:
                        sound.play("lose")
                        paddle.haptic("defeat")
                    paddle.haptic("idle")   # blue when the victory/defeat feedback is done
                else:
                    score.publish_game(f"{me_pts}-{bot_pts}")
                    serve_at = now + POINT_PAUSE

            # --- level card hold (WAITING / MATCH OVER) ---
            def check_level_card():
                nonlocal hold_level, hold_since, hold_last_seen
                now = wall_now if paused else game_now   # the game clock is stopped while paused
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
            game_now = now
            if paused:
                frame[:] = cv2.convertScaleAbs(frame, alpha=0.35)   # darken everything drawn so far
                text(frame, "PAUSED", (w // 2, int(0.3 * h)), 3.0 * S, WHITE, 8, center=True)
                text(frame, f"{level}   ME {me_pts} - {bot_pts} {BOT_NAME[level]}", (w // 2, int(0.42 * h)),
                     1.3 * S, YELLOW, 3, center=True)
                text(frame, "SPACE: resume  |  Hold up a level card: new match at that level  |  Q: quit",
                     (w // 2, int(0.52 * h)), 0.75 * S, WHITE, 2, center=True)
                chosen = check_level_card()
                if chosen:   # abandon this match (no result published) and start a new one
                    paused = False
                    paused_total += wall_now - paused_at
                    print(f"Match abandoned - new match at {chosen}")
                    start_countdown(chosen)
            elif state == "WAITING":
                text(frame, "AR PING PONG", (w // 2, int(0.3 * h)), 2.8 * S, GOLD, 7, center=True)
                text(frame, "Hold up a level card: 1 EASY, 2 MEDIUM, 3 HARD", (w // 2, int(0.45 * h)),
                     1.1 * S, WHITE, 3, center=True)
                text(frame, "Paddle in the ring, swing after the bounce", (w // 2, int(0.53 * h)),
                     1.0 * S, YELLOW, 2, center=True)
                text(frame, "Records:  " + "  |  ".join(f"{lv} {score.records[lv]:.0f}" for lv in LEVELS.values()),
                     (w // 2, int(0.72 * h)), 1.0 * S, WHITE, 2, center=True)
                chosen = check_level_card()
                if chosen:
                    start_countdown(chosen)

            elif state == "COUNTDOWN":
                left = COUNTDOWN - (now - state_start)
                if left > 0:
                    if math.ceil(left) != last_count:
                        last_count = math.ceil(left)
                        sound.play("count")
                    text(frame, str(math.ceil(left)), (w // 2, h // 2), 8 * S, YELLOW, 12, center=True)
                    text(frame, f"{level}: you vs {BOT_NAME[level]}", (w // 2, int(0.75 * h)), 1.3 * S,
                         WHITE, 3, center=True)
                else:
                    state, flight = "PLAYING", FLIGHT_TIME[level]
                    ball = new_ball(now)    # the bot serves
                    sound.play("go")
                    go_until = now + 0.6

            elif state == "PLAYING":
                # your return reaches the bot's end: did its paddle get there?
                if ret and not ret["lost"] and now >= ret["arrive"]:
                    if bot.returns(ret["land"]):
                        sound.play("bot_hit")
                        ret = None
                        ball = new_ball(now)          # it hits the ball back to you
                        bot.recenter(now)
                    else:
                        ret["lost"] = True
                        why = ("too far" if abs(bot.x - ret["land"]) > bot.catch_radius
                               else "random miss chance")
                        print(f"{BOT_NAME[level]} missed ({why}): paddle at {bot.x:.2f}, ball at {ret['land']:.2f}")
                        end_point(True, "POINT!")
                # the ball coming to you: missed?
                if ball is not None and now > ball["arrive"] + WINDOW_AFTER + IMU_POLL:
                    if ball["last_swing"] is not None and ball["last_swing"] < ball["arrive"] - EARLY_WINDOW[level]:
                        miss_reason = "TOO EARLY"
                    elif ball["swung_wrong"]:
                        miss_reason = "WRONG SPOT"
                    elif ball["last_swing"] is None and in_ring(swing_paddle_at(ball["arrive"]), ball):
                        miss_reason = "NO SWING!"   # in position at arrival, just didn't swing
                    else:
                        miss_reason = "TOO LATE"
                    report_ball(f"MISS {miss_reason}")
                    paddle.haptic("miss")
                    sound.play("miss")
                    fxv.start_shake(now)
                    fxv.start_red_flash(now)
                    fx = {"t0": now, "ball": ball}
                    ball = None
                    streak = 0                        # the streak ends when YOU miss
                    end_point(False, f"MISS - {miss_reason}")
                # next serve (the bot serves every point)
                if state == "PLAYING" and serve_at is not None and now >= serve_at:
                    serve_at, flight = None, FLIGHT_TIME[level]
                    bot.recenter(now)
                    ball = new_ball(now)
                    sound.play("bot_hit")
                if point_msg and now < point_msg[3]:
                    text(frame, point_msg[0], (w // 2, int(0.36 * h)), 2.2 * S, point_msg[2], 6, center=True)
                    text(frame, point_msg[1], (w // 2, int(0.46 * h)), 1.2 * S, WHITE, 3, center=True)

            elif state == "MATCH OVER":
                if match_won:
                    if skunk:
                        text(frame, f"SKUNK! YOU WIN {me_pts}-{bot_pts}", (w // 2, int(0.22 * h)), 2.2 * S, GOLD, 7,
                             center=True)
                    else:
                        text(frame, "YOU WIN!", (w // 2, int(0.22 * h)), 3.0 * S, GOLD, 8, center=True)
                    if now - state_start < 3 and int((now - state_start) / 0.5) != int((now - state_start - dt_frame) / 0.5):
                        fxv.burst(now, random.uniform(0.2, 0.8) * w, 0.3 * h, S, n=35,
                                  colors=effects.CONFETTI, speed=500, life=1.8, up=300)
                elif skunk:
                    text(frame, f"SKUNKED! {me_pts}-{bot_pts}", (w // 2, int(0.22 * h)), 2.6 * S, RED, 7, center=True)
                else:
                    text(frame, f"{BOT_NAME[level].upper()} WINS", (w // 2, int(0.22 * h)), 2.6 * S, RED, 7,
                         center=True)
                text(frame, f"{me_pts} - {bot_pts}", (w // 2, int(0.34 * h)), 2.0 * S, WHITE, 5, center=True)
                text(frame, f"Best streak: {match_best}    {level} record: {score.records[level]:.0f}",
                     (w // 2, int(0.44 * h)), 1.2 * S, WHITE, 3, center=True)
                if new_record:
                    text(frame, "NEW RECORD!", (w // 2, int(0.52 * h)), 1.6 * S, GOLD, 5, center=True)
                text(frame, "Hold up a card to play again", (w // 2, int(0.59 * h)),
                     1.0 * S, WHITE, 2, center=True)
                if now - state_start > GAME_OVER_LOCKOUT:
                    chosen = check_level_card()
                    if chosen:
                        start_countdown(chosen)

            # --- scoreboard, combo, GO!, SMASH!, NEW RECORD! banner ---
            if state in ("COUNTDOWN", "PLAYING", "MATCH OVER"):
                board = f"ME  {me_pts} - {bot_pts}  {BOT_NAME[level]}"
                (bw_, bh_), _ = cv2.getTextSize(board, FONT, 1.1 * S, 3)
                ar_view.blend(frame, 0.55, (w // 2 - bw_ // 2 - 18 * S, 8 * S, w // 2 + bw_ // 2 + 18 * S, 20 * S + bh_ + 14 * S),
                              lambda img, ox, oy: img.fill(0))
                text(frame, board, (w // 2, int(14 * S + bh_ / 2 + 7 * S)), 1.1 * S, WHITE, 3, center=True)
            if state == "PLAYING" and not paused:
                if now < go_until:
                    text(frame, "GO!", (w // 2, h // 2), 5 * S, GREEN, 12, center=True)
                if streak > 0:
                    color = next((c for n, _, c in COMBO_TIERS if streak >= n), WHITE)
                    # left side under "Record", clear of the opponent at the far end
                    text(frame, f"x{streak}", (15, int(195 * S)), 2.0 * S, color, 6)
                if combo_label and now < combo_label[2]:
                    text(frame, combo_label[0], (15, int(245 * S)), 1.4 * S, combo_label[1], 4)
                if now < smash_until:
                    text(frame, "SMASH!", (w // 2, int(0.6 * h)), 2.4 * S, (0, 140, 255), 7, center=True)
            if now < banner_until and not paused:
                pulse = 1 + 0.08 * math.sin(now * 12)
                text(frame, "NEW RECORD!", (w // 2, int(0.3 * h)), 2.6 * S * pulse, GOLD, 8, center=True)

            # --- HUD (always) ---
            text(frame, f"Level: {level or '-'}", (15, int(40 * S)), 1.1 * S, WHITE, 2)
            text(frame, f"Streak: {streak}", (15, int(85 * S)), 1.1 * S, WHITE, 2)
            record_msg = f"Record: {score.records[level]:.0f}" if level else "Record: -"
            text(frame, record_msg, (15, int(130 * S)), 1.1 * S, WHITE, 2)

            if pos:
                color = GREEN if pos[2] == "TAG" else YELLOW
                text(frame, f"Paddle: {pos[2]}", (15, h - int(20 * S)), 1.1 * S, color, 3)
            else:
                text(frame, "PADDLE LOST", (15, h - int(20 * S)), 1.1 * S, RED, 3)

            if now - last_swing_shown < 0.3:
                text_right(frame, "SWING", h - int(20 * S), 1.3 * S, YELLOW, 3)

            dt = wall_now - last_time
            last_time = wall_now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
            text_right(frame, f"FPS {fps:.0f}", int(40 * S), 1.0 * S, WHITE, 2)
            mode = "MODEL" if paddle.model is not None else "THRESHOLD"
            motor_msg = f"Motor: YES ({mode})" if paddle.connected else "Motor: NO (S = swing)"
            text_right(frame, motor_msg, int(85 * S), 1.0 * S, GREEN if paddle.connected else RED, 2)
            sound_msg = "M: muted" if sound.muted else "M: sound on"
            (tw, _), _ = cv2.getTextSize(sound_msg, FONT, 0.8 * S, 2)
            text_right(frame, sound_msg, int(130 * S), 0.8 * S, RED if sound.muted else WHITE, 2)
            effects.draw_speaker(frame, w - 15 - tw - int(50 * S), int(105 * S), S, sound.muted)

            if not paused:
                frame = fxv.post(frame, now, S)   # miss: red edges + screen shake
            cv2.imshow("Ping Pong (press q to quit)", frame)

            # --- FPS report in the terminal ---
            t_end = time.time()
            perf["frames"] += 1
            perf["read"] += wall_now - t_loop
            perf["tags"] += t_tags - wall_now
            perf["total"] += t_end - t_loop
            if t_end - perf["start"] >= PERF_REPORT_S:
                n, span = perf["frames"], t_end - perf["start"]
                print(f"[perf] {n / span:.1f} FPS avg over {span:.0f} s | per frame: "
                      f"camera wait {1000 * perf['read'] / n:.1f} ms, tags {1000 * perf['tags'] / n:.1f} ms, "
                      f"everything else {1000 * (perf['total'] - perf['read'] - perf['tags']) / n:.1f} ms | "
                      f"pose {(pose.results - perf['pose']) / span:.0f} frames/s")
                perf.update(start=t_end, frames=0, read=0.0, tags=0.0, total=0.0, pose=pose.results)
    finally:
        paddle.close()
        score.close()
        pose.close()
        sound.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
