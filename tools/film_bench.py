"""Developer tool: the whole job on a section of a video, the way a user runs it (one click on
the person to keep), at a chosen background level. Prints the time per step and saves
side-by-side pictures of the result.
python tools/film_bench.py video.mp4 start_s end_s click_frame level [out_name]
  click_frame: a frame (counted in the section) where the person to keep is the biggest person
  level: film | better | sharpest | sharp | balanced | fast | fastest | auto"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import remove_people as rp  # noqa: E402

src, s0, s1, click, level = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
name = sys.argv[6] if len(sys.argv) > 6 else level
OUT = f"/content/kop_film_{name}"
shutil.rmtree(OUT, ignore_errors=True)
preset = "Best" if level in getattr(rp, "SVOR_LEVELS", ("film",)) else "Balanced"  # as the app does
vid, img = rp.load_sam2("/content/repos/sam2", rp.PRESETS[preset]["sam2"])
reid = rp.ReID(emb_weights="yolo11s-cls.pt")
LD = rp.learned_defaults("/nonexistent")
t0 = time.time()
st = rp.create_job(src, OUT + "/jobs", OUT + "/cache", s0, s1, preset, LD["conf"], rp.PART_SECONDS)
st.update(mode="keep", fill="realistic", out_dir=OUT + "/out")
if level != "auto":
    st["fill_level"] = level
b = st["boxes"][click]
k = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
x, y = (b[k, 0] + b[k, 2]) / 2, b[k, 1] + 0.35 * (b[k, 3] - b[k, 1])
rp.set_keeper(st, img, click, x, y)
rp.save_job(st)
t_prep = time.time() - t0
out, chk = rp.remove_others(st, reid, vid, img, "/content/repos/ProPainter", LD["grow"])
total = time.time() - t0
secs = st["n"] / rp.fps_float(st["fps"])
print("\nRESULT", out)
print(f"TOTAL {total / 60:.1f} min for {secs:.0f} s of video ({st['n']} frames), level {st.get('fill_level')}")
print("PREP", json.dumps(st.get("prep")))
print("STEPS", json.dumps({k: round(v) for k, v in st["timings"].items()}))
print("SELFCHECK", json.dumps({p: {k: v for k, v in (r or {}).items() if k != "samples"}
                               for p, r in (st.get("selfcheck") or {}).items()}))
shutil.copy(out, f"/content/film_{name}.mp4")
# pictures: original | result at 6 moments
cap_o, cap_r = cv2.VideoCapture(os.path.join(st["cache"], "master.mp4")), cv2.VideoCapture(out)
rows = []
for f in np.linspace(0, st["n"] - 1, 8)[1:-1].astype(int):
    pair = []
    for cap in (cap_o, cap_r):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, im = cap.read()
        pair.append(cv2.resize(im, (640, 360)) if ok else np.zeros((360, 640, 3), np.uint8))
    cv2.putText(pair[0], f"original {f}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(pair[1], f"{name} {f}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    rows.append(np.hstack(pair))
cv2.imwrite(f"/content/film_{name}.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(f"saved /content/film_{name}.jpg and /content/film_{name}.mp4")
