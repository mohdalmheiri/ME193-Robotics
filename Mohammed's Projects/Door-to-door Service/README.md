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

- [ ] Collect and label images of the green and blue minifigs
- [ ] Train a YOLO model to detect both minifigs
- [ ] Run the model on the live camera feed and find each minifig's position
- [ ] Publish the position over MQTT
- [ ] UNO Q: subscribe and draw a blue dot at the scaled position on the LED display
- [ ] UNO Q: drive the DC motors forward/backward until the minifig is centered, then stop
- [ ] Get two cars running from one computer (green minifig on the left, blue on the right)
- [ ] Put the code, GitHub link and answers to the questions on the group Notion site

## Questions to answer

- Describe the policy: how does it make decisions?
- What does the code do if no minifigure is detected?
- How good is the model? Can you confuse it? If so, how (a different
  color minifigure, etc.)?

## Folders

| Folder | What's in it |
| --- | --- |
| [ArduinoApps](ArduinoApps/) | Arduino App Lab apps for the UNO Q: LED blink, IP/temperature scroller, MQTT LED matrix and MQTT minifig monitor |
| [YOLO](YOLO/) | Script that fine-tunes a YOLOv8 nano model to detect the green and blue minifigs, plus the Roboflow dataset it trains on |
