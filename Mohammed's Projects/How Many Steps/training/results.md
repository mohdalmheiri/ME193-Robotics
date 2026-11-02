# Step counter: leave-one-trial-out results

Written by `train_steps.py`, features: direction_free (10 per sensor). 39 good trials, 1775 clips of 2 s. Each trial's totals come from a committee of 5 nets trained without it. Errors are the mean absolute error per trial, and in brackets the total error as a % of the true total. The +/- is the spread between the committee's nets.

| Pace | Trials | Steps error: ankle only | Steps error: ankle + phone | Steps error: peak counter | Distance error: ankle only | Distance error: ankle + phone | Typical +/- (ankle only) |
|---|---|---|---|---|---|---|---|
| Walk_slow | 7 | 0.7 (1.8%) | 0.8 (2.1%) | 0.9 (2.3%) | 0.6 (3.1%) m | 0.8 (4.1%) m | 0.4 steps, 0.3 m |
| Walk_normal | 7 | 1.0 (3.2%) | 0.9 (2.9%) | 1.4 (4.5%) | 0.8 (3.9%) m | 0.7 (3.6%) m | 0.6 steps, 0.5 m |
| Walk_fast | 7 | 0.8 (3.1%) | 1.1 (4.3%) | 10.0 (40.7%) | 1.3 (6.7%) m | 1.0 (4.8%) m | 0.5 steps, 0.6 m |
| Run | 7 | 0.7 (4.4%) | 0.6 (3.8%) | 2.1 (13.3%) | 1.6 (7.9%) m | 0.9 (4.7%) m | 0.7 steps, 0.9 m |
| Zero-step | 11 | 3.2 | 1.8 | 40.2 | 1.9 m | 1.2 m | 1.5 steps, 1.0 m |
| All | 39 | 1.5 (7.5%) | 1.1 (5.6%) | 13.9 (70.2%) | 1.3 (9.2%) m | 0.9 (6.6%) m | 0.8 steps, 0.7 m |

## The +/- the dashboard shows

From the ankle-only errors above (root-mean-square per group), not from the committee's spread, which is far smaller than the real errors. Saved in `step_model.npz`; the board picks the group from the net's own step rate for each clip and adds up `clip_uncertainty`.

| Group | Steps +/- | Distance +/- | Applies when the net's step rate is |
|---|---|---|---|
| Zero-step | 0.15 false steps per second | 0.09 m per second | below 0.71 steps/s |
| Walk_slow | 2.3% of the steps | 3.8% of the distance | 0.71 to 1.50 steps/s |
| Walk_normal | 4.0% of the steps | 5.1% of the distance | 1.50 to 1.74 steps/s |
| Walk_fast | 3.5% of the steps | 7.4% of the distance | 1.74 to 2.09 steps/s |
| Run | 5.1% of the steps | 9.7% of the distance | 2.09 and up steps/s |

## Compared with the 22-feature model

The same leave-one-out test, ankle only, for the earlier model with the 12 per-axis features as well (`step_model_22features.npz`, `results_per_trial_22features.csv`). Average error per trial, and in brackets as a % of the true total.

| Pace | Trials | Steps error: 22 features | Steps error: direction-free (now) | Distance error: 22 features | Distance error: direction-free (now) |
|---|---|---|---|---|---|
| Walk_slow | 7 | 0.6 (1.7%) | 0.7 (1.8%) | 0.7 (3.3%) m | 0.6 (3.1%) m |
| Walk_normal | 7 | 0.7 (2.3%) | 1.0 (3.2%) | 0.5 (2.3%) m | 0.8 (3.9%) m |
| Walk_fast | 7 | 0.5 (2.0%) | 0.8 (3.1%) | 0.9 (4.3%) m | 1.3 (6.7%) m |
| Run | 7 | 0.6 (3.5%) | 0.7 (4.4%) | 1.4 (6.9%) m | 1.6 (7.9%) m |
| Zero-step | 11 | 3.7 | 3.2 | 2.1 m | 1.9 m |
| All | 39 | 1.5 (7.5%) | 1.5 (7.5%) | 1.2 (8.3%) m | 1.3 (9.2%) m |

<!-- test walks: written by evaluate_tests.py -->
## Test walks: the live count on the board

Written by `evaluate_tests.py`. Counted walks on the 20 m course, counted live by the UNO Q (no stomp or phone). The live count is what the board saved for each walk; the peak counter ran on the same recordings.

### Before the fix: counted live by the 22-feature model

These walks showed the sensor-angle problem and chose the fix, so they're the "before" comparison, not a test of the fix.

Per pace ("Training expected" is that model's leave-one-out error):

| Pace | Live: average error | Live: worst | Live: error % | Training expected (leave-one-out) | Peak counter: error % | Live distance: average error | Distance error % | Training expected (distance) |
|---|---|---|---|---|---|---|---|---|
| Walk slow | 3.1 steps | -4.5 | 9.9% | 1.7% | 1.1% | 2.8 m | 13.8% | 3.3% |
| Walk normal | 5.5 steps | -7.3 | 19.5% | 2.3% | 31.8% | 3.9 m | 19.3% | 2.3% |
| Walk fast | 4.5 steps | -5.1 | 18.4% | 2.0% | 62.2% | 3.1 m | 15.4% | 4.3% |
| Run | 1.2 steps | -2.8 | 7.1% | 3.5% | 13.7% | 1.9 m | 9.6% | 6.9% |
| All | 3.6 steps | -7.3 | 14.2% | 2.4% (average) | 26.6% | 2.9 m | 14.5% | 4.2% (average) |

Each walk:

| Walk | Pace | Your count | Live count | Error | Within ±? | Peak counter | Live distance (of 20 m) |
|---|---|---|---|---|---|---|---|
| Test_T06 | Walk slow | 32 | 29.2 ± 1.1 | -2.8 | no | 32 (+0) | 17.6 ± 0.8 m (-2.4) |
| Test_T07 | Walk slow | 32 | 29.9 ± 1.2 | -2.1 | no | 32 (+0) | 17.9 ± 0.9 m (-2.1) |
| Test_T08 | Walk slow | 31 | 26.5 ± 1.1 | -4.5 | no | 32 (+1) | 16.2 ± 0.8 m (-3.8) |
| Test_T09 | Walk normal | 29 | 21.7 ± 1.0 | -7.3 | no | 30 (+1) | 15.0 ± 0.8 m (-5.0) |
| Test_T10 | Walk normal | 28 | 23.1 ± 0.9 | -4.9 | no | 54 (+26) | 16.3 ± 0.8 m (-3.7) |
| Test_T11 | Walk normal | 28 | 23.6 ± 0.9 | -4.4 | no | 28 (+0) | 17.1 ± 0.8 m (-2.9) |
| Test_T12 | Walk fast | 24 | 18.9 ± 0.7 | -5.1 | no | 46 (+22) | 15.9 ± 0.6 m (-4.1) |
| Test_T13 | Walk fast | 25 | 20.3 ± 0.8 | -4.7 | no | 48 (+23) | 16.7 ± 0.7 m (-3.3) |
| Test_T14 | Walk fast | 25 | 21.2 ± 0.8 | -3.8 | no | 26 (+1) | 18.2 ± 0.8 m (-1.8) |
| Test_T15 | Run | 17 | 14.2 ± 0.7 | -2.8 | no | 18 (+1) | 17.2 ± 1.3 m (-2.8) |
| Test_T16 | Run | 17 | 17.4 ± 0.9 | +0.4 | yes | 20 (+3) | 22.1 ± 1.9 m (+2.1) |
| Test_T17 | Run | 17 | 16.6 ± 0.9 | -0.4 | yes | 20 (+3) | 20.8 ± 1.9 m (+0.8) |

2 of 12 walks were within the live ±.

Why they came out low: the same committee retrained on the training trials and run on these walks the training way (moving stretch only). With all 22 features it undercounts like the board; with only the 10 features that don't depend on how the sensor sits on the leg, it's close. This is how the fix was chosen.

| Walk | Your count | Retrained, all 22 features | Retrained, direction-free only |
|---|---|---|---|
| Test_T06 | 32 | 29.6 | 31.7 |
| Test_T07 | 32 | 29.8 | 31.8 |
| Test_T08 | 31 | 28.0 | 31.8 |
| Test_T09 | 29 | 24.1 | 29.4 |
| Test_T10 | 28 | 23.8 | 27.2 |
| Test_T11 | 28 | 23.8 | 27.4 |
| Test_T12 | 24 | 19.2 | 24.1 |
| Test_T13 | 25 | 21.2 | 25.4 |
| Test_T14 | 25 | 21.2 | 25.5 |
| Test_T15 | 17 | 16.4 | 17.8 |
| Test_T16 | 17 | 18.5 | 18.3 |
| Test_T17 | 17 | 19.0 | 17.7 |

Average error per walk: all 22 features: 3.1 steps; direction-free only: 0.6 steps.

### After the fix

No test walks yet (Test T18 and up, after the redeploy).
