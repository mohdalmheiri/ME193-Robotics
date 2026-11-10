# The Impenetrable Safe (MT2)

A laser-cut box that opens only for the right hand signals. A webcam watches
you hold up fingers, a neural network (trained with PyTorch) counts how many (0 to 5), and
if you show the correct three-number code in order, an Arduino UNO Q drives a
small TT motor through a Cytron Maker Drive to swing a latch and unlock the
box. Show the wrong code and the latch stays shut. The project runs the whole
chain a robot needs, from seeing (camera), to deciding (neural network and
code check), to acting (motor and latch), on one small board.

## How it works

**Camera**
- **Where it looks:** a USB webcam on a stand looks down at a red square on the desk. It plugs into the UNO Q through an Arduino USB-C hub.
- **Always 640x480:** the camera is forced to 640x480 and every frame is checked. A different picture shape shows a different slice of the desk, so any other size is refused: the laptop tools stop with a clear error, and the board shows a camera icon until the picture is right again (the webcam once switched to 640x360 in the middle of a session).
- **The crop:** a saved box around the red square (`crop_config.json`: x 71, y 3, size 475) is cut out and shrunk to 128x128. [hand_crop.py](02_data_collection/hand_crop.py) does this for the training photos and for the live frames, so the network always sees the same kind of picture.

**Network**
- **Shape:** a small CNN ([model.py](03_training/model.py)): 3 convolution layers (8, 16 and 32 filters of 3x3), each followed by ReLU and 2x2 max pooling, then one linear layer that gives 6 scores, one per count (0-5). 55,190 numbers in all.
- **Training (laptop, PyTorch):** 1,020 photos of Mohammed's hand from three sessions: daylight, evening with finger shadows, and harder poses. 80% train, 20% validation, split by blocks of photos taken together, so near-copies never land on both sides. Training photos are randomly rotated (±15°), shifted (±8%), brightened or darkened (×0.8-1.2) and mirrored; validation photos never are. Adam, cross-entropy, and the best epoch is kept.
- **Results:** 91.2% on the 204 validation photos at the best epoch, about 87% typically: 93.8% on daylight photos, 97.9% on evening photos, 81.7% on the harder poses. A daylight-only network scored 58.3% on the evening photos, so the evening session is what fixed the shadow mistakes.
- **On the board:** PyTorch isn't installed on the UNO Q. [finger_net.py](04_unoq_app/safe_app/python/finger_net.py) does the same maths in plain numpy: the same guess as PyTorch on all 204 validation photos, about 41 ms per guess. The board runs it at most 10 times a second, on one core, to go easy on the power bank.

**Lock policy** ([lock_logic.py](04_unoq_app/safe_app/python/lock_logic.py), shared by the board and the laptop version)
- **Steady answers only:** single guesses flicker while a hand moves, so a guess only counts when the network is at least **85% sure**, and a digit only counts when the same answer is held for **1 s**.
- **Waking up:** hold an **open palm** (5). It counts when at least 80% of the guesses in the last 1.2 s say 5, each at least 70% sure: more forgiving than a digit, because the palm can't open anything. It only counts after a fist or an empty box.
- **Between digits:** a **fist or an empty box for 0.5 s**. That stops one held finger from typing 1-1-1, and still allows repeated digits (1, fist, 1, fist, 2).
- **After 3 digits:** the right code unlocks. A wrong code is a strike; **3 strikes** in a row start a **30 s lockout**. **15 s** with no progress sends it back to sleep.
- **Locking again:** while open, a fist and then an open palm.
- **The code:** read from `safe_code.txt`, which stays out of Git. Without it the lock won't start.

**Latch**
- **Motor:** a TT motor through the Cytron Maker Drive (D9 and D10, speed 150 of 255). It has no position sensor, so every move is a timed run.
- **The wall is home:** LOCK runs **240 ms** out to 90°. UNLOCK runs 90 ms fast, then 450 ms at a slow speed (75), so the arm reaches the box wall gently and leans on it. The wall stops it in the same spot every time, which wipes out any drift.
- **Safe moves:** the sketch only moves when asked and ignores a repeat (a second LOCK would push the arm past 90°). At power-up it waits 3 s, homes against the wall and locks, so the safe always starts locked.

**Tamper alarm**
- **Sensor:** an MPU-6050 on the box floor, read by the sketch 100 times a second. Two movement numbers come out of it: **shake** (how far the acceleration jumps from its recent average, in thousandths of gravity, mg) and **turn** (how fast the box rotates, in °/s).
- **Rule ([tamper.py](04_unoq_app/safe_app/python/tamper.py)):** only while the latch is locked, **shake ≥ 80 mg or turn ≥ 12 °/s** sets off a 5 s alarm. The LED matrix flashes a warning, and the board's web page shows TAMPER ALERT and beeps. Movement while the latch moves, and for 1 s after, is ignored.
- **Calibrated on the real box:** still, at most 25 mg and 2 °/s; lifting the locked lid, 71-251 mg and 15-38 °/s; gentle taps (at most 64 mg, 11 °/s) are ignored on purpose.

**LED matrix**

| Pattern | Meaning |
|---|---|
| closed padlock | asleep and locked; a bar along the bottom fills while the open palm is held |
| three dim empty boxes | awake, ready for the code |
| boxes fill in | one box per digit entered (never the digits themselves) |
| bottom-row bar | fills while a digit or the fist is held |
| check mark, then open padlock | right code: unlocked |
| X | wrong code: a strike |
| seconds counting down, with "!" | lockout |
| "?" | the latch's state isn't known yet (starting up) |
| small camera | the webcam isn't working (unplugged, or not 640x480) |
| flashing warning triangle | tamper alarm |

### Board web server

The safe app serves port 7000 on the board (`http://Mohammed.local:7000` on the same Wi-Fi).

| Address | What it does |
|---|---|
| `GET /` | demo page: camera view with the crop box, the guess, LOCKED/UNLOCKED, the code dots, TAMPER ALERT with a beep (click the page once to allow sound) |
| `GET /status` | the latch's state (locked, unlocked, busy) and the lock's state |
| `GET /frame` | the latest camera picture for the demo page |
| `GET /guesses?secret=...` | the last 10 minutes of the network's guesses, for tuning |
| `GET /motion?secret=...` | the last 10 minutes of motion-sensor readings, for calibrating |
| `POST /unlock?secret=...`, `POST /lock?secret=...` | open or lock from the laptop (a backup) |

The secret word is in `link_secret.txt` (not in Git). The guess log needs it because it would reveal the code as it's entered.

## Hardware

- **Board:** an Arduino UNO Q. Its Linux side runs the camera, the network and the rules in Python; its microcontroller drives the motor, the LED matrix and the motion sensor. The two talk over the board's built-in Bridge.
- **Power and camera:** an Arduino USB-C hub. The webcam (icspring) plugs into its USB-A port, and a 5 V / 2.4 A power bank on its PD port powers the board and the camera.
- **Latch:** a Cytron Maker Drive (only channel 1 is used) and a TT gear motor turning the latch arm.
- **Tamper sensor:** an MPU-6050, stuck flat on the floor of the box away from the motor.
- **Box:** a laser-cut wooden box and latch arm.
- **Laptop:** used for collecting photos and training (and for the first, laptop version of the lock).

| From | To | What it does |
|---|---|---|
| Maker Drive M1A / M1B (inputs) | UNO Q D9 / D10 | speed signal (PWM) for each direction: one on and the other off turns the motor that way |
| Maker Drive GND | UNO Q GND | shared ground |
| Maker Drive VB+ / VB- | UNO Q 5V / GND | motor power |
| Motor wires | Maker Drive M1A / M1B (output terminals) | the motor itself |
| MPU-6050 VCC / GND | UNO Q 3.3V / GND | sensor power |
| MPU-6050 SCL / SDA | UNO Q SCL / SDA | I2C: the sketch reads the sensor |

## Files

```
MT2 - The Impenetrable Safe/
├── README.md, BUILD_LOG.md
├── 01_warmup_gradient_descent/   one neuron by hand, the same steps in Excel, two neurons in PyTorch
├── 02_data_collection/           webcam tool for labeled 128x128 finger photos (the photos stay off Git)
├── 03_training/                  the CNN, its training, plots and live test (laptop)
├── 04_unoq_app/                  the lock: laptop version, and safe_app/ for the UNO Q
├── 05_hardware_tests/            latch motor test app
├── 06_movie/                     the stop-motion movie of how the network works
└── media/                        photos of the finished safe and its LED matrix
```

| File | What it does |
|---|---|
| **01_warmup_gradient_descent/** | |
| [single_neuron.py](01_warmup_gradient_descent/single_neuron.py) | One ReLU neuron fitted to the V data, with the gradients written out by hand |
| [gradient_descent_5_iterations.xlsx](01_warmup_gradient_descent/gradient_descent_5_iterations.xlsx) | The same first 5 steps as live spreadsheet formulas |
| [two_neurons.py](01_warmup_gradient_descent/two_neurons.py) | A hidden layer of 2 ReLU neurons in PyTorch, compared with the single neuron |
| `annacode-v.tsv`, `*.png` | The V data (120 points, from Anna's Code) and the plots the scripts make |
| **02_data_collection/** | |
| [capture.py](02_data_collection/capture.py) | Live preview with the crop box; number keys 0-5 save labeled photos |
| [hand_crop.py](02_data_collection/hand_crop.py) | Forces 640x480, checks every frame, crops and shrinks to 128x128; shared by everything |
| `crop_config.json` | The saved crop box |
| **03_training/** | |
| [model.py](03_training/model.py) | The network (3 convolution layers + 1 linear) |
| [train.py](03_training/train.py) | Split, augmentation, training, plots and a score per photo session; saves `finger_cnn.pt` |
| [live_test.py](03_training/live_test.py) | Live webcam window with the network's guess and how sure it is |
| [feature_maps.py](03_training/feature_maps.py) | Pictures of what each layer "sees"; `feature_maps/overview.png` |
| `finger_cnn.pt`, `loss.png`, `accuracy.png`, `confusion_matrix.png`, `mistakes.png` | The trained network and its plots |
| **04_unoq_app/** | |
| [laptop_lock.py](04_unoq_app/laptop_lock.py) | The first version: the whole lock on the laptop, with SPACE and L keys, sending UNLOCK/LOCK to the board |
| [prepare_board_files.py](04_unoq_app/prepare_board_files.py) | Copies `hand_crop.py`, the crop box and the code into `safe_app/`, exports the network to numpy and checks it matches PyTorch |
| [safe_app/python/main.py](04_unoq_app/safe_app/python/main.py) | The board app: camera, network, rules, latch, LED matrix, alarm, web server |
| [safe_app/python/lock_logic.py](04_unoq_app/safe_app/python/lock_logic.py) | The lock's rules and timings |
| [safe_app/python/finger_net.py](04_unoq_app/safe_app/python/finger_net.py) | The network in plain numpy (`finger_net.npz` holds its trained numbers) |
| [safe_app/python/tamper.py](04_unoq_app/safe_app/python/tamper.py) | The tamper alarm rule and its calibrated thresholds |
| [safe_app/python/matrix_patterns.py](04_unoq_app/safe_app/python/matrix_patterns.py) | The LED matrix pictures |
| [safe_app/sketch/sketch.ino](04_unoq_app/safe_app/sketch/sketch.ino) | Microcontroller: the latch moves, the LED matrix and the motion sensor |
| [safe_app/assets/index.html](04_unoq_app/safe_app/assets/index.html) | The demo page |
| `safe_code.txt`, `safe_app/python/link_secret.txt` | The code and the secret word (both stay off Git) |
| **05_hardware_tests/** | |
| [latch_motor_test/sketch/sketch.ino](05_hardware_tests/latch_motor_test/sketch/sketch.ino) | Swings the latch back and forth, used to tune the moves (215 ms lock, tuned on laptop power) |
| **06_movie/** | |
| [make_stopmotion.py](06_movie/make_stopmotion.py) | Makes `how_the_network_works.mp4`: a 95 s paper-cutout stop-motion movie (12 fps, no sound) |
| [make_movie.py](06_movie/make_movie.py) | Computes every number in the movie from the real network on one real webcam frame (`source_frame.png`) |
| [clean_background.py](06_movie/clean_background.py) | Cleans a desk photo into `background_paper.png` |
| `scene_times.txt`, `training_loss.csv`, `safe_photo.jpg` | When each scene starts, the real loss per epoch, and the safe photo for the ending |
| **media/** | |
| `safe_closed.jpg`, `box_open.jpg`, `box_inside.jpg` | The finished safe: closed, with the lid open, and the electronics inside |
| `setup.jpg` | The whole setup: laptop, webcam stand over the red square, and the safe |
| `led_locked.jpg`, `led_awake.jpg`, `led_right_code.jpg`, `led_unlocked.jpg`, `led_wrong_code.jpg` | The LED matrix: padlock, ready boxes, check mark, open padlock, X |

## Setup and run

The laptop scripts use the repo's Python virtual environment. From the repo root:

```bash
source .venv/bin/activate
cd "Mohammed's Projects/MT2 - The Impenetrable Safe"
pip install -r 01_warmup_gradient_descent/requirements.txt -r 02_data_collection/requirements.txt -r 03_training/requirements.txt
```

Each stage, from the project folder:

```bash
python 01_warmup_gradient_descent/single_neuron.py           # warm-up (also two_neurons.py)
python 02_data_collection/capture.py --list                  # find the webcam's number
python 02_data_collection/capture.py --camera 1 --person mohammed   # take photos (keys 0-5)
python 03_training/train.py                                  # about 3 min; saves finger_cnn.pt and the plots
python 03_training/live_test.py                              # live guess window (q quits)
python 04_unoq_app/prepare_board_files.py                    # copy everything the board needs into safe_app/
python 06_movie/make_stopmotion.py                           # the movie (about 3 min)
```

In `capture.py`: `w a s d` move the box, `[ ]` resize it, `f` fits it to the red square, `c` saves it, `0`-`5` save photos, `q` quits.

**Deploying to the UNO Q.** The board apps are linked into the local `ArduinoApps` folder (`safe-app` points to `04_unoq_app/safe_app`, `latch-motor-test` to `05_hardware_tests/latch_motor_test`). Over USB, or over Wi-Fi without the cable:

```bash
cd ~/Documents/GitHub/ArduinoApps
export PATH="$HOME/Library/Arduino15/packages/arduino/tools/adb/32.0.0:$PATH"   # lets deploy.py find adb (USB)
python3 tools/deploy.py safe-app
python3 tools/deploy.py --cmd "arduino-app-cli properties set default /home/arduino/ArduinoApps/safe-app"   # start at power-on
```

The safe is the board's power-up app, so the power bank alone runs the lock: about a minute after power-on, the arm homes and locks and the padlock shows. `link_secret.txt` must exist before deploying (make one with `python3 -c "import secrets; print(secrets.token_urlsafe(24))" > 04_unoq_app/safe_app/python/link_secret.txt`).

**The laptop version** (webcam plugged into the laptop): `python 04_unoq_app/laptop_lock.py`. SPACE wakes the lock, L locks it again, q quits. It sends UNLOCK/LOCK to the board over USB first, then Wi-Fi (`Mohammed.local`).

**Finding the demo page on another network:** try `http://Mohammed.local:7000`. Campus Wi-Fi often blocks `.local` names, so on campus turn on the iPhone hotspot before powering the board (the board prefers it), or ask the board over USB: `python3 tools/deploy.py --cmd "ip -4 addr show wlan0"`. Classmates' boards also serve port 7000, so check that the page is titled "Impenetrable Safe" and shows your red square.

### How to open the safe

1. **Wake it:** hold an open palm over the red square for about 1 s. The padlock's bottom bar fills, then three empty boxes appear.
2. **Pause:** make a fist (or take your hand away) until the bar fills.
3. **First digit:** hold up 1 to 5 fingers, still, for 1 s. The first box fills.
4. **Fist again, then the next digit.** Repeat for the second and third digits.
5. **Open:** with the right code, a check mark shows and the latch swings open (open padlock). A wrong code shows an X and counts as a strike; after 3 strikes the safe waits 30 s.
6. **Lock again:** make a fist, then hold an open palm for about 1 s.

Keep your hand fully inside the red square, at the angles you used for the training photos.

## Tuning and notes

- **Constants:**
  - lock rules and timings: the top of [lock_logic.py](04_unoq_app/safe_app/python/lock_logic.py)
  - tamper thresholds: [tamper.py](04_unoq_app/safe_app/python/tamper.py)
  - latch moves (`LOCK_MS`, `UNLOCK_FAST_MS`, `SOFT_SPEED`, `UNLOCK_SOFT_MS`): [sketch.ino](04_unoq_app/safe_app/sketch/sketch.ino)
  - training settings: the top of [train.py](03_training/train.py)
  - guess rate and polling: the top of [main.py](04_unoq_app/safe_app/python/main.py)
- **Lock angle depends on power:** LOCK has no wall to stop against, so its angle depends on the motor's voltage. 240 ms reaches 90° on the power bank; on laptop USB power it was 215 ms (the latch test sketch still uses that).
- **Power-up:** the safe homes and locks at power-on, so the latch is open for about half a second during start-up.
- **Other hands:** every training photo is Mohammed's hand, but his roommate, whose hand was never in the training photos, tried the safe and opened it on his first try. Very different hands are still untested.
- **Hard poses:** a single fingertip at the very edge of the box reads as 0, and two fingers pointing down from the top edge can read as 3.

### Retraining the network

1. Take more photos with `capture.py`, with the webcam on the laptop in the same stand (check the green box still lines up with the red square; don't press `f` or `c`). Keep each class in one sitting: a gap over 30 minutes starts a new photo session.
2. Run `train.py`. It prints the best and typical validation scores and a score per session.
3. Run `prepare_board_files.py` (it stops if numpy and PyTorch disagree), move the webcam back to the hub, and deploy `safe-app`.

### The warm-up: one neuron vs. a V

- **Data:** the V from Anna's Code (`output = 2·|x − 60|` plus noise), rescaled to small numbers around 0.
- **One neuron draws a hockey stick:** flat at 0, then one straight ramp. A V needs two ramps, so the best one neuron can do is one side. It ends up on the right side because it starts at m = 1.
- **It gets stuck there:** the points on the left cause almost all of the remaining loss (0.0947 of 0.0950), but they sit on the neuron's flat part, where ReLU's slope is 0, so they add nothing to the gradient. The loss drops fast, then stays flat at 0.095.
- **Two neurons can fix it:** two hockey sticks added together can make both ramps of the V (`two_neurons.py` tries 10 random starts and keeps the best).
- **The same trap again:** a neuron that is flat for every input gets no gradient and stops learning. The same thing left 18 of 32 layer-3 filters dead in the first CNN, until better starting values fixed it.

The full record of what was tried, what failed and what fixed it is in [BUILD_LOG.md](BUILD_LOG.md).
