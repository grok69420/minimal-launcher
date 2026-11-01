"""Developer tool: time only the copy + scan of a video (preset Balanced, first-time settings).
python tools/scan_bench.py video.mp4    (KOP_SCAN_THREADS=1 for the old one-at-a-time scan)"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.environ.get("KOP_ENGINE", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import remove_people as rp  # noqa: E402

out = "/content/kop_scan_bench"
shutil.rmtree(out, ignore_errors=True)
t = time.time()
st = rp.create_job(sys.argv[1], out + "/jobs", out + "/cache", 0, 0, "Balanced",
                   rp.learned_defaults("/nonexistent")["conf"], rp.PART_SECONDS)
print(f"SCAN {time.time() - t:.0f} s, threads {rp.SCAN_THREADS}, people found "
      f"{sum(len(b) for b in st['boxes'])}, prep {st.get('prep')}")
shutil.rmtree(out, ignore_errors=True)
