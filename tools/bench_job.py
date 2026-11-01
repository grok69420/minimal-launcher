"""Developer tool: redo the newest job (same video, same choices) headless with the current
code and print how long every step takes.
python tools/bench_job.py [job folder]"""
import glob
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import remove_people as rp  # noqa: E402

ROOT = "/content/drive/MyDrive/Keep One Person/In progress (automatic)"
OUT = "/content/kop_bench"
old_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
    max(glob.glob(ROOT + "/*/job.pkl"), key=os.path.getmtime))
old = rp.load_job(old_dir, "/content/kop_cache")
src = old["src"] if os.path.exists(old["src"]) else os.path.join(old_dir, "master.mp4")
print("video:", src, old["n"], "frames", old["w"], "x", old["h"], old["preset"], old.get("mode"),
      flush=True)
shutil.rmtree(OUT, ignore_errors=True)
vid, img = rp.load_sam2("/content/repos/sam2", rp.PRESETS[old["preset"]]["sam2"])
reid = rp.ReID(emb_weights="yolo11s-cls.pt")
t0 = time.time()
st = rp.create_job(src, OUT + "/jobs", OUT + "/cache", 0, 0, old["preset"], 0.25, rp.PART_SECONDS)
st.update(mode=old.get("mode", "keep"), fill=old.get("fill", "realistic"), out_dir=OUT + "/out")
for u, s in old["seeds"].items():  # the same clicks, mapped by frame number
    if s is not None:
        st["seeds"][int(st["_unit_of"][s[0]])] = s
for u, lst in old.get("rseeds", {}).items():
    for s in lst:
        st.setdefault("rseeds", {}).setdefault(int(st["_unit_of"][s[0]]), []).append(s)
photos = sorted(glob.glob(os.path.join(old_dir, "photos", "*")))
rp.save_job(st)
out, chk = rp.remove_others(st, reid, vid, img, "/content/repos/ProPainter",
                            old.get("grow", 0.012), photos)
total = time.time() - t0
print("\nRESULT", out)
print(f"TOTAL {total / 60:.1f} min for {st['n'] / rp.fps_float(st['fps']) / 60:.1f} min of video")
print("PREP", json.dumps(st.get("prep")))
print("STEPS", json.dumps({k: round(v) for k, v in st["timings"].items()}))
print("SELFCHECK", json.dumps(st.get("selfcheck")))
