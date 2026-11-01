# How many steps? (HW7)

An ankle wearable that counts your steps and estimates how far you have gone, using a
neural net. An IMU (accelerometer + gyroscope) on an Arduino UNO Q is strapped to the
ankle, and a small PyTorch net trained on the laptop turns its motion data into a step
count and a distance, shown live on a dashboard.

## How it works

This section grows as the parts are built. So far there is a practice run on the HW6
data, a live dashboard running on fake data, the recorder for counted trials, and the
step counter trained on them.

### Recording counted trials

The board runs the **Step Recorder** app (`uno_q/`), controlled from a phone. For each
trial you pick a name and activity, press Start, stomp once, do the trial and press Stop.
The board saves the ankle IMU at 100 Hz as `Person_Activity_Tnn.csv`, then waits for the
real step count and distance typed in on the phone and adds a row to `trials.csv`. At the
same time the phone records its own accelerometer and gyroscope in a pocket with phyphox
(plus GPS on the outdoor walk). The stomp at the start of every trial shows up in both,
so the two recordings can be lined up later. `data/sync_from_board.py` copies the trials
to the laptop. Naming, columns and phyphox setup are in
[`data/README.md`](data/README.md).

### The step counter

`training/train_steps.py` trains the step counter on every good trial (each row of
`data/trials.csv` not listed in `data/excluded_trials.csv`) and tests it fairly:

1. Line up each ankle and phone recording on the stomp, and keep the moving stretch: from
   the ankle's first swing after the stomp to its last swing at the finish. Stand, Fidget
   and LegSwing keep everything after the stomp. (A stomp too soft for the checks, like
   seated LegSwing T04's, is taken as the biggest spike in the first 3 s.)
2. Cut it into 2 s clips, a new one every 0.5 s. Each clip's labels are its trial's step
   rate (steps ÷ moving time) and speed (distance ÷ moving time), 0 for the zero-step
   trials.
3. Describe each clip by the spread and peak of each channel, plus 10 numbers that don't
   depend on how the sensor sits on the leg: the spread and peak of the overall
   acceleration and rotation (whatever their direction), and the spread along the clip's
   own three main directions. That's 22 numbers for the ankle, 44 with the phone. No
   averages, since they mostly measure how the sensor is tilted.
4. Train a net, features → 16 → 16 → 2 (steps/s, m/s), with mean squared error, inputs
   rescaled on the training trials only, until the loss flattens.
5. Leave one trial out at a time: a committee of 5 nets trained without it estimates the
   trial's total steps and distance (rate × 0.5 s, added up over its clips), with the
   spread between the 5 as the ±. Done for ankle only and for ankle + phone, next to a
   plain peak counter (2 × the right leg's swings).
6. Save the plots, the error table (`training/results.md`) and `training/step_model.npz`:
   the ankle-only committee trained on all good trials, which runs with plain numpy
   (`numpy_predict` in the script), so the UNO Q doesn't need PyTorch.

### Practice: activity classifier on HW6 data

`training/practice_classifier.py` trains a small PyTorch net to recognize standing,
walking, running and biking from the recordings in
[`Gait Identifier/data/raw`](../Gait%20Identifier/data/raw):

1. Trim 2 s off both ends of each recording and cut the rest into back-to-back 2 s clips
   (200 samples at 100 Hz).
2. Describe each clip with 18 numbers: the average, spread (standard deviation) and peak
   (largest absolute value) of each of the 6 IMU channels.
3. Set aside one whole recording per activity for testing, so no recording has clips in
   both the training and the test set.
4. Rescale the features (measured on the training clips only) and train a net with
   18 inputs → 16 → 16 → 4 activities (ReLU, Adam, class-weighted cross-entropy).
5. Save the loss plot to `media/practice_loss.png`, and print the test accuracy and a
   confusion matrix.

### Live dashboard

The wearable will publish one JSON message twice a second over MQTT (`broker.hivemq.com`,
topic `ME193/Mohammed/steps`) with the step count, distance, both ± uncertainties,
cadence, speed and the values of the net's two hidden layers. `dashboard/index.html`
subscribes over WebSockets and shows it all live. Until the UNO Q sends real data,
`dashboard/fake_publisher.py` sends realistic made-up messages. The message format is
in [`dashboard/README.md`](dashboard/README.md).

## Hardware

- Arduino UNO Q with an MPU-6050 IMU on I2C, wired as in
  [HW6](../Gait%20Identifier/README.md), strapped to the right lower leg near the ankle
- USB power bank, so the board runs without the laptop
- A phone: controls the recorder (port 7000) and records its own sensors with
  [phyphox](https://phyphox.org)
- A measured 20 m course

## Files

```
How Many Steps/
├── data/
│   ├── raw/                     ankle recordings, one CSV per trial
│   ├── phone_raw/               phone recordings: one folder per trial, zips in original_zips/
│   ├── trials.csv               real step count and distance for each trial
│   ├── excluded_trials.csv      damaged trials left out of training, with the reason
│   ├── real_durations.csv       real length and sample rate of each ankle recording
│   ├── sync_from_board.py       copies the trials from the board
│   ├── check_recordings.py      damage checks, stomp alignment, one plot per trial
│   ├── RECORDING_CHECKLIST.md   step by step, for the phone during recording
│   └── README.md                naming, columns, phyphox setup, the stomp
├── training/
│   ├── train_steps.py           the step counter: training and leave-one-trial-out test
│   ├── step_model.npz           trained ankle-only committee, for plain numpy on the UNO Q
│   ├── results.md               errors per pace
│   ├── results_per_trial.csv    every held-out trial's estimates
│   ├── practice_classifier.py   practice net on the HW6 data
│   └── requirements.txt         laptop packages for training
├── uno_q/                       Step Recorder app for the UNO Q (see its README)
├── dashboard/
│   ├── index.html               live dashboard page (open in a browser)
│   ├── fake_publisher.py        fake data until the hardware exists
│   └── README.md                the MQTT message format
└── media/
    ├── train_loss.png           step counter's loss while training
    ├── steps_est_vs_true.png    estimated vs true steps and distance, per held-out trial
    ├── practice_loss.png        loss curve from the practice run
    └── recording_checks/        one plot per trial: ankle and phone, lined up on the stomp
```

## Setup and run

From the repo root, with `.venv` active:

```
pip install -r "Mohammed's Projects/How Many Steps/training/requirements.txt"
cd "Mohammed's Projects/How Many Steps/training"
python train_steps.py            # step counter, about 1.5 min
python practice_classifier.py    # practice run on the HW6 data
```

Dashboard on fake data (from the repo root; `paho-mqtt` is in
`Mohammed's Projects/requirements.txt`):

```
python "Mohammed's Projects/How Many Steps/dashboard/fake_publisher.py"
open "Mohammed's Projects/How Many Steps/dashboard/index.html"
```

Step Recorder: from the ArduinoApps kit, `python3 tools/deploy.py step-recorder` (its
`step-recorder` folder is a symlink to `uno_q/`). It is the board's default app, so it
starts on power-up and scrolls its address on the LED matrix. The board joins home Wi-Fi
or Phone 2's hotspot, whichever it finds; the one-time board setup (address service,
hotspot, default app) is in [`uno_q/README.md`](uno_q/README.md). After recording, from the repo root:

```
python "Mohammed's Projects/How Many Steps/data/sync_from_board.py"
```

## Tuning and notes

- Recordings take about 0.9 MB per minute on the board, which has about 15 GB free.
- Leave the recordings on the board after syncing: trial numbers come from the files
  there, so deleting them would reuse numbers.
- `Outdoor` phone zips contain GPS positions, so they are kept off GitHub.

- Step counter, leave-one-trial-out on 39 trials (`training/results.md` has the full
  table): on walks and runs the ankle-only net is off by about 0.5-0.7 steps per trial
  (1.7-3.4%) and 0.4-1.4 m of 20 m; 1.5 steps per trial over all trials. The peak counter does well on most walks but
  double-counts some fast walks, overcounts runs (41% and 13% off) and counts leg swings
  as steps. Adding the phone barely changes walks and runs.
- Leg swings: with 8 LegSwing trials (sitting and standing, slow, fast and small), every
  held-out one comes out at 0-4 steps except LegSwing T03, at about 27. Its swing turns the
  sensor around the same axis as walking does (it was recorded with the sensor strapped
  as for that session's walks). Per-axis features depend on how the sensor sits on the
  leg, which is why the 10 direction-free features were added: with only the per-axis
  ones, T03 came out at 64 steps and the error over all trials was 2.3 steps per trial
  (1.5 now), while walks and runs stayed within 0.1 step per trial of the current numbers.
  `FEATURE_SET` at the top of `train_steps.py` switches back.
- The dashboard's ± is the leave-one-out error per pace (e.g. about 3% of the steps on a
  walk, 5% on a run), saved in `step_model.npz`, not the spread between the committee's 5
  nets. The nets agree with each other much more closely than with the truth (a spread of
  0.2-1.3 steps per trial, with the real error over twice that in 12 of 39 trials and up
  to 27 steps), so a ± from their spread would look confident and be wrong. Details in
  [`dashboard/README.md`](dashboard/README.md).
- The step counter's settings (clip length, layer size, learning rate, when to stop, the
  peak counter's thresholds) are constants at the top of `train_steps.py`.
- The practice run's settings (clip length, hidden layer size, epochs, learning rate,
  random seed) are constants at the top of `practice_classifier.py`.
- With only 4 test recordings, the accuracy depends a lot on which recordings are held
  out. The default seed scores 100%, but other seeds range from 58% to 98%. Testing on
  every recording in turn (leave-one-recording-out) gives 88.5% with all 18 features and
  96.5% without the 6 averages. The averages mostly record how the board was tilted on
  the leg, the same problem Model 2 v1 had in HW6.
