# Assignment Name (HWn)

One paragraph on the overall goal: what the robot does, what controls it,
and what AI or control idea the assignment is about. Keep it to what a
classmate needs to understand the project in 30 seconds.

## How it works

How the pieces fit together: what the laptop senses (camera, mic, sensors),
how the code turns that into decisions, and how the commands reach the robot.
A small diagram or table helps. Assignment-specific details go here as `###`
subsections (for example MQTT topics, match logic, the behavior tree).

Describe the system, not the assignment's reflection questions. Those
answers stay off GitHub.

## Hardware

- Robot parts (LEGO hubs, Arduino UNO Q, motors, sensors) and how they connect
- Anything else needed (webcam, phone, printed tags, instruments)
- Wiring, if there is any

## Files

| File | What it does |
|---|---|
| `main_script.py` | The program you run |
| `helpers/` | Supporting code, grouped into folders |
| `models/`, `data/` | Trained models, datasets, images to print |

## Setup and run

1. Install: `pip install -r "Mohammed's Projects/requirements.txt"` (or the
   project's own `requirements.txt`) from the repo root, with `.venv` active.
2. Configure: constants to fill in first (connection cards, MQTT topics).
3. Run:

   ```
   python main_script.py
   ```

## Tuning and notes

- The constants worth changing and what they do
- Known limitations and troubleshooting

## Credits

Only include this section when some of the code comes from someone else:
who wrote what, with a link to the original.
