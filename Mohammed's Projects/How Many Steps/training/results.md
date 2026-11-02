# Step counter: leave-one-trial-out results

Written by `train_steps.py`. 39 good trials, 1775 clips of 2 s. Each trial's totals come from a committee of 5 nets trained without it. Errors are the mean absolute error per trial, and in brackets the total error as a % of the true total. The +/- is the spread between the committee's nets.

| Pace | Trials | Steps error: ankle only | Steps error: ankle + phone | Steps error: peak counter | Distance error: ankle only | Distance error: ankle + phone | Typical +/- (ankle only) |
|---|---|---|---|---|---|---|---|
| Walk_slow | 7 | 0.6 (1.7%) | 0.6 (1.6%) | 0.9 (2.3%) | 0.7 (3.3%) m | 0.8 (4.1%) m | 0.2 steps, 0.2 m |
| Walk_normal | 7 | 0.7 (2.3%) | 0.8 (2.5%) | 1.4 (4.5%) | 0.4 (2.2%) m | 0.6 (2.8%) m | 0.5 steps, 0.4 m |
| Walk_fast | 7 | 0.5 (2.1%) | 0.6 (2.3%) | 10.0 (40.7%) | 0.9 (4.4%) m | 0.8 (3.8%) m | 0.5 steps, 0.5 m |
| Run | 7 | 0.5 (3.4%) | 1.0 (6.2%) | 2.1 (13.3%) | 1.4 (6.9%) m | 1.2 (5.8%) m | 0.5 steps, 0.6 m |
| Zero-step | 11 | 3.7 | 1.6 | 40.2 | 2.1 m | 1.0 m | 1.3 steps, 0.8 m |
| All | 39 | 1.5 (7.5%) | 1.0 (4.9%) | 13.9 (70.2%) | 1.2 (8.4%) m | 0.9 (6.2%) m | 0.7 steps, 0.5 m |

## The +/- the dashboard shows

From the ankle-only errors above (root-mean-square per group), not from the committee's spread, which is far smaller than the real errors. Saved in `step_model.npz`; the board picks the group from the net's own step rate for each clip and adds up `clip_uncertainty`.

| Group | Steps +/- | Distance +/- | Applies when the net's step rate is |
|---|---|---|---|
| Zero-step | 0.14 false steps per second | 0.08 m per second | below 0.71 steps/s |
| Walk_slow | 2.7% of the steps | 4.0% of the distance | 0.71 to 1.50 steps/s |
| Walk_normal | 2.6% of the steps | 2.8% of the distance | 1.50 to 1.74 steps/s |
| Walk_fast | 2.4% of the steps | 4.9% of the distance | 1.74 to 2.09 steps/s |
| Run | 4.6% of the steps | 9.0% of the distance | 2.09 and up steps/s |

<!-- test walks: written by evaluate_tests.py -->
## Test walks: the live count on the board

Written by `evaluate_tests.py`. 12 counted walks on the 20 m course, 3 per pace, counted live by the UNO Q (no stomp or phone). The live count is what the board saved for each walk; the peak counter ran on the same recordings.

### Per pace

| Pace | Live: average error | Live: worst | Live: error % | Training expected (leave-one-out) | Peak counter: error % | Live distance: average error | Distance error % | Training expected (distance) |
|---|---|---|---|---|---|---|---|---|
| Walk slow | 3.1 steps | -4.5 | 9.9% | 1.7% | 1.1% | 2.8 m | 13.8% | 3.3% |
| Walk normal | 5.5 steps | -7.3 | 19.5% | 2.3% | 31.8% | 3.9 m | 19.3% | 2.3% |
| Walk fast | 4.5 steps | -5.1 | 18.4% | 2.0% | 62.2% | 3.1 m | 15.4% | 4.3% |
| Run | 1.2 steps | -2.8 | 7.1% | 3.5% | 13.7% | 1.9 m | 9.6% | 6.9% |
| All | 3.6 steps | -7.3 | 14.2% | 2.4% (average) | 26.6% | 2.9 m | 14.5% | 4.2% (average) |

### Each walk

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

### Why the walks came out low: the sensor's angle

The same committee retrained on the training trials and run on these walks the training way (moving stretch only): with all 22 features it undercounts like the board; with only the 10 features that don't depend on how the sensor sits on the leg, it's close. Diagnostic only, not the deployed model.

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
