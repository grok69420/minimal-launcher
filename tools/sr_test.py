"""Developer tool: how sharp is the painted background? Paints 49 frames of a video (everyone
except the biggest person removed) and saves comparison pictures:
  /content/sr_cmp.jpg  rows: fast level enlarged | fast level + sharpener | sharpest level
python tools/sr_test.py video.mp4 first_frame"""
import os
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import remove_people as rp  # noqa: E402
from ultralytics import YOLO  # noqa: E402

src, start = sys.argv[1], int(sys.argv[2])
cap = cv2.VideoCapture(src)
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
frames = []
for _ in range(49):
    ok, f = cap.read()
    if not ok:
        break
    frames.append(f)
frames = frames[:((len(frames) - 1) // 4) * 4 + 1]
h, w = frames[0].shape[:2]
det = YOLO("yolo11x-seg.pt")
masks = []
grow = max(3, int(rp.GROW * max(w, h)))
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
print(len(frames), "frames", w, "x", h, "removed area", round(100 * np.mean([m.mean() for m in masks]), 1), "%")
filler = rp.MiniMaxFiller()
k = len(frames) // 2


def paint(area, steps):
    fw, fh = rp.fill_size(w, h, area)
    filler.fill(frames[:5], masks[:5], fw, fh, steps=steps)
    t = time.time()
    out = filler.fill(frames, masks, fw, fh, steps=steps)
    print(f"painted at {fw}x{fh}, {steps} steps: {len(frames) / (time.time() - t):.1f} frames/s")
    return out


def comp(img):
    o = frames[k].copy()
    o[masks[k]] = img[masks[k]]
    return o


fast = paint(512 * 288, 4)
lan = comp(cv2.resize(fast[k], (w, h), interpolation=cv2.INTER_LANCZOS4))
sh = rp.sharpener()
t = time.time()
srs = sh(fast, (w, h))
print(f"sharpener: {len(fast) / (time.time() - t):.0f} frames/s")
sr = comp(srs[k])
best = comp(cv2.resize(paint(832 * 480, 8)[k], (w, h), interpolation=cv2.INTER_LANCZOS4))
x1, y1, x2, y2 = (int(v) for v in rp._bbox(masks[k]))
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
X1, Y1 = int(np.clip(cx - 320, 0, w - 640)), int(np.clip(cy - 180, 0, h - 360))
crops = [im[Y1:Y1 + 360, X1:X1 + 640] for im in (frames[k], lan, sr, best)]
for c, t_ in zip(crops, ("original", "fast (as before)", "fast + sharpener (new)", "sharpest level")):
    cv2.putText(c, t_, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
cv2.imwrite("/content/sr_cmp.jpg", np.vstack([np.hstack(crops[:2]), np.hstack(crops[2:])]),
            [cv2.IMWRITE_JPEG_QUALITY, 92])


def flicker(seq):  # how much the painted area changes from frame to frame (lower = steadier)
    return float(np.mean([np.abs(seq[i + 1].astype(np.int16) - seq[i])[masks[i] & masks[i + 1]].mean()
                          for i in range(len(seq) - 1)]))


lans = [cv2.resize(o, (w, h), interpolation=cv2.INTER_LANCZOS4) for o in fast]
print(f"frame-to-frame change in painted area: enlarged {flicker(lans):.2f}, sharpened {flicker(srs):.2f}, "
      f"original video {flicker(frames):.2f}")


def sharpness(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F)[masks[k]].var())


print(f"detail in painted area (higher = sharper): enlarged {sharpness(lan):.0f}, sharpened {sharpness(sr):.0f}, "
      f"sharpest level {sharpness(best):.0f}, real video around it {sharpness(frames[k]):.0f}")
print("saved /content/sr_cmp.jpg")
