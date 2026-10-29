"""Copy the Step Recorder's trials from the UNO Q into this folder.

    python sync_from_board.py

- Every Person_Activity_Tnn.csv on the board goes to raw/.
- The board's trials.csv replaces trials.csv here (the board is the master copy).
- Prints anything that doesn't match up: a recording without a row in
  trials.csv, a row without its recording, or a phyphox zip that's missing.

It finds the board with the ArduinoApps kit's deploy.py (USB first, then the
addresses in board_secrets.py). That connection checks the board's ssh key,
so on campus Wi-Fi it can't copy from a classmate's board by mistake.
"""
import csv
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The deploy kit lives outside this repo (it holds the board's address and login)
KIT_TOOLS = Path.home() / "Documents" / "GitHub" / "ArduinoApps" / "tools"
REMOTE_DIR = "/home/arduino/ArduinoApps/step-recorder/python/recordings"

DATA_DIR = Path(__file__).resolve().parent
RAW_DIR = DATA_DIR / "raw"
PHONE_DIR = DATA_DIR / "phone_raw"
TRIALS_CSV = DATA_DIR / "trials.csv"

sys.path.insert(0, str(KIT_TOOLS))
import deploy  # noqa: E402  (needs the line above to be found)


def copy_from_board(board, dest):
    """Copy the board's recordings folder into dest, over USB or ssh."""
    kind, target = board
    if kind == "adb":
        subprocess.run(["adb", "pull", f"{REMOTE_DIR}/.", str(dest)], check=True)
    else:
        subprocess.run(["scp", *deploy.SSH_OPTS, "-r", "-q", f"{target}:{REMOTE_DIR}/.", str(dest)], check=True)


def main():
    board = deploy.find_board()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        copy_from_board(board, tmp)

        # Recordings: copy new or changed files into raw/
        new = changed = 0
        for src in sorted(tmp.glob("*_T*.csv")):
            dst = RAW_DIR / src.name
            if dst.exists() and filecmp.cmp(src, dst, shallow=False):
                continue
            changed += dst.exists()
            new += not dst.exists()
            shutil.copy2(src, dst)
        board_files = {p.name for p in tmp.glob("*_T*.csv")}

        if (tmp / "trials.csv").exists():
            shutil.copy2(tmp / "trials.csv", TRIALS_CSV)
    print(f"\n{new} new and {changed} updated recordings in raw/, trials.csv updated")

    # Cross-checks, so a missing count or phone file is noticed while the
    # trial can still be redone
    rows = []
    if TRIALS_CSV.exists():
        with open(TRIALS_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
    in_trials = {r["file"] for r in rows}
    for name in sorted(board_files - in_trials):
        print(f"  no row in trials.csv (stopped but never saved?): {name}")
    for name in sorted(in_trials - board_files):
        print(f"  in trials.csv but not on the board: {name}")
    for name in sorted(p.name for p in RAW_DIR.glob("*_T*.csv") if p.name not in board_files):
        print(f"  in raw/ but deleted on the board: {name}")
    missing = [r["file"] for r in rows if not (PHONE_DIR / r["file"].replace(".csv", ".zip")).exists()]
    if missing:
        print(f"  {len(missing)} trials have no phyphox zip in phone_raw/ yet, e.g. {missing[0]}")
    print(f"{len(rows)} trials in trials.csv")


if __name__ == "__main__":
    main()
