# AR Ping-Pong

A ping-pong game played in augmented reality: the laptop webcam shows you standing at the end of a virtual table, and you return balls from a virtual opponent, "Chris", using a real paddle: a LEGO Education Double Motor with an AprilTag on it. The motor's IMU detects your swings with a trained classifier and buzzes in your hand when you hit, and the live score is published over MQTT to a scoreboard on an Arduino UNO Q.

## How to play

1. **Pick a level:** hold a level card up to the camera for 1 second: **1 = EASY**, **2 = MEDIUM**, **3 = HARD**. After a 3-2-1 countdown, Chris serves.
2. **Get in position:** move the paddle so its **white center dot is inside the target ring**. The ring fills in when you're lined up.
3. **Swing after the bounce:** the ball bounces on your side of the table at the moment the ring turns green and **NOW!** appears. Swing (or push the paddle toward the screen) then.
4. **Aim and power:**
   - **Aim:** hitting with the paddle left or right of the ring's center sends the return toward that side of Chris's end.
   - **Power:** a harder swing sends it faster. A very hard swing is a **SMASH!**
5. **Scoring:** you win the point if Chris doesn't reach your return in time, and Chris wins it if you miss. Games go to **11, win by 2**, and a **7-0** lead ends the match early (skunk).
6. **Keys:**

   | Key | Action |
   |---|---|
   | **SPACE** | pause / resume. While paused, hold up a level card to start a new match at that level |
   | **S** | swing from the keyboard |
   | **M** | mute / unmute |
   | **Q** | quit |

Your **streak** is how many balls in a row you've hit (it resets when you miss). The best streak per level is your **record**.

## Hardware

- **Laptop:** a Mac with a webcam. The game asks the camera for 1280x720.
- **Double Motor:** a LEGO Education Double Motor (Bluetooth) used as the paddle, with **AprilTag 0** stuck on it.
- **Level cards:** AprilTags **1, 2, 3** (print `tags/tags_sheet.png` at 100% scale).
- **Optional:** an Arduino UNO Q for the LED-matrix scoreboard ([unoq_scoreboard/README.md](unoq_scoreboard/README.md)).

## Setup and run

The game runs on the repo's Python virtual environment (`.venv`, Python 3.11 or newer; it was developed on 3.14):

```bash
cd ME193-Robotics
python3 -m venv .venv          # first time only
.venv/bin/python -m pip install legoeducation opencv-python "mediapipe==0.10.35" numpy \
    paho-mqtt scikit-learn joblib sounddevice certifi
```

Run it from the repo root:

```bash
.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/game.py"              # normal: Double Motor paddle
.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/game.py" --no-motor   # no motor: press S to swing
.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/game.py" --threshold  # old threshold swing detection
```

Turn the Double Motor on before starting. On first use, macOS asks to let the terminal use the camera and Bluetooth. Every 10 seconds the terminal prints the frame rate and where the time goes (`[perf] ...`).

## File map

| File / folder | What it does |
|---|---|
| [game.py](game.py) | The game: camera loop, game states, hit check, rallies and scoring, MQTT. **All tunable constants are at the top.** |
| [ar_view.py](ar_view.py) | Drawing: the perspective table, the ball's flight and bounce, the paddle, the opponent |
| [opponent.py](opponent.py) | The opponent's PD-controlled paddle, and how your return's aim and power become a landing point and speed |
| [effects.py](effects.py) | Arcade effects: particles, floating "+1", screen shake, red flash, speaker icon |
| [sounds.py](sounds.py) | All sounds, synthesized with numpy (no sound files) and played through `sounddevice` |
| [swing_features.py](swing_features.py) | The 14 IMU window features used by both the classifier training and the game |
| [collect_swing_data.py](collect_swing_data.py) | Records labeled IMU data (swings after beeps, plus normal non-swing moves) into `swing_data.csv` |
| [train_swing_classifier.py](train_swing_classifier.py) | Trains the logistic-regression swing classifier and saves `swing_model.joblib` |
| [tune_opponent.py](tune_opponent.py) | Simulates thousands of rallies to check how hard each level's opponent is |
| [make_tags.py](make_tags.py) | Makes the AprilTag images in `tags/` |
| `swing_data.csv` | The recorded swing / non-swing IMU data |
| `swing_model.joblib` | The trained swing classifier the game loads |
| `record.json` | Best streak per level (EASY / MEDIUM / HARD) |
| [models/](models/) | MediaPipe pose landmarker model (`pose_landmarker_lite.task`) |
| [tags/](tags/) | Printable AprilTags: 0 = paddle, 1-3 = level cards, plus a one-page sheet |
| [unoq_scoreboard/](unoq_scoreboard/) | Arduino UNO Q app: shows the live score from MQTT on its LED matrix |
| [steps/](steps/) | Early standalone tests: `imu_test.py` (IMU readout), `swing_test.py` (threshold swing + haptic kick), `paddle_tracker.py` (AprilTag tracking) |

## How it works

**Camera**
- **Paddle (AprilTag):** each frame, OpenCV's `cv2.aruco` finds the AprilTags (family 36h11) in the webcam image. The video is shown mirrored like a selfie camera.
- **Body (MediaPipe Pose):** on a background thread, it finds the wrist of the paddle hand and your shoulders, and makes a person mask.
- **When the tag is blurred:** fast swings blur the tag. The game then uses the wrist plus the learned wrist-to-tag offset, and remembers the paddle's last position for 0.7 s.
- **Targets:** they're placed relative to your shoulders, leaning toward your paddle hand.
- **Drawing you in front:** the person mask draws you in front of the table.

**Swing detection (IMU)**
- **Data:** the Double Motor's IMU streams at about 50 readings per second.
- **Classifier:** a scikit-learn logistic regression looks at the last 0.4 s of readings (14 features such as peak gyro and peak acceleration difference from gravity). It calls it a swing when the probability is above 0.5, with a 0.6 s cooldown.
- **Fallback:** with `--threshold`, or if `swing_model.joblib` is missing, a swing is gyro > 560 or an acceleration more than 500 milli-g away from gravity.

**Hit check**
- A hit needs **both**:
  - a swing between `EARLY_WINDOW` seconds before the ball arrives (EASY 0.8, MEDIUM 0.6, HARD 0.45 s) and 0.25 s after
  - the paddle's center within the ring (`HIT_RADIUS`: EASY 0.20, MEDIUM 0.16, HARD 0.11 of the screen)
- **Miss reasons:** TOO EARLY, TOO LATE, WRONG SPOT, or NO SWING!

**The opponent**
- **Your return:** your aim sets where the ball lands at Chris's end, and your swing power (from the IMU peaks) sets how fast it gets there.
- **Chris's paddle:** it chases the landing point with a PD controller (acceleration = Kp·(target − x) − Kd·velocity). It has a speed limit, a reaction delay, a catch radius and a small random miss chance. The values are set per level.
- **Faster rallies:** each hit makes the next incoming ball faster, and the speed resets every point.

**Feedback**
- **On a hit:** the motor kicks with a green light and a beep.
- **On a miss:** it gives a longer buzz with a red light.
- **Lights:** blue while waiting, at match end and while paused. A new record pulses the light green with three beeps. Winning a match cycles colors with rising beeps, and losing plays falling beeps.

## MQTT topics

Broker `broker.hivemq.com`, port 1883. All messages are **retained**, so a new subscriber gets the latest value right away.

| Topic | Value | Example | When |
|---|---|---|---|
| `ME193/Rogers/Mohammed` | best record over all levels (float) | `15.0` | at startup and whenever it goes up |
| `ME193/Rogers/Mohammed/easy` | EASY record (float) | `15.0` | at startup and whenever it goes up |
| `ME193/Rogers/Mohammed/medium` | MEDIUM record (float) | `5.0` | at startup and whenever it goes up |
| `ME193/Rogers/Mohammed/hard` | HARD record (float) | `3.0` | at startup and whenever it goes up |
| `ME193/Rogers/Mohammed/game` | live match score | `0-0`, `7-5`, `11-7 WIN`, `9-11 LOSS`, `7-0 WIN (SKUNK)` | match start, every point, match end |

The physical scoreboard that shows these is in [unoq_scoreboard/](unoq_scoreboard/README.md).

## Retraining the swing classifier

If swings are missed or gentle moves count as swings, record more data and retrain (the Double Motor must be on):

```bash
.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/collect_swing_data.py"        # 30 beeps + 60 s moving + 10 s still
.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/train_swing_classifier.py"    # prints accuracy, saves swing_model.joblib
```

- **What the collector does:** after each beep, swing like you do in the game. Then move around normally without swinging. Every run appends to `swing_data.csv`, so you can add data later (for example `--swings 10 --idle 20 --still 5`).
- **What training reports:** test accuracy and a confusion matrix on swings it never trained on (the split is by event), plus the three most important features.

## Tuning

- **Constants:** all game constants are at the top of [game.py](game.py), grouped by topic:
  - per-level difficulty (flight time, hit radius, early window, speed-up)
  - the opponent (`BOT_*`)
  - return shots (aim spread, `POWER_*`, smash)
  - match rules (`POINTS_TO_WIN`, `WIN_BY`, `SKUNK_SCORE`)
  - swing detection (`SWING_PROB`, thresholds)
  - targets, camera and performance
- **Drawing constants:** table and ball-flight constants are at the top of [ar_view.py](ar_view.py).
- **Checking the opponent:** after changing the opponent's `BOT_*` values, run `.venv/bin/python "Mohammed's Projects/Midterm Ping Pong/tune_opponent.py"`. It uses the same opponent code as the game and prints, per level, how often the opponent fails to return different kinds of shots, and how often a player who hits 90% or 60% of balls wins points and games.

## Opponent photo

The opponent shows a head-and-shoulders photo, `chris_photo.png`, on a cartoon robot body. The photo is **not in this repository** (it's in `.gitignore`).

- **With the photo:** put it in this folder and the game cuts the person out with MediaPipe on the first run, caching the result as `chris_cutout.png` (also not committed).
- **Without it:** the game uses a cartoon robot head instead. Everything else works the same.
