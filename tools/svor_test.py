"""Developer tool: film painter (SVOR) vs quick painter (MiniMax) on the same frames.
python tools/svor_test.py video.mp4 first_frame [n_frames] [mask_video]
-> speeds + /content/svor_cmp.jpg (rows: crop around the removed area, whole frame)"""
import os
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import remove_people as rp  # noqa: E402

src, start = sys.argv[1], int(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 49
mask_src = sys.argv[4] if len(sys.argv) > 4 else None
cap = cv2.VideoCapture(src)
cap.set(cv2.CAP_PROP_POS_FRAMES, start)
frames = []
for _ in range(n):
    ok, f = cap.read()
    if not ok:
        break
    frames.append(f)
frames = frames[:((len(frames) - 1) // 4) * 4 + 1]
h, w = frames[0].shape[:2]
masks = []
if mask_src:
    mc = cv2.VideoCapture(mask_src)
    mc.set(cv2.CAP_PROP_POS_FRAMES, start)
    for _ in frames:
        ok, m = mc.read()
        masks.append(cv2.cvtColor(m, cv2.COLOR_BGR2GRAY) > 127)
else:
    from ultralytics import YOLO
    det = YOLO("yolo11x-seg.pt")
    grow = max(3, int(rp.GROW * max(w, h)))
    for f in frames:
        r = det.predict(f, classes=[0], conf=0.15, iou=0.8, imgsz=1280, retina_masks=True, verbose=False)[0]
        m = np.zeros((h, w), bool)
        if r.masks is not None and len(r.boxes) > 1:
            b = r.boxes.xyxy.cpu().numpy()
            keep = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
            for k, mk in enumerate(r.masks.data.cpu().numpy()):
                if k != keep:
                    m |= mk > 0.5
        masks.append(cv2.dilate(m.view(np.uint8), np.ones((grow, grow), np.uint8)) > 0)
print(len(frames), "frames", w, "x", h, "removed area", round(100 * np.mean([m.mean() for m in masks]), 1), "%",
      flush=True)
k = len(frames) // 2
fw, fh = rp.fill_size(w, h, 832 * 480)
results = []


def run(name, filler, **kw):
    torch.cuda.synchronize()
    t = time.time()
    out = filler.fill(frames, masks, fw, fh, **kw)
    torch.cuda.synchronize()
    dt = time.time() - t
    print(f"{name}: {len(frames) / dt:.2f} frames/s ({dt:.0f} s for {len(frames)} frames), "
          f"GPU memory peak {torch.cuda.max_memory_allocated() / 1e9:.1f} GB", flush=True)
    up = cv2.resize(out[k], (w, h), interpolation=cv2.INTER_LANCZOS4)
    results.append((f"{name} {len(frames) / dt:.2f} f/s", up))


if os.environ.get("KOP_SKIP_MM") != "1":
    mm = rp.MiniMaxFiller()
    mm.use_tae(True)
    run("quick (MiniMax 832x480, 6 steps)", mm, steps=6)
    del mm
    torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
sv = rp.SVORFiller()
# configurations "steps:guidance" separated by commas, e.g. KOP_SVOR_CFGS=20:6,12:6,12:4
for c in os.environ.get("KOP_SVOR_CFGS", "20:6,10:1").split(","):
    steps, g = c.split(":")
    sv.guidance = float(g)
    run(f"film (SVOR {steps} steps, guidance {g})", sv, steps=int(steps))
x1, y1, x2, y2 = (int(v) for v in rp._bbox(masks[k])) if masks[k].any() else (0, 0, w, h)
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
cw, ch = min(w, 640), min(h, 360)
X1, Y1 = int(np.clip(cx - cw // 2, 0, w - cw)), int(np.clip(cy - ch // 2, 0, h - ch))
crops, fulls = [], []
for name, img in [("original", frames[k])] + results:
    c = img[Y1:Y1 + ch, X1:X1 + cw].copy()
    if name != "original":  # where the painter changed the picture outside the mask (shadows ...)
        d = cv2.GaussianBlur(np.abs(img.astype(np.int16) - frames[k]).max(2).astype(np.uint8), (0, 0), 2)
        d[masks[k]] = 0
        c[d[Y1:Y1 + ch, X1:X1 + cw] > 25] //= 2
        c[d[Y1:Y1 + ch, X1:X1 + cw] > 25] += np.uint8([0, 64, 64])
    cv2.putText(c, name[:48], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    crops.append(c)
    fulls.append(cv2.resize(img, (cw, ch)))
cv2.imwrite("/content/svor_cmp.jpg", np.vstack([np.hstack(crops), np.hstack(fulls)]),
            [cv2.IMWRITE_JPEG_QUALITY, 90])
print("saved /content/svor_cmp.jpg (yellow tint = changed outside the mask, e.g. shadows removed)")
