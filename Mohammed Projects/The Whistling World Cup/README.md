# The Whistling World Cup

Use `pyaudio` to grab a live microphone stream and use it to control the
robot: a high-pitched whistle speeds it up, a low-pitched whistle stops it,
and pitches in between steer it left or right.

On competition day, each team is assigned a role — **ball** or **goalie** —
and drives toward the goal once a `"start"` message is published over MQTT
on the topic `ME193/Rogers`. If the goalie gets close enough to the ball's
light sensor, the ball shuts down, publishes an MQTT "failed" message, and
plays a death song, while the goalie (subscribed to the same channel) plays
a song of success. If the ball reaches the goal first, it whistles a special
command that publishes the opposite MQTT messages instead.

## Requirements

- Python 3.8+
- Packages: `pyaudio`, `paho-mqtt`

```
pip install --upgrade pip
pip install pyaudio paho-mqtt
```

## Plan / TODO

- [ ] Capture and process the live audio stream with `pyaudio`
- [ ] Build a pitch-detection policy that maps whistle pitch to
      speed/turn/stop commands
- [ ] Display the live audio signal and the resulting decision on screen
- [ ] Wire up MQTT: subscribe to `ME193/Rogers` for the `"start"` trigger,
      and agree on the "success"/"failure" messages with the opponent team
- [ ] Handle the no-whistle case (robot should hold/stop, not react to
      silence or noise)
- [ ] Filter out background/unwanted noise from the whistle signal

## Notes

No code here yet — this folder is a placeholder for the assignment.
