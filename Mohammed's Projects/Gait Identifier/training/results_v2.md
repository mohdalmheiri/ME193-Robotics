# Gait Identifier: results, version 2

Produced by `python train.py` (second version). Same data, windows and test as
[results_v1.md](results_v1.md): 12 recordings, 1412 windows of 2 s sliding by 0.5 s,
leave-one-recording-out. Model 1 and Model 2 v1 are unchanged; v2 is new.

## What changed: tilt-free features

Model 2 v1 failed because its accelerometer mean/min/max mostly measured tilt (how the board
was strapped on), not the activity. v2 uses only the **magnitude** (the length of the
x, y, z arrow, sqrt(x² + y² + z²)), which stays the same however the board is turned:

- Total acceleration magnitude: mean, std, max, dominant frequency
- Total rotation (gyro) magnitude: mean, std, max, dominant frequency
- Dominant frequency of whichever gyro axis swings the most in the window

9 features, same tree settings as v1 (max depth 4, `class_weight="balanced"`).

## Accuracy

| Model | Features | Accuracy | Standing | Walking | Running | Biking |
|---|---|---|---|---|---|---|
| Model 1 | peak \|ay\|, thresholds | 79.8% | 100% | 94% | 0% | 100% |
| Model 2 v1 | 30 per-axis features | 65.2% | 100% | 0% | 89% | 100% |
| **Model 2 v2** | **9 tilt-free features** | **88.2%** | 100% | 68% | 95% | 97% |

## Confusion matrix, Model 2 v2 (rows = true activity, columns = predicted)

| True \ Predicted | Standing | Walking | Running | Biking |
|---|---|---|---|---|
| Standing | 475 | 0 | 0 | 0 |
| Walking | 1 | 315 | 145 | 1 |
| Running | 0 | 12 | 244 | 1 |
| Biking | 0 | 0 | 7 | 211 |

Figures: `figures/model2_confusion_matrix_v2.png`, `figures/model2_decision_tree_v2.png`.

## What the v2 tree uses

Share of the tree's decisions per feature: acc_mag_std 59%, gyro_mag_mean 34%,
gyro_mag_std 4%, gyro_mag_dom_freq 3%. Not used: acc_mag_mean, acc_mag_dom_freq and
gyro_top_axis_dom_freq. Small splits on gyro_mag_max and acc_mag_max carry almost no weight.

1. **Is the leg rotating?** gyro_mag_mean ≤ 21 °/s → Standing (Standing ≈ 4 °/s, everything
   else ≥ 90 °/s).
2. **How much does the total jolt vary?** acc_mag_std: about 0.25 g walking, 0.5 g running,
   0.85 g biking.
3. **Smooth or jerky rotation?** gyro_mag_std separates Biking (steady pedalling circle) from
   Running (stop-start swing) when both jolt a lot.

acc_mag_mean is unused because it is always about 1 g (gravity). Rhythm barely helps: a 2 s
window only resolves frequency in 0.5 Hz steps, too coarse to tell step rates apart.

## Per-recording accuracy, Model 2 v2

| Recording | Correct |
|---|---|
| Biking 011031 / 011137 / 011306 / 011424 | 91% / 100% / 98% / 100% |
| Running 005452 / 005641 / 010258 / 010411 | 58% / 98% / 97% / 99% |
| Standing 004048 / 011929 | 100% / 100% |
| Walking 004331 / 012135 | 95% / 41% |

## Remaining weaknesses

- **Walking called Running (31%)** comes almost entirely from Walking 012135. Its median
  rotation is 124 °/s vs 91 °/s in the other walk, close to running (130–175 °/s). With only
  two Walking recordings, holding one out leaves a single walk to learn from.
- **Running 005452** is the short 15 s run, and it jolts as hard as biking.
- Next step: more Walking recordings at different speeds.
