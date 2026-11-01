# Step counter: leave-one-trial-out results

Written by `train_steps.py`. 39 good trials, 1775 clips of 2 s. Each trial's totals come from a committee of 5 nets trained without it. Errors are the mean absolute error per trial, and in brackets the total error as a % of the true total. The +/- is the spread between the committee's nets.

| Pace | Trials | Steps error: ankle only | Steps error: ankle + phone | Steps error: peak counter | Distance error: ankle only | Distance error: ankle + phone | Typical +/- (ankle only) |
|---|---|---|---|---|---|---|---|
| Walk_slow | 7 | 0.6 (1.5%) | 0.4 (1.0%) | 0.9 (2.3%) | 0.6 (3.2%) m | 0.6 (3.1%) m | 0.4 steps, 0.4 m |
| Walk_normal | 7 | 0.8 (2.5%) | 0.8 (2.7%) | 1.4 (4.5%) | 0.4 (2.1%) m | 0.6 (2.9%) m | 0.4 steps, 0.3 m |
| Walk_fast | 7 | 0.4 (1.8%) | 0.6 (2.4%) | 10.0 (40.7%) | 1.0 (5.2%) m | 0.9 (4.7%) m | 0.5 steps, 0.6 m |
| Run | 7 | 0.6 (3.8%) | 0.7 (4.6%) | 2.1 (13.3%) | 1.5 (7.6%) m | 0.9 (4.4%) m | 0.5 steps, 0.5 m |
| Zero-step | 11 | 6.6 | 2.3 | 40.2 | 3.9 m | 1.4 m | 1.5 steps, 1.1 m |
| All | 39 | 2.3 (11.6%) | 1.1 (5.6%) | 13.9 (70.2%) | 1.8 (12.2%) m | 0.9 (6.6%) m | 0.7 steps, 0.6 m |

## The +/- the dashboard shows

From the ankle-only errors above (root-mean-square per group), not from the committee's spread, which is far smaller than the real errors. Saved in `step_model.npz`; the board picks the group from the net's own step rate for each clip and adds up `clip_uncertainty`.

| Group | Steps +/- | Distance +/- | Applies when the net's step rate is |
|---|---|---|---|
| Zero-step | 0.32 false steps per second | 0.18 m per second | below 0.71 steps/s |
| Walk_slow | 2.3% of the steps | 4.1% of the distance | 0.71 to 1.50 steps/s |
| Walk_normal | 2.5% of the steps | 2.4% of the distance | 1.50 to 1.74 steps/s |
| Walk_fast | 2.2% of the steps | 5.9% of the distance | 1.74 to 2.09 steps/s |
| Run | 4.9% of the steps | 9.5% of the distance | 2.09 and up steps/s |
