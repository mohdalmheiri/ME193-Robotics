# YOLO

Trains a YOLOv8 nano model to detect two classes, `green_minifig` and
`blue_minifig`. It starts from `yolov8n.pt` (pretrained on COCO) and
fine-tunes it on our own photos.

## Dataset

Put the Roboflow YOLOv8 export in `YOLO/dataset/`, so that
`YOLO/dataset/data.yaml` exists next to the `train/`, `valid/` and
`test/` folders.

## Install

```
pip install -r requirements.txt
```

## Run

From this folder:

```
python train.py
```

It trains on the Apple Silicon GPU (`mps`) and falls back to the CPU if
that isn't available. When it finishes, the trained model is copied to
`YOLO/best.pt`. The full training output stays in `runs/`, which git
ignores.
