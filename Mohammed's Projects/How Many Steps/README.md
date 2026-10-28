# How many steps? (HW7)

An ankle wearable that counts your steps and estimates how far you have gone, using a
neural net. An IMU (accelerometer + gyroscope) on an Arduino UNO Q is strapped to the
ankle, and a small PyTorch net trained on the laptop turns its motion data into a step
count and a distance, shown live on a dashboard.

## How it works

The project is just starting, so this section will grow as the parts are built. So far
there is a practice run on the HW6 data (no new hardware yet).

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

## Hardware

Not built yet. The plan is the HW6 setup worn at the ankle: an IMU and an Arduino UNO Q
with a power bank.

## Files

```
How Many Steps/
├── data/          new HW7 recordings (empty for now)
├── training/
│   ├── practice_classifier.py   practice net on the HW6 data
│   └── requirements.txt         laptop packages for training
├── uno_q/         the UNO Q app (empty for now)
├── dashboard/     live step count and distance (empty for now)
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

## Tuning and notes

- The settings (clip length, hidden layer size, epochs, learning rate, random seed) are
  constants at the top of `practice_classifier.py`.
- With only 4 test recordings, the accuracy depends a lot on which recordings are held
  out. The default seed scores 100%, but other seeds range from 58% to 98%. Testing on
  every recording in turn (leave-one-recording-out) gives 88.5% with all 18 features and
  96.5% without the 6 averages. The averages mostly record how the board was tilted on
  the leg, the same problem Model 2 v1 had in HW6.
