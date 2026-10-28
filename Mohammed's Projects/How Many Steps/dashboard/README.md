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
uncertainties should grow as the walk goes on, since small errors add up.

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
