"""Speed test of the realistic-fill model on this GPU (developer tool).
python tools/bench_fill.py [video]  - uses the newest job's master copy if no video is given."""
import glob
import os
import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import remove_people as rp  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else max(
    glob.glob("/content/drive/MyDrive/Keep One Person/In progress (automatic)/*/master.mp4"),
    key=os.path.getmtime)
cap = cv2.VideoCapture(src)
cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
imgs = [cap.read()[1] for _ in range(81)]
h, w = imgs[0].shape[:2]
masks = []
for k in range(81):  # a person-sized hole moving across the picture
    m = np.zeros((h, w), bool)
    x = int(w * (0.25 + 0.3 * k / 80))
    m[h // 5:h, x:x + w // 7] = True
    masks.append(m)
t = time.time()
f = rp.MiniMaxFiller()
print(f"model loaded in {time.time() - t:.1f} s", flush=True)
out = None
CONFIGS = [(6, 640, 368, 49), (6, 640, 368, 49), (4, 640, 368, 49), (4, 512, 288, 49),
           (4, 512, 288, 81), (8, 832, 480, 49)]
if os.environ.get("BENCH_CONFIGS"):  # e.g. "4x512x288x49,6x640x368x49"
    CONFIGS = [tuple(int(v) for v in c.split("x")) for c in os.environ["BENCH_CONFIGS"].split(",")]
for steps, fw, fh, nf in CONFIGS:
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t = time.time()
    out = f.fill(imgs[:nf], masks[:nf], fw, fh, steps=steps)
    torch.cuda.synchronize()
    dt = time.time() - t
    print(f"steps={steps} {fw}x{fh} frames={nf}: {dt:.1f} s = {nf / dt:.1f} frames/s, "
          f"GPU memory {torch.cuda.max_memory_allocated() / 1e9:.1f} GB", flush=True)
cv2.imwrite("/content/bench_fill.jpg",
            np.hstack([cv2.resize(imgs[40], (832, 480)), cv2.resize(out[40], (832, 480))]))
