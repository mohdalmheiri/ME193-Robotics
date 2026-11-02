# Gait Identifier: results, version 3 (more data)

Produced by `python train.py` on all recordings. Same models, features, windows and
leave-one-recording-out test as [results_v2.md](results_v2.md); only the data changed.

## New data

7 new recordings (all Mohammed), added to the 12 old ones:

| Recording | What | Seconds |
|---|---|---|
| Walking 020548 / 020656 / 020802 | slow / normal / fast walk, same strap as before | 63.7 / 62.2 / 62.2 |
| Standing 021140 | after re-strapping the board | 62.5 |
| Walking 021249 | after re-strapping | 61.2 |
| Running 021356 | after re-strapping | 61.5 |
| Biking 021508 | after re-strapping | 38.1 |

| | Old data | New data |
|---|---|---|
| Recordings (Standing / Walking / Running / Biking) | 12 (2 / 2 / 4 / 4) | 19 (3 / 6 / 5 / 5) |
| Windows (2 s, sliding 0.5 s) | 1412 | 2155 (589 / 915 / 368 / 283) |

## Comparison: old data vs new data (leave-one-recording-out)

| Model | Data | Accuracy | Standing | Walking | Running | Biking |
|---|---|---|---|---|---|---|
| Model 1 (peak \|ay\|) | old, 12 rec. | 79.8% | 100% | 94% | 0% | 100% |
| Model 1 (peak \|ay\|) | new, 19 rec. | 74.6% | 81% | 93% | 0% | 100% |
| Model 2 v1 (30 per-axis) | old, 12 rec. | 65.2% | 100% | 0% | 89% | 100% |
| Model 2 v1 (30 per-axis) | new, 19 rec. | **96.1%** | 100% | 93% | 94% | 100% |
| Model 2 v2 (9 tilt-free) | old, 12 rec. | 88.2% | 100% | 68% | 95% | 97% |
| Model 2 v2 (9 tilt-free) | new, 19 rec. | **95.5%** | 100% | 93% | 93% | 98% |

The gap between v1 and v2 on new data (0.6 points, about 13 of 2155 windows) is too small to
call either one better.

## Two extra checks

**1. The deployed models on recordings they had never seen.** Before retraining, the models
trained on the old 12 recordings (the ones running on the board) were tested on the 7 new
recordings:

| Model | Accuracy on the 7 new recordings |
|---|---|
| Model 1 | 80.2% |
| Model 2 v2 | 94.8% (fast walk: 73%, 27% called Running) |

**2. A new strap.** Leave-one-recording-out never holds out a whole strapping. To test that,
each model was trained on the other 15 recordings and tested on the 4 recorded after
re-strapping:

| Model | Re-strapped 4 | Standing | Walking | Running | Biking |
|---|---|---|---|---|---|
| Model 1 | 40.9% | 0% | 89% | 0% | 100% |
| Model 2 v1 | 98.5% | 100% | 100% | 95% | 100% |
| Model 2 v2 | 98.5% | 100% | 100% | 95% | 100% |

These two checks were one-off scripts, not part of `train.py`.

## Confusion matrices, new data (rows = true activity, columns = predicted)

Model 1 (peak |ay|):

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 475 | 114 | 0 | 0 |
| Walking | 6 | 850 | 0 | 59 |
| Running | 0 | 29 | 0 | 339 |
| Biking | 0 | 0 | 0 | 283 |

Model 2 v1 (30 per-axis features):

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 589 | 0 | 0 | 0 |
| Walking | 0 | 852 | 63 | 0 |
| Running | 0 | 21 | 347 | 0 |
| Biking | 0 | 0 | 0 | 283 |

Model 2 v2 (9 tilt-free features):

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 589 | 0 | 0 | 0 |
| Walking | 0 | 850 | 65 | 0 |
| Running | 0 | 25 | 343 | 0 |
| Biking | 0 | 0 | 7 | 276 |

Figures (regenerated): `figures/model1_confusion_matrix.png`, `figures/model1_peak_histogram.png`,
`figures/model2_confusion_matrix.png`, `figures/model2_decision_tree.png`,
`figures/model2_confusion_matrix_v2.png`, `figures/model2_decision_tree_v2.png`.

## Per-recording accuracy for the new recordings (leave-one-recording-out)

| Recording | Model 1 | Model 2 v1 | Model 2 v2 |
|---|---|---|---|
| Walking 020548 (slow) | 95% | 100% | 100% |
| Walking 020656 (normal) | 90% | 100% | 100% |
| Walking 020802 (fast) | 93% | 93% | **55%** |
| Standing 021140 (re-strapped) | **0%** | 100% | 100% |
| Walking 021249 (re-strapped) | 89% | 100% | 100% |
| Running 021356 (re-strapped) | 0% | 95% | 95% |
| Biking 021508 (re-strapped) | 100% | 100% | 100% |

## Final trained models (fit on all 19 recordings; deployed: Model 1 and Model 2 v2)

- **Model 1** thresholds on peak |ay|: ≤ 0.32 g Standing, 0.32–1.99 g Walking, > 1.99 g Biking
  (was 0.31 / 2.00). Running still never gets a band.
- **Model 2 v2** uses acc_mag_std (57% of the tree's decisions), gyro_mag_mean (35%),
  gyro_mag_std (5%), gyro_mag_dom_freq (2%) and acc_mag_max (1%). Its first two questions are the
  same as before: rotation ≤ 21 °/s → Standing, then how much the jolt varies.
  One small leaf (acc_mag_max > 15.5 g → Walking) catches a few windows where the sensor hit
  its ±16 g limit; it affects very few windows.

## What changed and why

- **Model 2 v2 improved (88% → 96%)** because Walking went from 2 recordings to 6. Holding
  one out now leaves five walks at different speeds and straps to learn from, not one.
- **Model 2 v1 recovered (65% → 96%)** for the same reason. Its tilt features (ay_mean) only
  failed because each activity had been recorded at a single strap angle; with recordings
  from three strappings, tilt alone no longer singles out one activity. It still depends on
  the strap angles it has seen, while v2 doesn't look at tilt at all.
- **Model 1 got worse (80% → 75%).** After re-strapping, gravity points partly along ay, so
  standing still already reads above the 0.32 g Standing limit (re-strapped Standing: 0%).
  Running and Biking peaks still overlap, so Running is never predicted.
- **Remaining weak spot: fast walking vs running.** A fast walk jolts nearly as much as a
  slow run, and a 2 s window measures rhythm too coarsely (0.5 Hz steps) to separate their
  step rates.
