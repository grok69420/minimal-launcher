"""Developer tool: where the time of one background painting goes (A100).
python tools/prof_mm.py [width height frames steps]"""
import os
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np  # noqa: E402
import torch  # noqa: E402
import remove_people as rp  # noqa: E402

W, H, F, S = (int(v) for v in (sys.argv[1:5] if len(sys.argv) > 4 else (512, 288, 49, 4)))
f = rp.MiniMaxFiller()
pipe = f.pipe
T = {}


def timed(name, fn):
    def wrap(*a, **k):
        torch.cuda.synchronize()
        t = time.time()
        r = fn(*a, **k)
        torch.cuda.synchronize()
        T[name] = T.get(name, 0.0) + time.time() - t
        return r
    return wrap


pipe.vae.encode = timed("vae encode (x2)", pipe.vae.encode)
pipe.vae.decode = timed("vae decode", pipe.vae.decode)
pipe.transformer.forward = timed(f"transformer ({S} steps)", pipe.transformer.forward)
rng = np.random.default_rng(0)
imgs = [rng.integers(0, 255, (H, W, 3), dtype=np.uint8) for _ in range(F)]
masks = [np.zeros((H, W), bool) for _ in range(F)]
for m in masks:
    m[H // 4:3 * H // 4, W // 3:2 * W // 3] = True
f.fill(imgs, masks, W, H, steps=S)  # warm-up
for rep in range(2):
    T.clear()
    torch.cuda.synchronize()
    t = time.time()
    out = f.fill(imgs, masks, W, H, steps=S)
    torch.cuda.synchronize()
    tot = time.time() - t
    print(f"--- {W}x{H}, {F} frames, {S} steps: {tot:.2f} s = {F / tot:.1f} frames/s")
    for k, v in T.items():
        print(f"  {k:26s} {v:6.2f} s ({100 * v / tot:4.1f} %)")
    print(f"  {'other (resize, copies)':26s} {tot - sum(T.values()):6.2f} s")

sh = rp.sharpener()
if sh is not None:
    for size in ((1280, 720), (854, 480)):
        sh(out[:8], size)
        torch.cuda.synchronize()
        t = time.time()
        sh(out, size)
        torch.cuda.synchronize()
        dt = time.time() - t
        print(f"sharpen {F} frames {W}x{H} -> {size[0]}x{size[1]}: {dt:.2f} s = {F / dt:.0f} frames/s")
