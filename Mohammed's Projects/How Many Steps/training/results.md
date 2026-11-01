# Step counter: leave-one-trial-out results

Written by `train_steps.py`. 33 good trials, 1430 clips of 2 s. Each trial's totals come from a committee of 5 nets trained without it. Errors are the mean absolute error per trial, and in brackets the total error as a % of the true total. The +/- is the spread between the committee's nets.

| Pace | Trials | Steps error: ankle only | Steps error: ankle + phone | Steps error: peak counter | Distance error: ankle only | Distance error: ankle + phone | Typical +/- (ankle only) |
|---|---|---|---|---|---|---|---|
| Walk_slow | 7 | 0.6 (1.5%) | 0.5 (1.4%) | 0.9 (2.3%) | 0.8 (3.8%) m | 0.8 (4.0%) m | 0.3 steps, 0.3 m |
| Walk_normal | 7 | 0.7 (2.2%) | 0.7 (2.1%) | 1.4 (4.5%) | 0.4 (2.2%) m | 0.8 (3.8%) m | 0.3 steps, 0.4 m |
| Walk_fast | 7 | 0.6 (2.4%) | 0.7 (2.9%) | 10.0 (40.7%) | 1.0 (4.9%) m | 1.0 (4.8%) m | 0.3 steps, 0.4 m |
| Run | 7 | 0.6 (4.0%) | 0.5 (3.2%) | 2.1 (13.3%) | 1.1 (5.6%) m | 0.7 (3.6%) m | 0.4 steps, 0.5 m |
| Zero-step | 5 | 13.0 | 8.2 | 34.0 | 7.6 m | 5.4 m | 2.5 steps, 1.7 m |
| All | 33 | 2.5 (10.6%) | 1.8 (7.5%) | 8.2 (35.1%) | 1.8 (10.9%) m | 1.5 (8.8%) m | 0.7 steps, 0.6 m |
