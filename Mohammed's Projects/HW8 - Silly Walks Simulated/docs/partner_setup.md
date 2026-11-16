# Partner setup: robot side on a fresh laptop

This is for running the real-robot session on **your own laptop**. It installs only what the robot side needs:
- the `robot/` scripts
- the LEGO library (Bluetooth)
- MuJoCo, for the simulated rehearsal and tests

You do **not** need MJLab, the training code, or the Onshape keys.

**Time:** about 10 minutes, plus the downloads. Do it the evening before, not at the robot.

**Tested:** a fresh clone with a fresh Python 3.12 environment on a Mac (2026-11-16). All 7 test scripts passed, as did the calibration rehearsal, the demo, the Bluetooth search without a robot, and the branch commands at the bottom (except the push itself).

> **Windows is untested.** The packages all have Windows versions and the steps below should work, but leave time to sort out problems. If you get stuck, see "If something fails" at the end.

## 1. Install Python and Git (once)

- **Python 3.12 or newer**, 64-bit, from [python.org](https://www.python.org/downloads/).
  - **Windows:** tick **"Add python.exe to PATH"** in the installer.
- **Git**: <https://git-scm.com/downloads>.
  - **Mac:** typing `git` in Terminal offers to install it.
  - **No Git?** You can instead download the repo as a ZIP: on GitHub, use **Code → Download ZIP**, unzip it, and skip step 2. In that case, send the results the "no Git" way (bottom of this page).

## 2. Get the repo

```bash
git clone https://github.com/mohdalmheiri/ME193-Robotics.git
cd ME193-Robotics
```

The repo is public, so you don't need an account to clone it.

## 3. Create the Python environment

The environment **must** be at the top of the repo and **must** be named `.venv`:
- Git ignores it there (anywhere inside `Mohammed's Projects/` it would show up as thousands of new files).
- All the commands in the checklist expect it there.

**Mac:**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r "Mohammed's Projects/HW8 - Silly Walks Simulated/robot/requirements.txt"
```

**Windows (PowerShell):**
```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r "Mohammed's Projects\HW8 - Silly Walks Simulated\robot\requirements.txt"
```

`robot/requirements.txt` installs exactly five things, at tested versions:

| Package | What it's for |
|---|---|
| numpy | the maths, and the policy network |
| mujoco | the simulator for the fake robot and tests |
| matplotlib | plots |
| opencv-python | the demo video |
| legoeducation | the LEGO Double Motor over Bluetooth; it also installs `bleak` |

## 4. Go to the HW8 folder and check everything

Every command in `docs/real_robot_checklist.md` runs from the HW8 folder.

**Mac:**
```bash
cd "Mohammed's Projects/HW8 - Silly Walks Simulated"
../../.venv/bin/python robot/tests/test_units.py
```

**Windows:**
```powershell
cd "Mohammed's Projects\HW8 - Silly Walks Simulated"
..\..\.venv\Scripts\python.exe robot\tests\test_units.py
```

**Reading the checklist's commands:** the checklist writes `robot/calibrate.py` and means `../../.venv/bin/python robot/calibrate.py`.
- **Windows:** use `..\..\.venv\Scripts\python.exe robot\calibrate.py` instead. Backslashes or forward slashes both work in the file paths.
- **Shortcut:** activate the environment once per terminal, then just type `python robot/calibrate.py` and so on:
  - Mac: `source ../../.venv/bin/activate`
  - Windows: `..\..\.venv\Scripts\Activate.ps1`. If PowerShell refuses, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once first.

**Run all 7 tests.** Each one must end with "passed". They take about 3 minutes in total, and none of them need the robot:
```bash
python robot/tests/test_units.py
python robot/tests/test_policy.py
python robot/tests/test_safety.py
python robot/tests/test_real_robot_dryrun.py
python robot/tests/test_calibration.py
python robot/tests/test_calibrate.py
python robot/tests/test_demo.py
```

## 5. Rehearse the calibration (simulated robot, about 1 minute)

This rehearses against a **deliberately mis-wired** simulated robot and writes into a **copy** of the config, so your real `config.py` is untouched.

**Mac:**
```bash
cp robot/config.py /tmp/config_rehearsal.py
python robot/calibrate.py --fake --fake-hub upside-down --config /tmp/config_rehearsal.py
```

**Windows:**
```powershell
copy robot\config.py $env:TEMP\config_rehearsal.py
python robot\calibrate.py --fake --fake-hub upside-down --config $env:TEMP\config_rehearsal.py
```

**What you should see:**
- the same questions you'll answer at the robot, with the simulated robot answering them
- a before → after table at the end, with most rows marked "changed"
- "A full policy action now = … 85 % power" and "Suggested baseline percent: 49 %"

Those last two numbers belong to the **fake** 130 rpm motor. The real robot (2026-11-16) measured 165.8 rpm at 100 %, giving **66 %** and a suggested **38 %**; the real policy logs gave 40 %.

## 6. Bluetooth check (no robot needed)

```bash
python -c "import legoeducation, bleak; print('LEGO library OK')"
```

- Turn Bluetooth on.
- **Mac:** the first time a terminal uses Bluetooth, macOS asks "Terminal would like to use Bluetooth". Click **Allow**. If you missed it, go to System Settings → Privacy & Security → Bluetooth and turn on your terminal app (Terminal, iTerm or VS Code).
- **Test search:**
  ```bash
  python robot/run_policy.py --real --seconds 1 --name connect
  ```
  - Without the robot, it searches for about 10 s and then stops with a long error (a "traceback"). The **last line** is `ConnectionError: Could not connect. Is it charged, on, and not connected elsewhere?`. **That is the expected result tonight.** Nothing was sent to any motor.
  - **Mac:** a crash mentioning Bluetooth permission means the Allow step above is missing.

## 7. The live demo (optional)

Headless check:
```bash
python robot/demo_live.py --headless --seconds 5
```
It prints two lines (baseline and policy).

Live window:
- **Mac:** use mjpython: `../../.venv/bin/mjpython robot/demo_live.py`. Plain `python` cannot open the MuJoCo window on a Mac.
- **Windows:** use plain Python: `python robot/demo_live.py`. There is no mjpython on Windows, and it isn't needed.
- **If the window won't open:** play `docs/media/demo_side_by_side.mp4` instead.

## Sending the results back

At the end of the session, the results are:
- **Run logs:** every CSV (and the drift tests' `.json` files) in `robot/runs/`. **Git ignores this folder.**
- **Calibration:** the changed `robot/config.py`. Its backups are in `robot/config_backups/`.
- **Julian's measurements:** the ruler table (step 3 of the checklist), the robot's weight, and the stop reasons and hand measurements you wrote down.
- **Phone videos and photos.**

**Option A: push a branch.** This needs push access to the repo; ask Mohammed to add you as a collaborator on GitHub. From the HW8 folder:

Mac:
```bash
git checkout -b julian-robot-session
mkdir -p docs/data/session_julian
cp robot/runs/* docs/data/session_julian/          # robot/runs/ itself is ignored by git
git add robot/config.py docs/data/session_julian docs/real_robot_checklist.md
git commit -m "HW8: robot session results (Julian)"
git push -u origin julian-robot-session
```

Windows:
```powershell
git checkout -b julian-robot-session
mkdir docs\data\session_julian
copy robot\runs\* docs\data\session_julian\
git add robot/config.py docs/data/session_julian docs/real_robot_checklist.md
git commit -m "HW8: robot session results (Julian)"
git push -u origin julian-robot-session
```

- **Measurements:** if you typed them into the tables in `docs/real_robot_checklist.md`, they are included. Otherwise, photograph the printed checklist.
- **Videos:** **not in git** (too big). Put them in a shared Google Drive folder and send the link.
- **Push to the branch, not to `main`:** Mohammed checks the `config.py` changes before they go into `main`.

**Option B: no Git, or no push access.** Zip these and send them through Google Drive:
- the whole `robot/runs/` folder
- `robot/config.py`
- the `robot/config_backups/` folder
- photos of the filled-in checklist and the ruler table
- the phone videos

## If something fails

| Problem | Fix |
|---|---|
| `pip install` fails on mujoco or opencv | Check that Python is **64-bit** and **3.12 or newer** (`python --version`). On Windows, reinstall from python.org, not the Microsoft Store |
| "No module named …" | You're not using the `.venv` Python. Use the full `../../.venv/...` path, or activate the environment |
| `FileNotFoundError` for `robot/...` | You're not in the HW8 folder; `cd` into it first |
| A test says FAIL | Send Mohammed the full output before the session. Don't run the real robot until it's clear why |
| The robot is never found | Check that the hub is on and blinking, that it isn't connected to another device (phone app, other laptop), and that Bluetooth is on; on a Mac, also check the permission above. Turn the hub off and on and try again, 3 tries at most, then use the backup plan in `docs/demo_script.md` |
