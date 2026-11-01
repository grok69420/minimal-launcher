"""Developer tool: how many people does the scan find in crowded frames, per setting?
python tools/det_test.py video.mp4 [frame ...]   -> counts, speed, /content/det_cmp.jpg"""
import sys
import time

import cv2
import numpy as np
import torch
import torchvision
from ultralytics import YOLO

src = sys.argv[1]
idx = [int(v) for v in sys.argv[2:]] or [600, 1500, 2400, 3300, 4200, 5100, 6000]
cap = cv2.VideoCapture(src)
frames = []
for i in idx:
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = cap.read()
    if ok:
        frames.append(f)
h, w = frames[0].shape[:2]
m = YOLO("yolo11x-seg.pt")


def run(imgs, imgsz, conf, iou):
    return m.predict(imgs, classes=[0], conf=conf, iou=iou, imgsz=imgsz, verbose=False, device=0,
                     quantize=16, retina_masks=False)


def plain(imgsz, conf, iou):
    return [r.boxes.xyxy.cpu() for r in run(frames, imgsz, conf, iou)], None


def tiled(imgsz, conf, iou):
    """whole frame + 2x2 overlapping tiles; boxes merged (people cut by a tile edge are dropped
    when the whole-frame pass or another tile has them)."""
    tw, th = int(w * 0.6), int(h * 0.6)
    offs = [(0, 0), (w - tw, 0), (0, h - th), (w - tw, h - th)]
    full = run(frames, imgsz, conf, iou)
    out = []
    for k, f in enumerate(frames):
        tiles = [f[y:y + th, x:x + tw] for x, y in offs]
        res = run(tiles, imgsz, conf, iou)
        bs, ss = [full[k].boxes.xyxy.cpu()], [full[k].boxes.conf.cpu()]
        for (x, y), r in zip(offs, res):
            b = r.boxes.xyxy.cpu().clone()
            edge = ((b[:, 0] < 2) & (x > 0)) | ((b[:, 1] < 2) & (y > 0)) | \
                   ((b[:, 2] > tw - 2) & (x + tw < w)) | ((b[:, 3] > th - 2) & (y + th < h))
            b, c = b[~edge], r.boxes.conf.cpu()[~edge]
            b[:, [0, 2]] += x
            b[:, [1, 3]] += y
            bs.append(b)
            ss.append(c)
        b, s = torch.cat(bs), torch.cat(ss)
        out.append(b[torchvision.ops.nms(b, s, iou)])
    return out, None


CONFIGS = [("now: 960, conf .20, iou .70", plain, (960, 0.20, 0.70)),
           ("960, conf .12, iou .85", plain, (960, 0.12, 0.85)),
           ("1280, conf .15, iou .80", plain, (1280, 0.15, 0.80)),
           ("960 + 4 tiles, conf .15, iou .80", tiled, (960, 0.15, 0.80))]
results = {}
for name, fn, args in CONFIGS:
    fn(*args)  # warm-up
    torch.cuda.synchronize()
    t = time.time()
    boxes, _ = fn(*args)
    torch.cuda.synchronize()
    dt = (time.time() - t) / len(frames)
    results[name] = boxes
    print(f"{name:34s} people per frame {[len(b) for b in boxes]} total {sum(len(b) for b in boxes)}"
          f"  ({1 / dt:.0f} frames/s)")
rows = []
for k in range(min(3, len(frames))):
    tiles = []
    for name in (CONFIGS[0][0], CONFIGS[-1][0]):
        img = frames[k].copy()
        for b in results[name][k].numpy().astype(int):
            cv2.rectangle(img, tuple(b[:2]), tuple(b[2:]), (0, 255, 255), 2)
        cv2.putText(img, f"{name}: {len(results[name][k])}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1,
                    (0, 255, 0), 3)
        tiles.append(cv2.resize(img, (640, 360)))
    rows.append(np.hstack(tiles))
cv2.imwrite("/content/det_cmp.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved /content/det_cmp.jpg")
