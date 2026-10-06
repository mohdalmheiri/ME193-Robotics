# Door-to-door Service

Use a YOLO object-detection model on the laptop camera to find LEGO
minifigures and send their position over MQTT to an Arduino UNO Q. The
UNO Q shows where the minifig is and drives a DC-motor car toward it.

The assignment has two parts:

1. **Find the minifig.** Detect a green LEGO minifigure in the camera
   image, publish its location over MQTT, and have the UNO Q draw a blue
   dot at the matching (scaled) spot on its LED display.
2. **Park on it.** Repeat the AprilTag Parking assignment with an Arduino
   and DC motors instead of LEGO. The UNO Q receives the minifig position
   over MQTT and drives forward or backward until the minifig is in the
   middle of the computer screen, then stops.

The final demo is two working cars, both run from the same computer: one
stops with the green minifig on the left, the other with the blue minifig
on the right.

The work has to use Python, GitHub and YOLO. Training the model ourselves
is part of it, so Roboflow can't do everything.

## Plan / TODO

- [x] Collect and label images of the green and blue minifigs
- [x] Train a YOLO model to detect both minifigs
- [x] Run the model on the live camera feed and find each minifig's position
- [x] Publish the position over MQTT
- [x] UNO Q: subscribe and draw a blue dot at the scaled position on the LED display
- [x] UNO Q: drive the DC motors forward/backward until the minifig is centered, then stop
- [ ] Get two cars running from one computer (green minifig on the left, blue on the right)
- [x] Put the code, GitHub link and answers to the questions on the group Notion site

## Questions to answer

- Describe the policy: how does it make decisions?
- What does the code do if no minifigure is detected?
- How good is the model? Can you confuse it? If so, how (a different
  color minifigure, etc.)?

## Folders

| Folder | What's in it |
| --- | --- |
| [ArduinoApps](ArduinoApps/) | Arduino App Lab apps for the UNO Q: LED blink, IP/temperature scroller, MQTT LED matrix and MQTT minifig monitor |
| [ArduinoApps/mqtt-minifig-drive](ArduinoApps/mqtt-minifig-drive/) | Luca's UNO Q app for Part 2: shows the minifig's position on the LED matrix and sends the left/right speeds it receives over MQTT straight to the two DC motors, stopping them if messages stop arriving |
| [YOLO](YOLO/) | My two-class model (green and blue minifigs), used for Part 1: the Roboflow dataset, `train.py` (fine-tunes YOLOv8 nano), the trained model `best.pt`, and `detect_publish.py` (runs the model on the laptop camera and publishes each minifig's position over MQTT) |
| [YOLO-green-car](YOLO-green-car/) | Luca's single-class model (`Minifig`) plus the PD controller that drives the car, used for Part 2: the dataset, `train.py`, `best.pt`, and `detect_publish.py` (finds the minifig on the car and publishes the speed that parks it at the center of the frame) |

The Part 2 car and its code (`YOLO-green-car` and `ArduinoApps/mqtt-minifig-drive`) are by my teammate Luca, copied from [Lucalo44/ME193-Code](https://github.com/Lucalo44/ME193-Code/tree/main/Door2Door).
