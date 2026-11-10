"""Developer tool: paint every frame vs every 2nd / 3rd frame (frames between follow the
camera). python tools/stride_test.py video.mp4 first_frame [n_frames]
-> speeds + /content/stride_cmp.jpg (rows: in-between frames; columns: stride 1 / 2 / 3)"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import remove_people as rp  # noqa: E402
from ultralytics import YOLO  # noqa: E402

src, start = sys.argv[1], int(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 97
tmp = tempfile.mkdtemp()
cap = cv2.VideoCapture(src)
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
paths, imgs = [], []
for i in range(n):
    ok, f = cap.read()
    if not ok:
        break
    imgs.append(f)
    paths.append(os.path.join(tmp, f"{i:06d}.jpg"))
    cv2.imwrite(paths[-1], f, [cv2.IMWRITE_JPEG_QUALITY, 95])
n = len(imgs)
h, w = imgs[0].shape[:2]
det = YOLO("yolo11x-seg.pt")
final = os.path.join(tmp, "final")
os.makedirs(final)
grow = max(3, int(rp.GROW * max(w, h)))
masks = []
for i, f in enumerate(imgs):
    r = det.predict(f, classes=[0], conf=0.15, iou=0.8, imgsz=1280, retina_masks=True, verbose=False)[0]
    m = np.zeros((h, w), bool)
    if r.masks is not None and len(r.boxes) > 1:
        b = r.boxes.xyxy.cpu().numpy()
        keep = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
        for k, mk in enumerate(r.masks.data.cpu().numpy()):
            if k != keep:
                m |= mk > 0.5
    m = cv2.dilate(m.view(np.uint8), np.ones((grow, grow), np.uint8)) > 0
    masks.append(m)
    rp._write_now(rp._mpath(final, i), m)
flags = {i: bool(masks[i].any()) for i in range(n)}
filler = rp.MiniMaxFiller()
filler.use_tae(True)

outs = {}
for stride in (1, 2, 3):
    work = os.path.join(tmp, f"w{stride}")
    torch.cuda.synchronize()
    t = time.time()
    chs, res = rp.fill_realistic(paths, final, flags, work, [(0, n)], w, h, filler,
                                 window=49 * stride, overlap=8, steps=6, stride=stride)
    rp.flush_masks()
    dt = time.time() - t
    print(f"stride {stride}: {n / dt:.1f} frames/s ({len(chs)} piece(s))", flush=True)
    outs[stride] = [rp._inpainted_frame(g, chs, res, 8, (w, h)) for g in range(n)]


def comp(img, g):
    o = imgs[g].copy()
    o[masks[g]] = img[masks[g]]
    return o


def flicker(seq):
    return float(np.mean([np.abs(seq[i + 1].astype(np.int16) - seq[i])[masks[i] & masks[i + 1]].mean()
                          for i in range(len(seq) - 1)]))


for stride in (1, 2, 3):
    print(f"stride {stride}: frame-to-frame change in painted area {flicker(outs[stride]):.2f}")
x1, y1, x2, y2 = (int(v) for v in rp._bbox(masks[n // 2]))
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
X1, Y1 = int(np.clip(cx - 320, 0, w - 640)), int(np.clip(cy - 180, 0, h - 360))
rows = []
for g in (n // 2 - 1, n // 2, n // 2 + 1):
    row = []
    for stride in (1, 2, 3):
        c = comp(outs[stride][g], g)[Y1:Y1 + 360, X1:X1 + 640].copy()
        cv2.putText(c, f"frame {g}, every {stride}. frame painted", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 255, 255), 2)
        row.append(c)
    rows.append(np.hstack(row))
cv2.imwrite("/content/stride_cmp.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved /content/stride_cmp.jpg")
