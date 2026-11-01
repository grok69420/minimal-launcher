"""Developer tool: the same moments from the original and two finished videos side by side.
python tools/compare_outputs.py original.mp4 old.mp4 new.mp4 [frame ...] -> /content/cmp_out.jpg"""
import sys

import cv2
import numpy as np

paths = sys.argv[1:4]
idx = [int(v) for v in sys.argv[4:]] or [600, 1500, 2400, 3300, 4200, 5100]
rows = []
for i in idx:
    row = []
    for name, p in zip(("original", "before", "now"), paths):
        cap = cv2.VideoCapture(p)
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        f = cv2.resize(f, (640, 360)) if ok else np.zeros((360, 640, 3), np.uint8)
        cv2.putText(f, f"{name} {i}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        row.append(f)
    rows.append(np.hstack(row))
cv2.imwrite("/content/cmp_out.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
print("saved /content/cmp_out.jpg")
