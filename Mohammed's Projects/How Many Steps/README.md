# How many steps? (HW7)

An ankle wearable that counts your steps and estimates how far you have gone, using a
neural net. An IMU (accelerometer + gyroscope) on an Arduino UNO Q is strapped to the
ankle, and a small PyTorch net trained on the laptop turns its motion data into a step
count and a distance, shown live on a dashboard.

## How it works

The project is just starting, so this section will grow as the parts are built. So far
there is a practice run on the HW6 data, a live dashboard running on fake data, and the
recorder for counted trials.

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
│   ├── phone_raw/               phyphox exports, one zip per trial
│   ├── trials.csv               real step count and distance for each trial
│   ├── sync_from_board.py       copies the trials from the board
│   ├── RECORDING_CHECKLIST.md   step by step, for the phone during recording
│   └── README.md                naming, columns, phyphox setup, the stomp
├── training/
│   ├── practice_classifier.py   practice net on the HW6 data
│   └── requirements.txt         laptop packages for training
├── uno_q/                       Step Recorder app for the UNO Q (see its README)
├── dashboard/
│   ├── index.html               live dashboard page (open in a browser)
│   ├── fake_publisher.py        fake data until the hardware exists
│   └── README.md                the MQTT message format
└── media/
    └── practice_loss.png        loss curve from the practice run
```

## Setup and run

From the repo root, with `.venv` active:

```
pip install -r "Mohammed's Projects/How Many Steps/training/requirements.txt"
cd "Mohammed's Projects/How Many Steps/training"
python practice_classifier.py
```

Dashboard on fake data (from the repo root; `paho-mqtt` is in
`Mohammed's Projects/requirements.txt`):

```
python "Mohammed's Projects/How Many Steps/dashboard/fake_publisher.py"
open "Mohammed's Projects/How Many Steps/dashboard/index.html"
```

Step Recorder: from the ArduinoApps kit, `python3 tools/deploy.py step-recorder` (its
`step-recorder` folder is a symlink to `uno_q/`). It is the board's default app, so it
starts on power-up. After recording, from the repo root:

```
python "Mohammed's Projects/How Many Steps/data/sync_from_board.py"
```

## Tuning and notes

- Recordings take about 0.9 MB per minute on the board, which has about 15 GB free.
- Leave the recordings on the board after syncing: trial numbers come from the files
  there, so deleting them would reuse numbers.
- `Outdoor` phone zips contain GPS positions, so they are kept off GitHub.

- The settings (clip length, hidden layer size, epochs, learning rate, random seed) are
  constants at the top of `practice_classifier.py`.
- With only 4 test recordings, the accuracy depends a lot on which recordings are held
  out. The default seed scores 100%, but other seeds range from 58% to 98%. Testing on
  every recording in turn (leave-one-recording-out) gives 88.5% with all 18 features and
  96.5% without the 6 averages. The averages mostly record how the board was tilted on
  the leg, the same problem Model 2 v1 had in HW6.
