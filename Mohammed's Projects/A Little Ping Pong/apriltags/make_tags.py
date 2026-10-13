# Step 3a: make printable AprilTags for the paddle and the level picker.
# Run:  python make_tags.py
# Saves tag_0.png ... tag_3.png plus tags_sheet.png (all four on one page) in
# this folder. Same family as HW2 (OpenCV aruco, AprilTag 36h11).
import os

import cv2
import numpy as np

TAG_FAMILY = cv2.aruco.DICT_APRILTAG_36h11
LABELS = {0: "0 = PADDLE", 1: "1 = EASY", 2: "2 = MEDIUM", 3: "3 = HARD"}
TAG_SIZE_PX = 400   # size of the black-and-white pattern itself
BORDER_PX = 60      # white quiet-zone border so the detector can find the edges
LABEL_PX = 80       # extra white space under the tag for the label

OUT_DIR = os.path.dirname(os.path.abspath(__file__))   # the images go next to this script


def make_tag(dictionary, tag_id):
    """One tag with a white border and its label underneath."""
    tag = cv2.aruco.generateImageMarker(dictionary, tag_id, TAG_SIZE_PX)
    img = cv2.copyMakeBorder(tag, BORDER_PX, BORDER_PX + LABEL_PX, BORDER_PX, BORDER_PX,
                             cv2.BORDER_CONSTANT, value=255)

    text = LABELS[tag_id]
    font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    x = (img.shape[1] - tw) // 2
    y = BORDER_PX + TAG_SIZE_PX + BORDER_PX // 2 + (LABEL_PX + th) // 2
    cv2.putText(img, text, (x, y), font, scale, 0, thick, cv2.LINE_AA)
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(TAG_FAMILY)

    tags = []
    for tag_id in LABELS:
        img = make_tag(dictionary, tag_id)
        path = os.path.join(OUT_DIR, f"tag_{tag_id}.png")
        cv2.imwrite(path, img)
        print(f"Saved {path} ({img.shape[1]}x{img.shape[0]} px)")
        tags.append(img)

    # 2x2 sheet with a thin grey cut line between the tags
    tags = [cv2.copyMakeBorder(t, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=180) for t in tags]
    sheet = np.vstack([np.hstack(tags[0:2]), np.hstack(tags[2:4])])
    sheet = cv2.copyMakeBorder(sheet, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    path = os.path.join(OUT_DIR, "tags_sheet.png")
    cv2.imwrite(path, sheet)
    print(f"Saved {path} ({sheet.shape[1]}x{sheet.shape[0]} px)")


if __name__ == "__main__":
    main()
