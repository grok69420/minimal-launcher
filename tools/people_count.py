"""Developer tool: counts the people a detector still sees in a finished video, next to the
original. Keep-one-person: the ideal result shows 1 person per picture.
python tools/people_count.py original.mp4 finished.mp4 [every_nth_frame=6] [conf=0.3]"""
import sys

import cv2
import numpy as np
from ultralytics import YOLO

orig, done = sys.argv[1], sys.argv[2]
every = int(sys.argv[3]) if len(sys.argv) > 3 else 6
conf = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
det = YOLO("/content/yolo11x.pt")


def count(path):
    cap, out, batch, i = cv2.VideoCapture(path), [], [], 0

    def flush():
        for r in det.predict(batch, classes=[0], conf=conf, imgsz=1280, verbose=False):
            out.append(len(r.boxes))
        batch.clear()
    while True:
        ok, im = cap.read()
        if not ok:
            break
        if i % every == 0:
            batch.append(im)
            if len(batch) == 8:
                flush()
        i += 1
    if batch:
        flush()
    return np.array(out)


a, b = count(orig), count(done)
n = min(len(a), len(b))
a, b = a[:n], b[:n]
print(f"PEOPLE {n} pictures checked (every {every}th), detector confidence {conf}")
print(f"  original: {a.mean():.2f} people per picture")
print(f"  finished: {b.mean():.2f} people per picture; more than one person in "
      f"{100 * (b > 1).mean():.1f}% of pictures; extra people in total {int(np.maximum(b - 1, 0).sum())}")
worst = np.argsort(-b)[:8]
print("  worst pictures (frame: people):", ", ".join(f"{int(k) * every}: {int(b[k])}" for k in sorted(worst)))
