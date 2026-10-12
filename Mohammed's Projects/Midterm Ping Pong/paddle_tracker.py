# Step 3b: track the paddle (tag 0) and level tags (1-3) with the webcam.
# Run:  python paddle_tracker.py      (press q in the video window to quit)
import time

import cv2
import numpy as np

CAMERA_INDEX = 0
TAG_FAMILY = cv2.aruco.DICT_APRILTAG_36h11   # same as HW2 / make_tags.py
PADDLE_ID = 0
LEVELS = {1: "EASY", 2: "MEDIUM", 3: "HARD"}

GREEN = (0, 255, 0)   # OpenCV colors are BGR
BLUE = (255, 0, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")

    dictionary = cv2.aruco.getPredefinedDictionary(TAG_FAMILY)
    detector = cv2.aruco.ArucoDetector(dictionary)

    fps = 0.0
    last_time = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]

            # Detect BEFORE mirroring: a mirrored AprilTag is a different
            # (invalid) pattern and won't be recognized. Then mirror the image
            # and flip the corner x-coordinates to match.
            corners, ids, _ = detector.detectMarkers(frame)
            frame = cv2.flip(frame, 1)

            paddle_found = False
            if ids is not None:
                for tag_corners, tag_id in zip(corners, ids.flatten()):
                    pts = tag_corners.reshape(4, 2).copy()
                    pts[:, 0] = (w - 1) - pts[:, 0]
                    cx, cy = pts.mean(axis=0)
                    box = [pts.astype(np.int32)]

                    if tag_id == PADDLE_ID:
                        paddle_found = True
                        nx, ny = cx / w, cy / h   # 0,0 = top-left, 1,1 = bottom-right
                        cv2.polylines(frame, box, True, GREEN, 3)
                        cv2.circle(frame, (int(cx), int(cy)), 6, GREEN, -1)
                        cv2.putText(frame, f"PADDLE x={nx:.2f} y={ny:.2f}",
                                    (int(pts[:, 0].min()), int(pts[:, 1].min()) - 10),
                                    FONT, 0.7, GREEN, 2)
                    elif tag_id in LEVELS:
                        cv2.polylines(frame, box, True, BLUE, 3)
                        cv2.putText(frame, LEVELS[tag_id],
                                    (int(pts[:, 0].max()) + 10, int(cy)),
                                    FONT, 1, BLUE, 2)

            if not paddle_found:
                cv2.putText(frame, "PADDLE NOT FOUND", (10, 35), FONT, 1, RED, 2)

            # smoothed frames-per-second, top-right corner
            now = time.time()
            dt = now - last_time
            last_time = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
            text = f"FPS {fps:.0f}"
            (tw, _), _ = cv2.getTextSize(text, FONT, 0.7, 2)
            cv2.putText(frame, text, (w - tw - 10, 30), FONT, 0.7, WHITE, 2)

            cv2.imshow("Paddle Tracker (press q to quit)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
