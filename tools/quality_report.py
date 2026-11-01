"""Developer tool: how close the finished video stays to the original where nothing was removed.
python tools/quality_report.py original.mp4 finished.mp4"""
import subprocess
import sys

import numpy as np


def frames(path, w, h, idx):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "bgr24",
                          "-vsync", "passthrough", "-"], stdout=subprocess.PIPE, bufsize=10 ** 8)
    want, out, i = set(idx), {}, 0
    while True:
        buf = p.stdout.read(w * h * 3)
        if len(buf) < w * h * 3 or i > max(want):
            break
        if i in want:
            out[i] = np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.float32)
        i += 1
    p.kill()
    return out


def info(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,width,height,bit_rate,nb_frames",
                        "-of", "compact=p=0:nk=1", path], capture_output=True, text=True).stdout
    return r.strip().splitlines()


src, out = sys.argv[1], sys.argv[2]
print("original:", info(src))
print("finished:", info(out))
w, h = 1280, 720
for line in info(src):
    parts = line.split("|")
    if parts[0] == "video":
        w, h = int(parts[2]), int(parts[3])
n = 6000
idx = list(range(0, n, 20))
a, b = frames(src, w, h, idx), frames(out, w, h, idx)
ps, col = [], []
for i in idx:
    if i in a and i in b:
        mse = float(((a[i] - b[i]) ** 2).mean())
        ps.append(99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse))
        col.append((b[i].mean((0, 1)) - a[i].mean((0, 1))))
ps = np.array(ps)
print(f"frames compared: {len(ps)}")
print(f"PSNR median {np.median(ps):.1f} dB | frames >= 40 dB (practically identical): {np.mean(ps >= 40) * 100:.0f}% "
      f"| 30-40 dB: {np.mean((ps >= 30) & (ps < 40)) * 100:.0f}% | < 30 dB (changed): {np.mean(ps < 30) * 100:.0f}%")
print("mean colour shift B,G,R:", np.round(np.mean(col, 0), 2))
