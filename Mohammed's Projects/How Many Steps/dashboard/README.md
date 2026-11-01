# Dashboard

A live webpage for the step counter: total steps and distance (each with its ±
uncertainty), a scrolling chart of cadence, and the neural net's two hidden layers
of 16 neurons drawn as circles that glow brighter when their value is higher. It
listens to MQTT, so it works the same with the fake publisher now and the UNO Q
later.

## Message format

Whoever sends the data (`fake_publisher.py` now, the UNO Q later) publishes one JSON
message **twice a second** to:

- Broker: `broker.hivemq.com` (port 1883 for Python, `wss://broker.hivemq.com:8884/mqtt` for the page)
- Topic: `ME193/Mohammed/steps`

```json
{"t": 12.5, "steps": 18, "steps_unc": 1, "distance_m": 13.4, "distance_unc": 0.7,
 "cadence": 1.82, "speed": 1.37,
 "layer1": [0.0, 0.83, 0.12, "... 16 numbers"],
 "layer2": [0.41, 0.0, 1.07, "... 16 numbers"]}
```

| Field | Meaning | Unit |
|---|---|---|
| `t` | time since the sender started | s |
| `steps` | total steps counted so far | steps |
| `steps_unc` | ± uncertainty on `steps` | steps |
| `distance_m` | total distance so far | m |
| `distance_unc` | ± uncertainty on `distance_m` | m |
| `cadence` | current step rate | steps/s |
| `speed` | current speed | m/s |
| `layer1` | the 16 values of the net's first hidden layer (after ReLU, so ≥ 0) | – |
| `layer2` | the 16 values of the second hidden layer (after ReLU, so ≥ 0) | – |

"±" means the true value is probably within that much of the number shown. Both
uncertainties grow as the walk goes on, since small errors add up.

### Where the ± comes from

The ± is how far off the step counter really was when it was tested on trials it hadn't
seen (leave-one-trial-out, in `training/train_steps.py`), per pace, as the
root-mean-square error. For example: about 3% of the steps on a walk, 5% on a run.
Zero-step activities have no true total to take a percentage of, so for them it's false
steps (and meters) per second. The numbers are in `training/step_model.npz`, with a table
in `training/results.md`. Each half second, the sender picks the pace from the net's own
step rate and adds that pace's share to the running ±.

It is **not** the spread between the committee's 5 nets. The 5 nets agree with each
other far more closely than they agree with the truth: in testing, the spread was
usually 0.2-1.3 steps per trial, while the real error was more than twice that in 12 of 39
trials, up to 27 steps on a leg-swing trial. A ± from that spread would look confident and be wrong. The
leave-one-out error is measured against the truth, so it's honest about how far off the
count can be.

`fake_publisher.py` uses the same rule and the same numbers.

## Files

| File | What it does |
|---|---|
| `index.html` | The dashboard page. Self-contained: open it in a browser, no server needed |
| `fake_publisher.py` | Sends made-up but realistic messages, cycling through standing, walking, running and sitting while swinging a leg |

## Run it

1. Start the fake data (needs `paho-mqtt`, already in `Mohammed's Projects/requirements.txt`).
   From the repo root, with `.venv` active:

   ```
   python "Mohammed's Projects/How Many Steps/dashboard/fake_publisher.py"
   ```

2. Open `index.html` in a browser (double-click it, or `open index.html` from this
   folder on a Mac). The dot at the top turns green once it is connected, and the
   numbers update twice a second.

   On a phone: the page has to be reachable from the phone, for example via the
   repo's GitHub Pages or by running `python -m http.server` in this folder and
   opening `http://<laptop IP>:8000` on the same Wi-Fi.

## Notes

- `broker.hivemq.com` is a public broker: anyone can read the topic. Don't send
  anything private.
- The page scales each layer's brightness by the largest value seen in that layer
  over the last 10 s (at least 1), so the circles stay readable whatever range the
  real net's values end up in, while a layer of small values still looks dim.
