"""
prepare_board_files.py - copy what the board needs into safe_app/python/.

Run (on the laptop, after training or after changing the crop box):
    python prepare_board_files.py
then deploy safe_app.

The board only receives the safe_app folder, so it can't import from
02_data_collection or 03_training. Instead of keeping hand-edited copies
(which would slowly drift apart), this script makes fresh copies from the
one true source each time:

  02_data_collection/hand_crop.py      -> safe_app/python/hand_crop.py      (same camera checks and crop)
  02_data_collection/crop_config.json  -> safe_app/python/crop_config.json  (same crop box)
  03_training/finger_cnn.pt            -> safe_app/python/finger_net.npz    (the trained numbers, for numpy)
  04_unoq_app/safe_code.txt            -> safe_app/python/safe_code.txt     (the code; both copies stay out of Git)

Then it checks that the numpy network (finger_net.py) gives the same
answers as PyTorch on every validation photo, and stops if it doesn't.
"""
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
APP_PY = HERE / "safe_app" / "python"
sys.path.insert(0, str(PROJECT / "03_training"))
sys.path.insert(0, str(PROJECT / "02_data_collection"))
sys.path.insert(0, str(APP_PY))
from model import load_trained        # noqa: E402
import hand_crop as hc                # noqa: E402
from finger_net import FingerNet      # noqa: E402
from lock_logic import read_code      # noqa: E402

GENERATED = "# GENERATED COPY - edit 02_data_collection/hand_crop.py instead, then run prepare_board_files.py\n"


def main():
    # 1. Copies of the shared camera code and the crop box
    src = PROJECT / "02_data_collection"
    (APP_PY / "hand_crop.py").write_text(GENERATED + (src / "hand_crop.py").read_text())
    shutil.copy(src / "crop_config.json", APP_PY / "crop_config.json")
    read_code(HERE / "safe_code.txt")                     # stops here if the code file is missing or wrong
    shutil.copy(HERE / "safe_code.txt", APP_PY / "safe_code.txt")

    # 2. The trained numbers, as a plain numpy file
    model, info = load_trained(PROJECT / "03_training" / "finger_cnn.pt")
    np.savez(APP_PY / "finger_net.npz", **{k: v.numpy() for k, v in model.state_dict().items()})

    # 3. Same answers? Every validation photo through both networks
    net = FingerNet(APP_PY / "finger_net.npz")
    data = PROJECT / "02_data_collection" / "data"
    worst, same = 0.0, 0
    files = info["val_files"]
    for rel in files:
        x = hc.to_network_input(cv2.imread(str(data / rel)))
        with torch.no_grad():
            want = model(torch.from_numpy(x).unsqueeze(0))[0].numpy()
        got = net.scores(x)
        worst = max(worst, float(np.abs(got - want).max()))
        same += int(got.argmax() == want.argmax())
    print(f"numpy vs PyTorch on {len(files)} validation photos: same guess on {same}, "
          f"largest score difference {worst:.2e}")
    if same != len(files) or worst > 1e-3:
        sys.exit("MISMATCH: the numpy network doesn't match PyTorch. Not safe to deploy.")
    print(f"Wrote hand_crop.py, crop_config.json, safe_code.txt, finger_net.npz to {APP_PY.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
