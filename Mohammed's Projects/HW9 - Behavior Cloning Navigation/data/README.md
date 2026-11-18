# Walk data

Every full walk of the route is saved as one CSV **by the board**, like HW7's Step
Recorder saves each trial, and then copied into `walks/` on the laptop. The phone page's
**Download CSV** button is only a backup. Both partners' walks go here, because the policy
is trained on both. For the step-by-step routine, see
[RECORDING_CHECKLIST.md](RECORDING_CHECKLIST.md).

(The board app isn't written yet. Until it is, the phone download is the only copy.)

## The 10-walk budget

The assignment allows **10 full walks in total**, both partners together, including
correction (DAgger) walks. **This table is the official walk count.** The counter on the
phone page is not: it starts over when the page reloads, and each phone counts only its
own walks. Every full walk gets a row here, even a failed one, so the count stays honest.
Short counted test walks of the step counter are not full route walks and are logged in
the process log instead.

| # | File | Walker | Date | Kind | Used for training? | Notes |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |
| 6 | | | | | | |
| 7 | | | | | | |
| 8 | | | | | | |
| 9 | | | | | | |
| 10 | | | | | | |

**Kind** is `demo` (a recorded walk: the walker labels what they do) or `dagger` (a
correction walk: the policy guides, and the walker presses the right action whenever it
is wrong). On the phone page these are the **Record demo** tab and the **Navigate +
correct** tab with "Save my corrections" ticked.

## File names

One file per walk: `walks/Person_kind_Wnn.csv`, numbered across both partners in the
order walked (the number in the table above), for example `walks/Raph_demo_W01.csv`,
`walks/Mohammed_demo_W02.csv`, `walks/Mohammed_dagger_W07.csv`.

The phone's backup download is different: one file, `nav_data_<date>-<time>.csv`, with
every walk since the page was opened, and walk numbers that start at 1 on each phone.
Use it only when the board's copy is missing, and split it by the `walk` column.

## Columns

These are exactly the columns the phone page (`uno_q/assets/index.html`) exports, in
this order, and the board's files will use the same ones. Each row is one moment of the
walk, a snapshot of what the sensors said and which button was pressed then.

| Column | What it means, in plain words |
|---|---|
| `walk` | Which walk this row belongs to (the walk number, the same on every row of a file). |
| `walker` | Who was walking: Mohammed or Raph. |
| `kind` | `demo` (a recorded walk) or `dagger` (a correction walk). |
| `t_ms` | The phone's clock when this row was saved, in milliseconds (1000 ms = 1 second). It is a standard computer clock (counting from 1 Jan 1970), so subtract a walk's first `t_ms` to get the time since that walk started. |
| `steps` | How many steps the walker has taken since the walk began, as a whole number (the counter's running total, rounded down). |
| `distance_m` | How far the walker has gone since the walk began, in meters (to 0.1 m), from the same step counter. Saved next to `steps` to compare the two on the first walks: a person with shorter strides takes more steps for the same corridor, but should cover the same meters. |
| `steps_since_turn` | How many steps since the last turn. The count starts over at 0 at every turn. **The policy uses this.** |
| `turns` | How many turns so far, left and right together. |
| `turns_left` | How many of those turns were to the left. **The policy uses this.** |
| `turns_right` | How many were to the right. **The policy uses this.** |
| `heading_deg` | Which way the walker faces, in degrees, worked out by adding up the waist gyro's turning. It slowly drifts wrong over a long walk, so it is saved only for checking afterwards. **The policy does not use it.** |
| `on_stairs` | Whether the walker is on stairs right now (yes or no). **The policy uses this.** |
| `label` | The button the walker had pressed: what they were doing. One of `Straight`, `Left`, `Right`, `Stairs`, `Arrived`. This is the answer the policy learns to copy. |
| `predicted` | Only on `dagger` rows: what the policy told the walker to do, before any correction. Where it differs from `label`, the policy was wrong and the walker corrected it. Empty on `demo` rows. |

`turns` is always `turns_left` + `turns_right`, and `steps_since_turn` is `steps` minus
the step count at the last turn. They are saved anyway because they make the files easy
to read by eye.

Raw labels are never edited in these files. Label cleanup is done by a training script,
so the original recording is always kept. The script will:
- shift each turn label a few steps earlier, to undo the walker's reaction delay
- fix a `Left` or `Right` label that stays on after the turn has ended. The page now ends
  a turn label when the board counts the turn (and after 10 steps at the latest), which
  should stop this in new walks; the cleanup keeps the fix as a safety net (see
  `docs/process_log.md`)
