"""Developer tool: one picture of the blending steps saved with KOP_DEBUG_DIR (a row per frame:
removed area | painted | after real background | final). python tools/dbg_grid.py [dir]"""
import glob
import os
import sys

import cv2
import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "/content/dbg"
frames = sorted({os.path.basename(p)[:6] for p in glob.glob(os.path.join(d, "*_d_final.jpg"))})
rows = []
for f in frames:
    row = []
    for k, name in (("b_mask", "removed area"), ("a_painted", "painted"), ("c_real", "+ real background"),
                    ("d_final", "final")):
        im = cv2.imread(os.path.join(d, f"{f}_{k}.jpg"))
        im = cv2.resize(im, (640, 360)) if im is not None else np.zeros((360, 640, 3), np.uint8)
        cv2.putText(im, f"{int(f)} {name}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        row.append(im)
    rows.append(np.hstack(row))
cv2.imwrite("/content/dbg_grid.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved /content/dbg_grid.jpg", len(rows), "frame(s)")
