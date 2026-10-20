# Door-to-door Service (HW4)

Use a YOLO object-detection model, trained on our own photos, to find LEGO
minifigures in the laptop camera feed, and send their position over MQTT to
an Arduino UNO Q. The UNO Q shows where the minifig is on its LED matrix and
drives a DC-motor car until the minifig is parked in the middle of the
camera's view. The final demo is two cars run from the same computer: one
stops with the green minifig on the left, the other with the blue minifig on
the right.

## How it works

```
laptop camera ─► YOLO model ─► detect_publish.py ─► MQTT (broker.hivemq.com) ─► UNO Q ─► LED matrix / DC motors
```

### Part 1: find the minifig

`YOLO/detect_publish.py` runs our two-class model (`green_minifig`,
`blue_minifig`) on the laptop camera and publishes where each minifig is as
JSON, for example `{"x": 412.0, "y": 230.5, "w": 640, "h": 480, "conf": 0.91}`,
to `ME193/Mohammed/green` and `ME193/Mohammed/blue`. The UNO Q app
`mqtt-minifig-monitor` subscribes to the green topic and draws a dot at the
matching (scaled) spot on its LED matrix.

### Part 2: park the car on the center

The camera stays fixed and watches the car, which carries the green minifig
as its marker. `YOLO-green-car/detect_publish.py` finds the minifig, measures
how far it is from the center of the frame, and a PD controller turns that
into one forward/backward speed. It publishes the speed for each motor to
`ME193/Luca/green`. The UNO Q app `mqtt-minifig-drive` passes those speeds
straight to the motors and stops them if messages stop arriving.

## Hardware

- A laptop with a webcam (fixed in place, looking along the track)
- Arduino UNO Q, connected to Wi-Fi, using its LED matrix
- A car with two DC motors on a dual-PWM motor driver (M1A/M1B and
  M2A/M2B). The pins are set at the top of
  `ArduinoApps/mqtt-minifig-drive/sketch/sketch.ino`.
- A green and a blue LEGO minifigure

## Code

| Folder | What's in it |
| --- | --- |
| [YOLO](YOLO/) | My two-class model (green and blue minifigs), used for Part 1: the Roboflow dataset, `train.py` (fine-tunes YOLOv8 nano), the trained model `best.pt`, and `detect_publish.py` (runs the model on the laptop camera and publishes each minifig's position over MQTT) |
| [YOLO-green-car](YOLO-green-car/) | Luca's single-class model (`Minifig`) plus the PD controller that drives the car, used for Part 2: the dataset, `train.py`, `best.pt`, and `detect_publish.py` (finds the minifig on the car and publishes the speed that parks it at the center of the frame) |
| [ArduinoApps/mqtt-minifig-monitor](ArduinoApps/mqtt-minifig-monitor/) | UNO Q app for Part 1: shows the minifig's position on the LED matrix |
| [ArduinoApps/mqtt-minifig-drive](ArduinoApps/mqtt-minifig-drive/) | Luca's UNO Q app for Part 2: shows the minifig's position on the LED matrix and sends the left/right speeds it receives over MQTT straight to the two DC motors, stopping them if messages stop arriving |
| [ArduinoApps](ArduinoApps/) (others) | Practice UNO Q apps: LED blink, IP/temperature scroller, MQTT LED matrix |

## Setup and run

1. Install YOLO and MQTT (from the repo root, with `.venv` active):
   ```
   pip install -r "Mohammed's Projects/Door-to-door Service/YOLO/requirements.txt"
   ```
2. Deploy the UNO Q app with Arduino App Lab: `mqtt-minifig-monitor` for
   Part 1, or `mqtt-minifig-drive` for Part 2.
3. Run the detector from its own folder:
   ```
   cd "Mohammed's Projects/Door-to-door Service/YOLO"            # Part 1
   python detect_publish.py

   cd "Mohammed's Projects/Door-to-door Service/YOLO-green-car"  # Part 2
   python detect_publish.py
   ```
4. Press `q` in the video window to quit.

To retrain a model, run `python train.py` in that model's folder. Each
folder's README has the details.

## Tuning and notes

- If the detector opens the wrong camera (for example your iPhone), change
  `CAMERA` at the top of `detect_publish.py` to `1`.
- Part 2's gains, deadzone and speed limits are trackbars on the preview
  window, so you can tune them live (see the
  [YOLO-green-car README](YOLO-green-car/README.md)).
- The broker and topic in `detect_publish.py` must match the UNO Q app's
  `MQTT_BROKER` and `MQTT_TOPIC`.

### Status

- [x] Collect and label images of the green and blue minifigs
- [x] Train a YOLO model to detect both minifigs
- [x] Run the model on the live camera feed and find each minifig's position
- [x] Publish the position over MQTT
- [x] UNO Q: subscribe and draw a blue dot at the scaled position on the LED display
- [x] UNO Q: drive the DC motors forward/backward until the minifig is centered, then stop
- [ ] Get two cars running from one computer (green minifig on the left, blue on the right)
- [x] Put the code, GitHub link and answers to the questions on the group Notion site

## Credits and links

- The Part 2 car and its code (`YOLO-green-car` and
  `ArduinoApps/mqtt-minifig-drive`) are by my teammate Luca, copied from
  [Lucalo44/ME193-Code](https://github.com/Lucalo44/ME193-Code/tree/main/Door2Door).
- Answers to the assignment questions are on our group Notion site.
