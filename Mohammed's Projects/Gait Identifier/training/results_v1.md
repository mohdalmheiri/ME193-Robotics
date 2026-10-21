# Gait Identifier: results, version 1

Produced by `python train.py` (first version).

## Data and test

- 12 recordings from one person (Mohammed): Standing 2, Walking 2, Running 4, Biking 4
- Each recording trimmed by 2 s at both ends, then cut into 2 s windows (200 samples at
  100 Hz) sliding by 0.5 s: **1412 windows** (Standing 475, Walking 462, Running 257, Biking 218)
- **Leave-one-recording-out**: train on 11 recordings, test on the one left out, repeat for
  all 12. All accuracies below are on recordings the model never saw during training.

## Accuracy

| Model | Features | Accuracy |
|---|---|---|
| Model 1 | peak \|ay\| in the window, up to 3 thresholds (depth-2 tree) | **79.8%** |
| Model 2 v1 | mean, std, min, max, dominant frequency of all 6 channels (30 features), depth-4 tree | **65.2%** |

Model 1 axis comparison: ax 15.2%, ay 79.8%, az 29.5%, so ay was kept.

## Per-activity accuracy (recall)

| Activity | Model 1 | Model 2 v1 |
|---|---|---|
| Standing | 100% | 100% |
| Walking | 94% | 0% |
| Running | 0% | 89% |
| Biking | 100% | 100% |

## Confusion matrices (rows = true activity, columns = predicted)

Model 1 (peak |ay| thresholds):

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 475 | 0 | 0 | 0 |
| Walking | 0 | 434 | 0 | 28 |
| Running | 0 | 24 | 0 | 233 |
| Biking | 0 | 0 | 0 | 218 |

Model 2 v1 (all-channel decision tree):

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 475 | 0 | 0 | 0 |
| Walking | 1 | 0 | 461 | 0 |
| Running | 0 | 29 | 228 | 0 |
| Biking | 0 | 0 | 0 | 218 |

Figures: `figures/model1_confusion_matrix.png`, `figures/model2_confusion_matrix.png`,
`figures/model1_peak_histogram.png`, `figures/model2_decision_tree.png`.

## Final trained models (fit on all 12 recordings)

- **Model 1** learned only 2 thresholds on peak |ay|: ≤ 0.31 g Standing, 0.31–2.00 g Walking,
  > 2.00 g Biking. Running never gets a band.
- **Model 2 v1** splits on ay_std, ay_mean, ay_min, gz_min and fits the training data at 99%.

## What went wrong

**Model 1: Running vs Biking.** The middle 80% of peak |ay| values per activity:

| Activity | Peak \|ay\| |
|---|---|
| Standing | 0.03–0.11 g |
| Walking | 0.94–1.80 g |
| Running | 2.08–3.66 g |
| Biking | 2.49–3.32 g |

Running and Biking peaks overlap almost completely, so no threshold on this one number can
separate them.

**Model 2 v1: Walking called Running.** The tree relies on the accelerometer mean/min/max,
which mostly measure tilt (which way gravity points), i.e. how the board was strapped on.
The two Walking recordings were made at different angles (median ax mean −0.81 g vs −0.05 g).
With one held out, the tree learns "Walking = the other recording's angle", so the held-out
walk is called Running. Removing the accelerometer mean/min/max raised the same test to
83.1%, which points to tilt, not the activity, as the problem.
