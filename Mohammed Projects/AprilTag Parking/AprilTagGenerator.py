"""Generate a printable AprilTag using OpenCV's aruco module.

AprilTags need a white "quiet zone" border around the black-and-white
pattern so a detector can find the tag's edges reliably - this adds one.
"""

import cv2

TAG_FAMILY = cv2.aruco.DICT_APRILTAG_36h11
TAG_ID = 0
TAG_SIZE_PX = 400  # size of the tag pattern itself, before the border
BORDER_PX = 60  # white quiet-zone border added on all four sides
OUTPUT_PATH = "apriltag_id0.png"


def main():
    dictionary = cv2.aruco.getPredefinedDictionary(TAG_FAMILY)
    tag = cv2.aruco.generateImageMarker(dictionary, TAG_ID, TAG_SIZE_PX)

    bordered = cv2.copyMakeBorder(
        tag, BORDER_PX, BORDER_PX, BORDER_PX, BORDER_PX,
        cv2.BORDER_CONSTANT, value=255,
    )
    cv2.imwrite(OUTPUT_PATH, bordered)
    print(f"Saved {OUTPUT_PATH} ({bordered.shape[1]}x{bordered.shape[0]} px), tag id {TAG_ID}, family 36h11")


if __name__ == "__main__":
    main()
