"""
live_test.py - watch the trained network count fingers live from the webcam.

Run:  python live_test.py            (camera 0)
      python live_test.py --camera 1 (if the webcam has another number)
Keys: q or Esc to quit (click the window first).

It prepares every picture exactly as the UNO Q app will:
  camera forced to 640x480 and EVERY frame checked (hand_crop.check_frame_size)
  -> the box from crop_config.json (refused if saved for another size)
  -> crop and shrink to 128x128 -> hand_crop.to_network_input -> the network.
On screen: the camera picture with the box, the guess and how sure the
network is, and a bar for each of the six counts.
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "02_data_collection"))
import hand_crop as hc                        # noqa: E402  (the shared camera + photo preparation)
from model import CLASSES, load_trained       # noqa: E402

MODEL_PATH = HERE / "finger_cnn.pt"
WINDOW = "finger counter (q to quit)"
SURE = 0.80        # below this confidence the guess is drawn in orange: "not sure"


def guess(model, frame, box):
    """One camera frame -> (best class, its confidence, all six confidences)."""
    x = torch.from_numpy(hc.frame_to_network_input(frame, box)).unsqueeze(0)   # a batch of one photo
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)[0].numpy()   # softmax: six scores -> confidences adding to 1
    best = int(probs.argmax())
    return best, float(probs[best]), probs


def draw(frame, box, best, conf, probs, ms):
    """The picture, the box, the guess and the six confidence bars."""
    fh, fw = frame.shape[:2]
    panel = np.full((fh, 260, 3), 30, np.uint8)                  # dark side panel
    x, y, s = box
    cv2.rectangle(frame, (x, y), (x + s, y + s), (80, 200, 80), 2)
    color = (80, 200, 80) if conf >= SURE else (0, 165, 255)     # green = sure, orange = not sure
    cv2.putText(panel, CLASSES[best], (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 4, color, 8)
    cv2.putText(panel, f"{conf:.0%} sure", (120, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(panel, "fingers", (120, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    for i, p in enumerate(probs):                                 # one bar per count
        yy = 170 + i * 40
        cv2.putText(panel, CLASSES[i], (20, yy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.rectangle(panel, (50, yy), (230, yy + 20), (70, 70, 70), -1)
        cv2.rectangle(panel, (50, yy), (50 + int(180 * p), yy + 20), color if i == best else (160, 160, 160), -1)
    cv2.putText(panel, f"network: {ms:.0f} ms", (20, fh - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    return np.hstack([frame, panel])


def main():
    parser = argparse.ArgumentParser(description="Live finger counting from the webcam.")
    parser.add_argument("--camera", type=int, default=0, help="camera number (default 0)")
    args = parser.parse_args()

    if not MODEL_PATH.exists():
        sys.exit("No finger_cnn.pt yet. Run  python train.py  first.")
    cfg = hc.load_config()
    if cfg is None:
        sys.exit("No crop_config.json. Line up the box with capture.py first (f, then c).")
    model, info = load_trained(MODEL_PATH)
    print(f"Loaded finger_cnn.pt (epoch {info['epoch']}, validation accuracy {info['val_accuracy']:.1%})")

    try:
        box = hc.box_from_config(cfg)            # refuses a box saved for another picture size
        cap = hc.open_camera(args.camera)
        if not cap.isOpened():
            sys.exit(f"Camera {args.camera} did not open. Run  python ../02_data_collection/capture.py --list")
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("The camera stopped sending pictures (unplugged?).")
                break
            if frame.mean() < 5:                 # cameras send black frames while waking up; skip them
                continue
            t0 = time.perf_counter()
            best, conf, probs = guess(model, frame, box)        # also checks the frame is 640x480
            ms = (time.perf_counter() - t0) * 1000
            cv2.imshow(WINDOW, draw(frame, box, best, conf, probs, ms))
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):          # q or Esc
                break
    except hc.FrameSizeError as e:
        sys.exit(f"STOPPED: {e}")
    finally:
        if "cap" in locals():
            cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
