# AprilTag Parking (HW2)

Drive a LEGO Education car so that an AprilTag ends up centered in a camera
feed, using OpenCV's AprilTag detector and a feedback controller. There are
two versions of the same idea with the camera and tag swapped: a fixed
webcam watching a tag on the car, and a phone on the car looking at a fixed
tag.

## How it works

- **`AprilTagParking.py`:** the AprilTag is taped to a tower on the car; a
  stationary webcam watches the car drive back and forth and centers the tag
  in its own frame.
- **`PhoneCameraParking.py`:** the opposite setup. The AprilTag is
  stationary (taped to a wall, monitor or table) and an iPhone mounted on the
  car (via macOS Continuity Camera) streams its view back to the computer,
  which drives the car to center the tag in *that* feed.

In both, each frame goes through OpenCV's `cv2.aruco` detector (AprilTag
36h11 family, id 0). The horizontal distance between the tag's center and the
middle of the frame is the error, and a controller turns it into a single
forward/backward speed sent to the car over Bluetooth with `movement_move()`.
The controller is either a plain P controller or, with `SPRING_LOADED = True`,
a spring-damper that lets the car overshoot and settle back.

## Hardware

- LEGO Education Double Motor (the drivetrain) and its Connection Card
- A webcam (`AprilTagParking.py`), or an iPhone with Continuity Camera
  mounted on the car (`PhoneCameraParking.py`)
- A printed AprilTag: `apriltag_id0.png`

## Code

| File | What it does |
|---|---|
| `AprilTagParking.py` | Fixed webcam, tag on the car |
| `PhoneCameraParking.py` | Phone on the car, fixed tag |
| `AprilTagGenerator.py` | Generates the tag image `apriltag_id0.png` |
| `apriltag_id0.png` | The AprilTag to print (36h11 family, id 0) |
| `lelib.py` | Shared LEGO Education wrapper from the class library (not used by these scripts) |

## Setup and run

1. Install the packages (from the repo root, with `.venv` active):
   ```
   pip install -r "Mohammed's Projects/requirements.txt"
   ```
2. Print `apriltag_id0.png` (regenerate with `python AprilTagGenerator.py`
   if needed) and tape it to a tower on the car (`AprilTagParking.py`) or to
   a wall/monitor the car will drive toward (`PhoneCameraParking.py`).
3. Update `CARD_COLOR` / `CARD_SERIAL` at the top of the script to match the
   car's Double Motor Connection Card.
4. For `PhoneCameraParking.py` only: turn on **Continuity Camera Webcam**
   (iPhone Settings > General > AirPlay & Handoff), make sure the phone is
   signed into the same Apple ID, unlocked, and nearby, then mount it on the
   car facing the wall-mounted tag. Adjust `CAMERA_INDEX` if the wrong camera
   opens (the preview window makes it obvious which is the phone).
5. Run either script:
   ```
   python AprilTagParking.py
   python PhoneCameraParking.py
   ```
6. Press `q` in the video window to stop and disconnect cleanly.

## Tuning and notes

- `KP`, `MAX_SPEED` and `DEADBAND_PX` set how hard the car chases the
  center and when it counts as parked. `SPRING_K` and `SPRING_DAMPING` do
  the same for the spring-loaded version. The phone version uses gentler
  gains, because driving fast whips the phone's view around.
- Whether positive error should drive the car left or right depends on which
  way the camera/car are physically facing, which can't be known ahead of
  time — if the car drives away from center instead of toward it, flip the
  sign of `KP` (or `SPRING_K`). The two scripts' signs are tuned
  independently since the phone faces a different way on the car than the
  tag-tower setup does.
- If the car's hub fails to connect, both scripts still run in
  camera-preview-only mode so you can debug tag detection without hardware.

## Credits and links

- Answers to the assignment questions are on our group Notion site.
