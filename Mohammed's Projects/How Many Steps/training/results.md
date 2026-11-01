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
