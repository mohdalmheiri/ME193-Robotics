# How many steps? (HW7)

An ankle wearable that counts your steps and estimates how far you have gone, using a
neural net. An IMU (accelerometer + gyroscope) on an Arduino UNO Q is strapped to the
ankle, and a small PyTorch net trained on the laptop turns its motion data into a step
count and a distance, shown live on a dashboard.

## How it works

The board records counted trials, a net is trained on them on the laptop, and the
trained net then runs live on the board, counting steps and distance and sending them
to the dashboard. There is also a practice run on the HW6 data.

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
3. Describe each clip by 10 numbers that don't depend on how the sensor sits on the leg:
   the spread and peak of the overall acceleration and rotation (whatever their
   direction), and the spread along the clip's own three main directions. That's 10
   numbers for the ankle, 20 with the phone. No averages, since they mostly measure how
   the sensor is tilted. (An earlier version also used the spread and peak of each sensor
   axis, 22 in all; see the notes for why it was dropped.)
4. Train a net, features → 16 → 16 → 2 (steps/s, m/s), with mean squared error, inputs
   rescaled on the training trials only, until the loss flattens.
5. Leave one trial out at a time: a committee of 5 nets trained without it estimates the
   trial's total steps and distance (rate × 0.5 s, added up over its clips), with the
   spread between the 5 as the ±. Done for ankle only and for ankle + phone, next to a
   plain peak counter (2 × the right leg's swings).
6. Save the plots, the error table (`training/results.md`) and `training/step_model.npz`:
   the ankle-only committee trained on all good trials, which runs with plain numpy
   (`numpy_predict` in the script), so the UNO Q doesn't need PyTorch.

### Counting live on the UNO Q

The Step Recorder app counts steps all the time, recording or not
(`uno_q/python/step_counter.py`, plain numpy):

1. It keeps the last 2 s of ankle samples. Every 0.5 s (50 new samples, so the clips
   are spaced exactly as in training), it computes the same features as training (the
   model file says which set: now the 10 direction-free ones).
2. It runs the 5-net committee from `step_model.npz` (which `train_steps.py` also
   copies into `uno_q/python/`), and adds rate × 0.5 s to the steps and speed × 0.5 s
   to the distance, plus the per-pace ±.
3. The running count goes to the LED matrix, the Step Recorder page (with a Reset
   button) and the dashboard, as the MQTT message in `dashboard/README.md`, with net 1's
   two hidden layers as `layer1`/`layer2`.
4. Every saved trial also stores its live count from Start to Stop, in
   `live_counts.csv`, so it can be compared with the real count.

`training/check_live_math.py` feeds saved recordings through the board's code in
10-sample batches, as the board receives them, and checks that every clip's features
and outputs match `train_steps.py` (they're identical).

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
│   ├── live_counts.csv          the board's live count for each trial (since it counts live)
│   ├── test_paces.csv           pace of each counted Test walk on the course
│   ├── demo_walks.csv           demo walks shown on the dashboard (real vs shown count)
│   ├── excluded_trials.csv      damaged trials left out of training, with the reason
│   ├── trial_corrections.csv    fixes to wrong counts or distances in trials.csv, with the reason
│   ├── real_durations.csv       real length and sample rate of each ankle recording
│   ├── sync_from_board.py       copies the trials from the board
│   ├── check_recordings.py      damage checks, stomp alignment, one plot per trial
│   ├── RECORDING_CHECKLIST.md   step by step, for the phone during recording
│   └── README.md                naming, columns, phyphox setup, the stomp
├── training/
│   ├── train_steps.py           the step counter: training and leave-one-trial-out test
│   ├── check_live_math.py       checks the board's live math matches training
│   ├── evaluate_tests.py        how the live count did on the counted Test walks
│   ├── test_results.csv         every Test walk: live vs real count and distance
│   ├── step_model.npz           trained ankle-only committee, for plain numpy on the UNO Q
│   ├── step_model_22features.npz   the earlier 22-feature committee, kept for comparison
│   ├── results_per_trial_22features.csv   its leave-one-out results
│   ├── results.md               errors per pace
│   ├── results_per_trial.csv    every held-out trial's estimates
│   ├── practice_classifier.py   practice net on the HW6 data
│   └── requirements.txt         laptop packages for training
├── uno_q/                       Step Recorder app: recording and live counting (see its README)
├── dashboard/
│   ├── index.html               live dashboard page (open in a browser)
│   ├── fake_publisher.py        fake data until the hardware exists
│   └── README.md                the MQTT message format
└── media/
    ├── train_loss.png           step counter's loss while training
    ├── steps_est_vs_true.png    estimated vs true steps and distance, per held-out trial
    ├── test_walks.png           the live count's error on each counted 20 m Test walk (before the fix)
    ├── test_walks_after_fix.png the same for the walks after the fix
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

- **Before the fix:** live on the board with the 22-feature model, 12 counted walks on
  the 20 m course (3 per pace, Test T06-T17; `training/results.md`,
  `media/test_walks.png`): the live count came out **low**, by
  14% of the steps overall (slow 10%, normal 20%, fast 18%, run 7%) and 15% of the
  distance, against the 2-3% the leave-one-out test predicted. Only 2 of 12 walks were
  within the live ±. The cause is the sensor's angle on the leg: for these walks it sat
  20-68° away from every training session (after the wiring repair), and 12 of the 22
  features are measured per sensor axis. Retrained on only the 10 direction-free
  features, the same committee counts these walks within 0.6 steps on average (3.1 with
  all 22). The peak counter was right on most slow and normal walks but double-counted 3
  walks (+22 to +26 steps).
- **The fix:** the counter now uses only the 10 direction-free features. In the
  leave-one-out test it's as accurate overall as the 22-feature model (1.5 steps per
  trial, 7.5%) and better on zero-step trials (3.2 vs 3.7 steps), but slightly worse on
  walks and runs (0.7-1.0 vs 0.5-0.7 steps per trial, 1.8-4.4% vs 1.7-3.5%): the
  per-axis features helped when the sensor sat as in training. The 22-feature model is
  kept as `training/step_model_22features.npz`, with its results in
  `results_per_trial_22features.csv`. Test T06-T17 chose this fix, so they can't test it
  fairly; new test walks from Test T18 on are the fair test (`evaluate_tests.py` reports
  them separately, as "after the fix").
- **After the fix:** 12 fresh counted walks on the 20 m course plus a 30 s leg swing
  (Test T18-T30; `training/results.md`, `media/test_walks_after_fix.png`). The live count
  was off by 3.0% of the steps overall, as the leave-one-out test expected (3.1%), down
  from 14.2% before the fix: slow walks 2.7%, normal 1.7%, fast 0.7%, runs 9.4%. Distance
  was off by 6.9% (5.4% expected), down from 14.5%. 10 of the 13 walks were within the
  live ±. The leg swing gave 0.2 false steps (the peak counter counted 48).
- **Demo:** in the apartment lobby (on video, saved outside the repo), 39 steps counted
  silently showed as 38 on the dashboard (2.6% off). The board needed a restart before it
  connected to the dashboard over Phone 2's hotspot.
- Runs and one slow walk came out low because Stop was pressed right at the last step.
  Each live clip looks back 2 s, so the last second or so of walking or running isn't
  counted until after Stop. Counted over the whole recording, Run T18 is 15.4 steps (16
  true) against 12.9 live. Standing still for 2 s before pressing Stop avoids this.
- The ± is training's typical error per pace, so it only holds when the sensor sits as
  it did in training. A new sensor angle is an error it doesn't cover.
- Live on the board, three counted walks around the apartment (Test T01-T03, 46, 31 and
  62 steps) came out at 48.5 ± 2.4, 34.6 ± 1.4 and 61.5 ± 2.1. Replaying the recordings
  shows where the extra comes from: during the walking itself the count was within 0.4,
  0.1 and 1.6 steps, and the stomp, standing still and stopping add 1-4 steps per trial,
  since training never saw the stomp. The live count runs nonstop, so those moments count
  too.
- Step counter, leave-one-trial-out on 39 trials (`training/results.md` has the full
  table): on walks and runs the ankle-only net is off by about 0.7-1.0 steps per trial
  (1.8-4.4%) and 0.6-1.6 m of 20 m; 1.5 steps per trial over all trials. The peak
  counter does well on most walks but
  double-counts some fast walks, overcounts runs (41% and 13% off) and counts leg swings
  as steps. Adding the phone barely changes walks and runs.
- Leg swings: with 8 LegSwing trials (sitting and standing, slow, fast and small), the
  held-out ones come out at 0-10 steps. LegSwing T03, whose swing turns the sensor the way
  walking does, went from 64 steps (per-axis features only) to 27 (22 features) to about
  1 now; LegSwing T05 and T09 (big and mixed swings) are the highest now, at about 10.
  `FEATURE_SET` at the top of `train_steps.py` switches between the feature sets.
- The dashboard's ± is the leave-one-out error per pace (e.g. about 2-4% of the steps on
  a walk, 5% on a run), saved in `step_model.npz`, not the spread between the committee's
  5 nets. The nets agree with each other much more closely than with the truth (a spread
  of 0.3-1.9 steps per trial, with the real error over twice that in 12 of 39 trials and
  up to 10 steps), so a ± from their spread would look confident and be wrong. Details in
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
