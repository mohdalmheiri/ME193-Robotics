"""
clean_background.py - turn the phone photo of a sheet of paper (IMG_0854.jpeg)
into the movie's background: background_paper.png.

Run:  python clean_background.py ~/Desktop/IMG_0854.jpeg

The three clean-ups, in plain words:
  1. Crop: cut off the thin paper edge and the darker strip on the far left.
  2. Show-through printing: the photo is split into FINE GRAIN (tiny
     pixel-to-pixel texture: the paper fibres) and everything bigger. In the
     bigger part, the faint printing is thin, slightly darker marks, so a
     "keep the lightest value nearby" filter (grey closing) wipes them out;
     then the grain is added back on top, so the paper still looks like paper.
  3. Faint vertical bands: each column's average brightness is compared with
     a smoothed version of itself; the narrow differences (the bands) are
     subtracted, and wide gentle changes are kept.
  4. Lighting: the brightness change from left to right is measured (a very
     blurred copy) and only a quarter of it is kept: still a little natural
     light, but no dark side.
  5. Colour: the paper is tinted a light cream, like paper under a desk lamp:
     brighter than the photo, but still darker than the white paper borders
     of the cutouts, so they stand out against it.
The result is a bit bigger than 1920x1080 so the movie can drift the
"camera" slightly without showing an edge.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
OUT_W, OUT_H = 2112, 1188          # 10% larger than 1920x1080: room for the camera to drift
CROP_LEFT = 0.05                   # share of the width cut off on the left (the paper edge and dark strip)
KEEP_LIGHTING = 0.25               # how much of the original light gradient stays (0 = flat, 1 = as photographed)
PAPER_RGB = (228, 219, 199)        # the average paper colour: light cream (cutout borders are ~250, so they stand out)


def main(src):
    img = cv2.imread(str(Path(src).expanduser()))
    h, w = img.shape[:2]
    img = img[:, int(w * CROP_LEFT):]                                   # 1. crop the left edge
    # Fit to 16:9 (crop the height a little if needed), then resize
    h, w = img.shape[:2]
    want_h = int(w * OUT_H / OUT_W)
    if want_h < h:
        top = (h - want_h) // 2
        img = img[top:top + want_h]
    img = cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA).astype(np.float32)

    # 2. Split: fine grain (what a 2-pixel blur removes) and the rest
    smooth = cv2.GaussianBlur(img, (0, 0), 2.0)
    grain = img - smooth
    # Wipe the faint printing out of the smooth part: thin dark marks vanish
    # under a closing (largest nearby value, then smallest), then a soft blur
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    paper = cv2.morphologyEx(smooth, cv2.MORPH_CLOSE, k)
    paper = cv2.GaussianBlur(paper, (0, 0), 12)

    # 3. Faint vertical bands: narrow column-to-column differences are removed
    cols = paper.mean(axis=0, keepdims=True)                            # 1 x width x 3
    bands = cols - cv2.GaussianBlur(cols, (0, 0), sigmaX=120, sigmaY=0.1)
    paper = paper - bands

    # 4. Lighting: the very slow brightness change across the sheet
    light = cv2.GaussianBlur(paper, (0, 0), 250)
    mean = light.reshape(-1, 3).mean(0)
    flat = paper / light * mean                                         # perfectly even paper
    gentle = mean + KEEP_LIGHTING * (light - mean)                      # a quarter of the original light
    # 5. Colour: even paper x gentle light, tinted cream; then the grain back (slightly stronger)
    cream = np.array(PAPER_RGB[::-1], np.float32)                       # OpenCV stores blue, green, red
    out = (flat / mean) * (gentle / mean) * cream + grain * 1.2
    out = np.clip(out, 0, 255).astype(np.uint8)
    cv2.imwrite(str(HERE / "background_paper.png"), out)
    print(f"saved background_paper.png {OUT_W}x{OUT_H}; light left/right before "
          f"{light[:, :200].mean():.0f}/{light[:, -200:].mean():.0f}, after "
          f"{gentle[:, :200].mean():.0f}/{gentle[:, -200:].mean():.0f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/IMG_0854.jpeg")
