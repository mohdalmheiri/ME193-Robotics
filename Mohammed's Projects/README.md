# ME193-3: AI in Mobile Robots

My ME193-3 (AI in Mobile Robots) coursework and projects.

## Assignments

| Folder | Assignment | Summary |
|---|---|---|
| [`Pose Race/`](./Pose%20Race) | Pose Race (HW1) | Control a LEGO car with arm gestures tracked via webcam + MediaPipe Pose |
| [`AprilTag Parking/`](./AprilTag%20Parking) | AprilTag Parking (HW2) | Drive a LEGO car to center an AprilTag in a webcam (or phone-camera) feed using a P/spring controller |
| [`The Whistling World Cup/`](./The%20Whistling%20World%20Cup) | The Whistling World Cup (HW3) | Drive a LEGO car with recorder notes and claps picked up by the laptop mic, playing ball vs. goalie over MQTT |
| [`Door-to-door Service/`](./Door-to-door%20Service) | Door-to-door Service (HW4) | Detect LEGO minifigs with a YOLO model on the laptop camera and send their position over MQTT to an Arduino UNO Q car |
| [`A Little Ping Pong/`](./A%20Little%20Ping%20Pong) | A Little Ping Pong (Midterm) | Augmented-reality ping-pong against a virtual opponent: a LEGO Double Motor is the paddle (AprilTag + MediaPipe tracking, trained IMU swing classifier, haptics), with the live score over MQTT on an Arduino UNO Q scoreboard |
| [`Sumo Wrestling/`](./Sumo%20Wrestling) | Sumo Wrestling (HW5) | LEGO sumo robot with shared control: a behavior tree fuses the controller levers with a color sensor (tape edge) and an HC-SR04 on an Arduino UNO Q over MQTT (opponent boost) |

## Setup

All the laptop-side code runs from one virtual environment at the root of
the repo. From the repo root:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r "Mohammed's Projects/requirements.txt"
```

That covers Pose Race, AprilTag Parking, The Whistling World Cup and A Little Ping Pong.
`pyaudio` (for The Whistling World Cup) also needs the PortAudio library;
see that project's README.

Door-to-door Service has its own requirements, since YOLO is a big install:

```
pip install -r "Mohammed's Projects/Door-to-door Service/YOLO/requirements.txt"
```

The `ArduinoApps` in Door-to-door Service and the `unoq_scoreboard` app in A Little
Ping Pong run on the Arduino UNO Q, not the laptop; see their READMEs for deploying.

Some of the code here comes from classmates' repos. Those projects'
READMEs say which parts and link to the original.
