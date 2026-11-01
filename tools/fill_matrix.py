"""Developer tool: painting quality vs speed for several sizes / step counts / decoders.
python tools/fill_matrix.py video.mp4 first_frame  -> speeds + /content/fill_matrix.jpg"""
import os
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import remove_people as rp  # noqa: E402
from ultralytics import YOLO  # noqa: E402

src, start = sys.argv[1], int(sys.argv[2])
cap = cv2.VideoCapture(src)
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
frames = [cap.read()[1] for _ in range(49)]
h, w = frames[0].shape[:2]
det = YOLO("yolo11x-seg.pt")
grow = max(3, int(rp.GROW * max(w, h)))
masks = []
for f in frames:
    r = det.predict(f, classes=[0], conf=0.2, imgsz=960, retina_masks=True, verbose=False)[0]
    m = np.zeros((h, w), bool)
    if r.masks is not None and len(r.boxes) > 1:
        b = r.boxes.xyxy.cpu().numpy()
        keep = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
        for k, mk in enumerate(r.masks.data.cpu().numpy()):
            if k != keep:
                m |= mk > 0.5
    masks.append(cv2.dilate(m.view(np.uint8), np.ones((grow, grow), np.uint8)) > 0)
filler = rp.MiniMaxFiller()
k = 24
x1, y1, x2, y2 = (int(v) for v in rp._bbox(masks[k]))
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
X1, Y1 = int(np.clip(cx - 320, 0, w - 640)), int(np.clip(cy - 180, 0, h - 360))


def label(img, text):
    c = img[Y1:Y1 + 360, X1:X1 + 640].copy()
    cv2.putText(c, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    return c


tiles = [label(frames[k], "original")]
CONFIGS = [(512 * 288, 4, False), (512 * 288, 6, False), (640 * 368, 5, False), (640 * 368, 6, False),
           (832 * 480, 6, False), (832 * 480, 6, True), (640 * 368, 6, True), (832 * 480, 8, False)]
for area, steps, tae in CONFIGS:
    filler.use_tae(tae)
    fw, fh = rp.fill_size(w, h, area)
    filler.fill(frames[:5], masks[:5], fw, fh, steps=steps)
    torch.cuda.synchronize()
    t = time.time()
    out = filler.fill(frames, masks, fw, fh, steps=steps)
    torch.cuda.synchronize()
    fps = len(frames) / (time.time() - t)
    o = frames[k].copy()
    up = cv2.resize(out[k], (w, h), interpolation=cv2.INTER_LANCZOS4)
    o[masks[k]] = up[masks[k]]
    name = f"{fw}x{fh} {steps} steps{' tiny dec' if tae else ''}: {fps:.1f} f/s"
    print(name, flush=True)
    tiles.append(label(o, name))
while len(tiles) % 3:
    tiles.append(np.zeros_like(tiles[0]))
grid = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
cv2.imwrite("/content/fill_matrix.jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved /content/fill_matrix.jpg")
