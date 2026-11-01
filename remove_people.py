"""remove_people.py v3 - keep ONE chosen person in any video, erase everyone else.

Short clips and long videos (music videos, presentations, scene compilations):
  1. master copy : the (optionally trimmed) video re-encoded at a constant frame rate,
                   so any frame can be fetched exactly by its number
  2. scan        : one streaming pass finds scene cuts and every person (YOLO11)
  3. parts       : the video is split into parts of ~90 s, at scene cuts when possible
  4. re-ID       : the chosen person is found in every scene (face + clothing, optional
                   reference photos); scenes without them -> everyone removed
  5. per part    : SAM 2 masks (kept person + everyone else), ProPainter background
                   rebuild, composite at full resolution -> part video saved to the job
                   folder (Google Drive), so a disconnect only loses the current part
  6. join        : parts joined losslessly, original audio added
"""
import contextlib
import glob
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import time
import traceback

import cv2
import numpy as np
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cuda":  # faster maths on A100 / L4 at no visible quality cost
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True


def big_gpu():
    """A100 / L4 class GPU (more than 20 GB): keep data on the GPU, use longer windows."""
    return DEVICE == "cuda" and torch.cuda.get_device_properties(0).total_memory > 20e9
SAM2_MODELS = {
    "large": ("sam2.1_hiera_large.pt", "configs/sam2.1/sam2.1_hiera_l.yaml"),
    "base_plus": ("sam2.1_hiera_base_plus.pt", "configs/sam2.1/sam2.1_hiera_b+.yaml"),
    "small": ("sam2.1_hiera_small.pt", "configs/sam2.1/sam2.1_hiera_s.yaml"),
    "tiny": ("sam2.1_hiera_tiny.pt", "configs/sam2.1/sam2.1_hiera_t.yaml"),
}
PRESETS = {
    "Best": dict(sam2="large", det="yolo11x.pt", det_imgsz=1280, pp_max_side=960),
    "Balanced": dict(sam2="base_plus", det="yolo11x.pt", det_imgsz=960, pp_max_side=854),
    "Fast": dict(sam2="small", det="yolo11m.pt", det_imgsz=640, pp_max_side=640),
}
PART_SECONDS = 90.0
JOB_FILE = "job.pkl"

# ---------------------------------------------------------------- logging / progress
_PROGRESS = None


_PREVIEW = None
TIMINGS = {}  # seconds spent per stage (shown to the user; shows which step is slow)


def set_progress(fn):
    """fn(fraction_or_None, text) - used by the web app to show progress."""
    global _PROGRESS
    _PROGRESS = fn


def set_preview(fn):
    """fn(bgr_frame) - receives finished frames now and then (live view in the app)."""
    global _PREVIEW
    _PREVIEW = fn


def log(msg, frac=None):
    print(msg, flush=True)
    if _PROGRESS is not None:
        try:
            _PROGRESS(frac, msg.strip())
        except Exception:
            pass


class Stages:
    def __init__(self, names, outer=None):
        self.names, self.i, self.outer = names, 0, outer

    def _f(self, f):
        if self.outer:
            k, n = self.outer
            return (k + f) / n
        return f

    def _pre(self):
        return f"Part {self.outer[0] + 1}/{self.outer[1]} · " if self.outer else ""

    def start(self, i):
        self.done()
        self._t = time.time()
        self.i = i
        log(f"{self._pre()}{i + 1}/{len(self.names)} {self.names[i]} ...",
            self._f(i / len(self.names)))

    def done(self):
        if getattr(self, "_t", None) is not None:
            k = self.names[self.i]
            TIMINGS[k] = TIMINGS.get(k, 0.0) + time.time() - self._t
            self._t = None

    def step(self, j, total):
        every = max(1, total // 20)
        if j == total or j % every == 0:
            log(f"  {self._pre()}{self.names[self.i]}: {j}/{total}",
                self._f((self.i + j / max(total, 1)) / len(self.names)))


def _autocast():
    # bfloat16 only on Ampere+ GPUs (A100/L4); T4 runs fp32
    if DEVICE == "cuda" and torch.cuda.get_device_capability()[0] >= 8:
        return torch.autocast("cuda", dtype=torch.bfloat16)
    return contextlib.nullcontext()


def _mpath(d, i):
    return os.path.join(d, f"{i:06d}.png")


def _read_mask(d, i):
    return cv2.imread(_mpath(d, i), cv2.IMREAD_GRAYSCALE) > 127


def _write_mask(d, i, m):
    cv2.imwrite(_mpath(d, i), m.astype(np.uint8) * 255, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    _live_view(d, i, m)


_PV = {"t": 0.0, "video": None, "remove": False}


def _live_view(d, i, m):
    """While masks are being made, now and then show the frame with the person kept (green)
    and the people being removed (red) - so the live view is never empty."""
    if _PREVIEW is None or _PV["video"] is None or time.time() - _PV["t"] < 1.5:
        return
    kind = os.path.basename(d)
    if kind not in ("target", "raw", "tracked", "final"):
        return
    _PV["t"] = time.time()
    try:
        img = cv2.imread(_PV["video"].path(i))
        if img is None or img.shape[:2] != m.shape:
            return
        red, green = np.array([0, 0, 235]), np.array([0, 210, 0])
        if kind == "target":
            col = red if _PV["remove"] else green
            img[m] = (0.45 * img[m] + 0.55 * col).astype(np.uint8)
        else:
            img[m] = (0.45 * img[m] + 0.55 * red).astype(np.uint8)
            prot = _mpath(os.path.join(os.path.dirname(d), "protect"), i)
            if not _PV["remove"] and os.path.exists(prot):
                k = cv2.imread(prot, cv2.IMREAD_GRAYSCALE) > 127
                img[k] = (0.45 * img[k] + 0.55 * green).astype(np.uint8)
        _PREVIEW(img)
    except Exception:
        pass


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    return np.array([xs.min(), ys.min(), xs.max() + 1, ys.max() + 1], np.float32)


def _copy_atomic(src, dst):
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


# ---------------------------------------------------------------- video I/O
def fps_float(fps):
    n, _, d = str(fps).partition("/")
    return float(n) / float(d or 1)


def probe(path):
    """(fps string, has_audio, duration seconds, width, height) of the first video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=avg_frame_rate,r_frame_rate,width,height:format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    fps = s.get("avg_frame_rate", "0/0")
    if fps in ("0/0", "", None):
        fps = s["r_frame_rate"]
    aud = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    dur = float(j.get("format", {}).get("duration", 0) or 0)
    return fps, bool(aud), dur, int(s["width"]), int(s["height"])


def _trim_args(start, end):
    a = []
    if start and start > 0:
        a += ["-ss", f"{start:.3f}"]
    if end and end > 0:
        a += ["-to", f"{end:.3f}"]
    return a


def make_master(src, out, fps, start=0.0, end=0.0):
    """Constant-frame-rate master copy (short keyframe interval = fast exact seeking)."""
    tmp = out + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + _trim_args(start, end) +
                   ["-i", src, "-map", "0:v:0", "-vf",
                    f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
                    "-preset", "fast", "-crf", "14", "-g", "30", "-pix_fmt", "yuv420p", "-an",
                    tmp], check=True)
    os.replace(tmp, out)


def extract_audio(src, out, start=0.0, end=0.0):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + _trim_args(start, end) +
                       ["-i", src, "-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "192k", out])
    return out if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0 else None


class Video:
    """Exact frame access to the master copy. video[i] -> path of frame i as JPEG
    (decoded on demand into the cache)."""

    def __init__(self, master, fps, w, h, cache):
        self.master, self.fps, self.w, self.h = master, fps, w, h
        self.dir = os.path.join(cache, "frames")
        os.makedirs(self.dir, exist_ok=True)

    def path(self, i):
        return os.path.join(self.dir, f"{i:06d}.jpg")

    def __getitem__(self, i):
        p = self.path(i)
        if not os.path.exists(p):
            self.extract(i, i + 1)
        return p

    def _seek(self, a):
        return ["-ss", f"{(a - 0.5) / fps_float(self.fps):.6f}"] if a > 0 else []

    def extract(self, a, b):
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + self._seek(a) +
                       ["-i", self.master, "-frames:v", str(b - a), "-vsync", "passthrough",
                        "-q:v", "2", "-start_number", str(a),
                        os.path.join(self.dir, "%06d.jpg")], check=True)
        missing = [i for i in range(a, b) if not os.path.exists(self.path(i))]
        if missing:
            raise RuntimeError(f"Could not decode frames {missing[:3]}... of the master copy.")

    def ensure(self, a, b):
        if any(not os.path.exists(self.path(i)) for i in range(a, b)):
            self.extract(a, b)

    def drop(self, a, b):
        for i in range(a, b):
            try:
                os.remove(self.path(i))
            except FileNotFoundError:
                pass

    def stream(self):
        """All frames in order as BGR arrays (no disk use)."""
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", self.master, "-f", "rawvideo",
                              "-pix_fmt", "bgr24", "-vsync", "passthrough", "-"],
                             stdout=subprocess.PIPE, bufsize=10 ** 8)
        size = self.w * self.h * 3
        try:
            while True:
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                yield np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        finally:
            p.stdout.close()
            p.wait()


class FFWriter:
    """Pipe BGR frames into ffmpeg (H.264), optionally muxing audio from `audio_src`."""

    def __init__(self, path, w, h, fps, audio_src=None, crf=16, duration=None):
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if audio_src:
            cmd += ["-i", audio_src, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:a", "aac", "-b:a", "192k"]
            if duration:  # video length decides; audio is trimmed to it, never the reverse
                cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
                "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", path]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, img):
        self.p.stdin.write(np.ascontiguousarray(img).tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg encoding failed")


# ---------------------------------------------------------------- scan: scenes + people
def scan(video, det_weights, imgsz, conf, n_est, stages=None, batch=None):
    """One streaming pass: colour-change score per frame (for scene cuts) + person boxes."""
    from ultralytics import YOLO
    model = YOLO(det_weights)
    batch = batch or (16 if DEVICE == "cuda" else 4)
    scores, boxes, buf, prev = [], [], [], None

    def flush():
        res = model.predict(buf, classes=[0], conf=conf, imgsz=imgsz, verbose=False,
                            device=0 if DEVICE == "cuda" else "cpu")
        boxes.extend(r.boxes.xyxy.cpu().numpy().astype(np.float32) for r in res)
        buf.clear()

    for i, fr in enumerate(video.stream()):
        sm = cv2.cvtColor(cv2.resize(fr, (128, 72), interpolation=cv2.INTER_AREA),
                          cv2.COLOR_BGR2HSV).astype(np.float32)
        scores.append(0.0 if prev is None else float(np.abs(sm - prev).mean()))
        prev = sm
        buf.append(fr)
        if len(buf) == batch:
            flush()
            if stages:
                stages.step(i + 1, max(n_est, i + 1))
    if buf:
        flush()
    return np.asarray(scores, np.float32), boxes


def shots_from_scores(score, min_len=4, ratio=3.0, min_score=12.0, win=4):
    """Hard cuts: a colour change that is both large and much larger than the local
    median starts a new scene. Returns [(start, end), ...]."""
    n = len(score)
    cuts = [0]
    for i in range(1, n):
        nb = [score[j] for j in range(max(1, i - win), min(n, i + win + 1)) if j != i]
        base = float(np.median(nb)) if nb else 0.0
        if score[i] >= min_score and score[i] >= ratio * (base + 1.0) and i - cuts[-1] >= min_len:
            cuts.append(i)
    return [(a, b) for a, b in zip(cuts, cuts[1:] + [n])]


def plan_parts(shots, n, max_len):
    """Parts of at most max_len frames, cut at scene boundaries when possible
    (a single scene longer than max_len is split)."""
    parts, cur = [], 0
    for a, b in shots:
        if b - cur <= max_len:
            continue
        if a > cur:
            parts.append((cur, a))
            cur = a
        while b - cur > max_len:
            parts.append((cur, cur + max_len))
            cur += max_len
    if cur < n:
        parts.append((cur, n))
    return parts


def make_units(shots, parts):
    """Scene pieces inside parts: [(start, end, scene_index)]."""
    units = []
    for pa, pb in parts:
        for k, (a, b) in enumerate(shots):
            lo, hi = max(a, pa), min(b, pb)
            if lo < hi:
                units.append((lo, hi, k))
    return units


# ---------------------------------------------------------------- SAM 2
def load_sam2(sam2_dir, size="large", ckpt=None):
    if sam2_dir not in sys.path:
        sys.path.insert(0, sam2_dir)
    from sam2.build_sam import build_sam2, build_sam2_video_predictor
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    name, cfg = SAM2_MODELS[size]
    if ckpt is None:
        ckpt = os.path.join(sam2_dir, "checkpoints", name)
    vid = build_sam2_video_predictor(cfg, ckpt, device=DEVICE)
    img = SAM2ImagePredictor(build_sam2(cfg, ckpt, device=DEVICE))
    return vid, img


def segment_boxes(img_pred, img_bgr, boxes):
    """Pixel masks for each box on one frame."""
    if not len(boxes):
        return []
    with torch.inference_mode(), _autocast():
        img_pred.set_image(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        out = []
        for b in boxes:
            m, _, _ = img_pred.predict(box=b, multimask_output=False)
            out.append(m[0] > 0.5)
    return out


def segment_frames(img_pred, imgs_bgr, boxes_list):
    """Masks for the boxes of several frames at once (same result as segment_boxes)."""
    idx = [k for k, b in enumerate(boxes_list) if len(b)]
    out = [[] for _ in boxes_list]
    if not idx:
        return out
    with torch.inference_mode(), _autocast():
        img_pred.set_image_batch([cv2.cvtColor(imgs_bgr[k], cv2.COLOR_BGR2RGB) for k in idx])
        ms, _, _ = img_pred.predict_batch(box_batch=[np.asarray(boxes_list[k], np.float32) for k in idx],
                                          multimask_output=False)
    for k, m in zip(idx, ms):
        m = m[:, None] if m.ndim == 3 and len(boxes_list[k]) > 1 else m
        m = m[None] if m.ndim == 3 else m
        out[k] = [mm[0] > 0.5 for mm in m]
    return out


SEG_BATCH = 8 if DEVICE == "cuda" else 2


def person_at(img_pred, frame_path, boxes, x, y):
    """The person under a click: (box, mask). Prefers a detected person whose mask
    contains the click; otherwise segments from the click point itself."""
    img = cv2.imread(frame_path)
    h, w = img.shape[:2]
    x, y = int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))
    inside = [b for b in boxes if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
    masks = segment_boxes(img_pred, img, inside)
    hits = [(m.sum(), k) for k, m in enumerate(masks) if m[y, x]]
    if hits:
        k = min(hits)[1]
        return np.asarray(inside[k], np.float32), masks[k]
    with torch.inference_mode(), _autocast():
        img_pred.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        ms, sc, _ = img_pred.predict(point_coords=np.array([[x, y]], np.float32),
                                     point_labels=np.array([1]), multimask_output=True)
    ms = [m > 0.5 for m in ms]
    ok = [k for k in np.argsort([-m.sum() for m in ms]) if 0 < ms[k].sum() < 0.6 * h * w]
    if not ok:
        return None, None
    m = ms[ok[0]]
    return _bbox(m), m


def _track_seq(pred, frames, idxs, seeds, tmp, on_frame):
    """Track objects through frames `idxs` (in that order). All seeds ("box"|"mask", array)
    are applied at idxs[0]. Calls on_frame(global_idx, bool masks [K,H,W] in seed order)."""
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for j, g in enumerate(idxs):
        os.symlink(os.path.abspath(frames[g]), os.path.join(tmp, f"{j:05d}.jpg"))
    with torch.inference_mode(), _autocast():
        off = not big_gpu()
        st = pred.init_state(tmp, offload_video_to_cpu=off, offload_state_to_cpu=off)
        for k, (kind, arr) in enumerate(seeds):
            if kind == "box":
                pred.add_new_points_or_box(st, frame_idx=0, obj_id=k + 1, box=arr)
            else:
                pred.add_new_mask(st, frame_idx=0, obj_id=k + 1, mask=arr)
        for fi, obj_ids, logits in pred.propagate_in_video(st):
            m = (logits[:, 0] > 0).cpu().numpy()
            order = np.argsort(np.asarray(obj_ids))
            on_frame(idxs[fi], m[order])
        pred.reset_state(st)
    del st
    if DEVICE == "cuda":
        torch.cuda.empty_cache()


def track_target(pred, frames, seed_idx, box, out_dir, tmp, lo, hi, chunk=200, min_px=64):
    """Track the kept person through frames [lo, hi), forward and backward from the seed
    frame. Chunks are re-seeded with the last frame where the person was visible, so
    tracking survives chunk borders and short exits from the frame."""
    os.makedirs(out_dir, exist_ok=True)
    box = np.asarray(box, dtype=np.float32)
    for forward in (True, False):
        seq = list(range(seed_idx, hi)) if forward else list(range(seed_idx, lo - 1, -1))
        seed = {"g": seed_idx, "s": ("box", box)}
        if forward and len(seq) == 1:
            _track_seq(pred, frames, [seed_idx], [seed["s"]], tmp,
                       lambda g, m: _write_mask(out_dir, g, m[0]))
            continue
        pos = 1
        while pos < len(seq):
            idxs = [seed["g"]] + seq[pos:pos + chunk - 1]
            first = forward and pos == 1

            def on_frame(g, m, idxs=idxs, first=first):
                if g == idxs[0] and not first:
                    return  # seed frame already written by the previous chunk
                _write_mask(out_dir, g, m[0])
                if g != idxs[0] and m[0].sum() >= min_px:
                    seed["g"], seed["s"] = g, ("mask", m[0])

            _track_seq(pred, frames, idxs, [seed["s"]], tmp, on_frame)
            pos += chunk - 1
    shutil.rmtree(tmp, ignore_errors=True)


def mask_others(img_pred, frames, boxes, tgt_dir, raw_dir, prot_dir, inst_dir, lo, hi,
                keep_thr=0.3, stages=None):
    """Per frame in [lo, hi): segment every detected person; the single detection that
    best matches the tracked person is skipped, all others go into the removal mask
    (and into an instance-label image used to seed tracking)."""
    for d in (raw_dir, prot_dir, inst_dir):
        os.makedirs(d, exist_ok=True)
    seg = {}
    for i in range(lo, hi):
        if i not in seg:
            ks = list(range(i, min(hi, i + SEG_BATCH)))
            got = segment_frames(img_pred, [cv2.imread(frames[k]) for k in ks], [boxes[k] for k in ks])
            seg = dict(zip(ks, got))
        tgt = _read_mask(tgt_dir, i)
        other = np.zeros_like(tgt)
        prot = tgt.copy()
        inst = []
        if len(boxes[i]):
            masks = seg[i]
            scores = [(m & tgt).sum() / max(m.sum(), 1) for m in masks]
            keep = int(np.argmax(scores)) if tgt.any() and max(scores) >= keep_thr else -1
            for k, m in enumerate(masks):
                # keeper's own detection: not erased, but not used for protection either
                # (its box can include a person standing behind them)
                if k != keep and scores[k] <= 0.5:  # >50% inside kept person = duplicate box
                    other |= m
                    inst.append(m)
        other &= ~prot
        lab = np.zeros(tgt.shape, np.uint8)
        for k, m in enumerate(sorted(inst, key=lambda x: -x.sum())[:254]):
            lab[m & ~prot] = k + 1
        cv2.imwrite(_mpath(inst_dir, i), lab)
        _write_mask(raw_dir, i, other)
        _write_mask(prot_dir, i, prot)
        if stages:
            stages.step(i - lo + 1, hi - lo)


def track_others(pred, frames, inst_dir, prot_dir, out_dir, tmp, ranges, chunk=60,
                 min_px=64, max_age=3, max_objs=30, stages=None):
    """Track every other person with SAM 2 (forward and backward, inside each scene
    piece), so people stay masked while hidden behind the kept person or missed by the
    detector. Each chunk is re-seeded from fresh detections plus still-visible tracks;
    undetected tracks expire after `max_age` chunks."""
    os.makedirs(out_dir, exist_ok=True)
    for si, (lo, hi) in enumerate(ranges):
        for forward in (True, False):
            seq = list(range(lo, hi)) if forward else list(range(hi - 1, lo - 1, -1))
            carried, pos = [], 0
            while pos < len(seq) - 1:
                s = seq[pos]
                idxs = [s] + seq[pos + 1:pos + chunk]
                lab = cv2.imread(_mpath(inst_dir, s), cv2.IMREAD_GRAYSCALE)
                prot = _read_mask(prot_dir, s)
                dets = [lab == k for k in np.unique(lab) if k]
                dets = [d for d in dets if d.sum() >= min_px]
                seeds = [(d, 0) for d in dets]
                for m, age in carried:
                    m = m & ~prot
                    if m.sum() < min_px or age + 1 > max_age:
                        continue
                    if any((m & d).sum() > 0.3 * min(m.sum(), d.sum()) for d in dets):
                        continue  # same person as a fresh detection
                    seeds.append((m, age + 1))
                seeds = sorted(seeds, key=lambda x: -x[0].sum())[:max_objs]
                pos += chunk - 1
                if not seeds:
                    carried = []
                    continue
                last = {}

                def on_frame(g, m, s=s, last_g=idxs[-1]):
                    if g != s:
                        u = m.any(axis=0)
                        if os.path.exists(_mpath(out_dir, g)):
                            u |= _read_mask(out_dir, g)
                        _write_mask(out_dir, g, u)
                    if g == last_g:
                        last["m"] = m

                _track_seq(pred, frames, idxs, [("mask", m) for m, _ in seeds], tmp, on_frame)
                carried = [(last["m"][k], seeds[k][1]) for k in range(len(seeds))]
        if stages:
            stages.step(si + 1, len(ranges))
    shutil.rmtree(tmp, ignore_errors=True)


def finalize_masks(raw_dir, trk_dir, prot_dir, final_dir, ranges, pad_t=2, grow_px=15):
    """Union of detections + tracks, temporal carry-over inside the scene piece (covers
    flicker) and dilation (hair, motion blur). The kept person's pixels are never
    included. Returns {frame: needs_removal}."""
    os.makedirs(final_dir, exist_ok=True)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1))
    flags = {}
    for lo, hi in ranges:
        cache = {}
        for i in range(lo, hi):
            win = range(max(lo, i - pad_t), min(hi, i + pad_t + 1))
            for j in win:
                if j not in cache:
                    cache[j] = _read_mask(raw_dir, j)
                    if os.path.exists(_mpath(trk_dir, j)):
                        cache[j] |= _read_mask(trk_dir, j)
            for j in [j for j in cache if j < i - pad_t]:
                del cache[j]
            u = np.zeros_like(cache[i])
            for j in win:
                u |= cache[j]
            if u.any() and grow_px > 0:
                u = cv2.dilate(u.astype(np.uint8), k) > 0
            u &= ~_read_mask(prot_dir, i)
            _write_mask(final_dir, i, u)
            flags[i] = bool(u.any())
    return flags


def preview_size(w, h, max_side=720):
    s = min(1.0, max_side / max(h, w))
    return int(w * s) // 2 * 2, int(h * s) // 2 * 2


def make_preview(frames, final_dir, prot_dir, out_mp4, fps, lo, hi, label, w, h):
    """Red = will be erased, green = kept person. Check this before trusting the result."""
    pw, ph = preview_size(w, h)
    wr = FFWriter(out_mp4, pw, ph, fps, crf=23)
    for i in range(lo, hi):
        img = cv2.resize(cv2.imread(frames[i]), (pw, ph), interpolation=cv2.INTER_AREA)
        rm = cv2.resize(_read_mask(final_dir, i).astype(np.uint8), (pw, ph)) > 0
        kp = cv2.resize(_read_mask(prot_dir, i).astype(np.uint8), (pw, ph)) > 0
        img[rm] = (0.45 * img[rm] + 0.55 * np.array([0, 0, 255])).astype(np.uint8)
        img[kp] = (0.65 * img[kp] + 0.35 * np.array([0, 255, 0])).astype(np.uint8)
        cv2.putText(img, label(i), (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
                    cv2.LINE_AA)
        wr.write(img)
    wr.close()


# ---------------------------------------------------------------- re-identification
class ReID:
    """Finds the kept person in other scenes. Face similarity (InsightFace ArcFace)
    decides when a face is visible; otherwise clothing appearance (colour layout +
    CNN embedding of the segmented body) is used."""

    FACE_MATCH = 0.40   # same person if face cosine similarity >= this
    FACE_REJECT = 0.20  # clearly a different person if below this
    BODY_MATCH = 0.90   # appearance similarity needed when no face decides
    BODY_MARGIN = 0.05  # ...and this much better than anyone else in that frame
    MIN_FACE_PX = 28

    def __init__(self, emb_weights="yolo11s-cls.pt", use_face=True):
        from ultralytics import YOLO
        self.emb = YOLO(emb_weights)
        self.face = None
        if use_face:
            try:
                from insightface.app import FaceAnalysis
                fa = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"],
                                  providers=["CPUExecutionProvider"])
                fa.prepare(ctx_id=-1, det_size=(640, 640))
                self.face = fa
            except Exception as e:  # never block the pipeline on the optional face model
                log(f"  face recognition unavailable ({e}); using appearance only")
        self.reset()

    def reset(self):
        self.ref_faces, self.ref_bodies = [], []

    def _faces(self, img):
        if self.face is None:
            return []
        out = []
        for f in self.face.get(img):
            x1, y1, x2, y2 = f.bbox
            if f.det_score >= 0.5 and min(x2 - x1, y2 - y1) >= self.MIN_FACE_PX:
                out.append(f)
        return out

    def _body(self, img, box, mask):
        h, w = img.shape[:2]
        x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
        x2, y2 = min(w, int(np.ceil(box[2]))), min(h, int(np.ceil(box[3])))
        crop, m = img[y1:y2, x1:x2], mask[y1:y2, x1:x2].astype(np.uint8)
        if crop.size == 0:
            return None
        if m.sum() < 50:
            m = np.ones_like(m)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hh = crop.shape[0]
        parts = []
        for a, b in ((0.0, 0.33), (0.33, 0.66), (0.66, 1.0)):
            r0, r1 = int(a * hh), max(int(a * hh) + 1, int(b * hh))
            hist = cv2.calcHist([hsv[r0:r1]], [0, 1], m[r0:r1], [12, 6], [0, 180, 0, 256]).ravel()
            vh = cv2.calcHist([hsv[r0:r1]], [2], m[r0:r1], [6], [0, 256]).ravel()
            v = np.concatenate([hist, vh])
            parts.append(np.sqrt(v / max(v.sum(), 1e-6)))
        col = np.concatenate(parts)
        col /= np.linalg.norm(col) + 1e-6
        masked = crop.copy()
        masked[m == 0] = 114
        e = self.emb.embed([masked], imgsz=224, verbose=False)[0].float().cpu().numpy()
        e /= np.linalg.norm(e) + 1e-6
        return col, e

    def describe(self, img, boxes, masks):
        """[{'face': emb|None, 'body': (col, cnn)|None}] for each person."""
        faces = self._faces(img)
        owner = {}
        for f in faces:
            cx, cy = (f.bbox[0] + f.bbox[2]) / 2, (f.bbox[1] + f.bbox[3]) / 2
            cands = []
            for k, (b, m) in enumerate(zip(boxes, masks)):
                if b[0] <= cx <= b[2] and b[1] <= cy <= b[1] + 0.6 * (b[3] - b[1]):
                    yy = int(np.clip(cy, 0, m.shape[0] - 1))
                    xx = int(np.clip(cx, 0, m.shape[1] - 1))
                    cands.append((0 if m[yy, xx] else 1, (b[2] - b[0]) * (b[3] - b[1]), k))
            if cands:
                k = min(cands)[2]
                area = (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
                if k not in owner or area > owner[k][0]:
                    owner[k] = (area, f.normed_embedding)
        return [{"face": owner[k][1] if k in owner else None,
                 "body": self._body(img, b, m)} for k, (b, m) in enumerate(zip(boxes, masks))]

    def add_person(self, img, box, mask):
        d = self.describe(img, [box], [mask])[0]
        if d["face"] is not None:
            self.ref_faces.append(d["face"])
        if d["body"] is not None:
            self.ref_bodies.append(d["body"])
        return d

    def add_photo(self, path):
        img = cv2.imread(path)
        if img is None:
            return False
        faces = self._faces(img)
        if not faces:
            return False
        f = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        self.ref_faces.append(f.normed_embedding)
        return True

    def face_sim(self, d):
        if d["face"] is None or not self.ref_faces:
            return None
        return float(max(np.dot(r, d["face"]) for r in self.ref_faces))

    def body_sim(self, d):
        if d["body"] is None or not self.ref_bodies:
            return 0.0
        sims = sorted((0.5 * float(np.dot(c, d["body"][0])) + 0.5 * float(np.dot(e, d["body"][1]))
                       for c, e in self.ref_bodies), reverse=True)
        return float(np.mean(sims[:3]))

    def find_in_shot(self, img_pred, frames, boxes, lo, hi, n_samples=8):
        """Best {frame, box, how, score} for the kept person in frames [lo, hi), or None."""
        inner = list(range(lo + 1, hi - 1)) if hi - lo > 4 else list(range(lo, hi))
        idxs = sorted(set(inner[int(round(t))] for t in
                          np.linspace(0, len(inner) - 1, min(n_samples, len(inner)))))
        cands = []
        for i in idxs:
            if not len(boxes[i]):
                continue
            img = cv2.imread(frames[i])
            masks = segment_boxes(img_pred, img, boxes[i])
            for k, d in enumerate(self.describe(img, boxes[i], masks)):
                cands.append(dict(frame=i, k=k, box=boxes[i][k], face=self.face_sim(d),
                                  body=self.body_sim(d)))
        if not cands:
            return None
        faced = [c for c in cands if c["face"] is not None and c["face"] >= self.FACE_MATCH]
        if faced:
            c = max(faced, key=lambda c: c["face"])
            return dict(frame=c["frame"], box=c["box"], how="face", score=c["face"])
        ok = [c for c in cands if c["face"] is None or c["face"] >= self.FACE_REJECT]
        if not ok:
            return None
        c = max(ok, key=lambda c: c["body"])
        rivals = [o["body"] for o in cands if o["frame"] == c["frame"] and o["k"] != c["k"]]
        if c["body"] >= self.BODY_MATCH and (not rivals or c["body"] - max(rivals) >= self.BODY_MARGIN):
            return dict(frame=c["frame"], box=c["box"], how="appearance", score=c["body"])
        return None


# ---------------------------------------------------------------- realistic fill (MiniMax-Remover)
MM_CODE = os.environ.get("KOP_MM_CODE", "/content/repos/MiniMax-Remover")
MM_WEIGHTS = os.environ.get("KOP_MM_WEIGHTS", "/content/repos/minimax_weights")


def fill_size(w, h, area=832 * 480):
    """Working size for the generative fill (the model was trained at 832x480)."""
    a, ref = w / h, 832 / 480
    if abs(a - ref) / ref < 0.06:
        return 832, 480
    if abs(a - 1 / ref) * ref < 0.06:
        return 480, 832
    return (max(16, int(round((area * a) ** 0.5 / 16)) * 16),
            max(16, int(round((area / a) ** 0.5 / 16)) * 16))


class MiniMaxFiller:
    """Generates realistic background where people were removed (diffusion model)."""

    def __init__(self, code_dir=MM_CODE, weights=MM_WEIGHTS, steps=8):
        if code_dir not in sys.path:
            sys.path.insert(0, code_dir)
        from diffusers.models import AutoencoderKLWan
        from diffusers.schedulers import UniPCMultistepScheduler
        from transformer_minimax_remover import Transformer3DModel
        from pipeline_minimax_remover import Minimax_Remover_Pipeline
        vae = AutoencoderKLWan.from_pretrained(os.path.join(weights, "vae"), torch_dtype=torch.float16)
        tr = Transformer3DModel.from_pretrained(os.path.join(weights, "transformer"),
                                                torch_dtype=torch.float16)
        sch = UniPCMultistepScheduler.from_pretrained(os.path.join(weights, "scheduler"))
        self.pipe = Minimax_Remover_Pipeline(transformer=tr, vae=vae, scheduler=sch).to("cuda")
        self.steps = steps

    def fill(self, imgs, masks, fw, fh, dil=2, seed=42, steps=None):
        """imgs: BGR frames, masks: bool arrays; len must be 4k+1. Returns BGR frames (fw x fh)."""
        x = np.stack([cv2.cvtColor(cv2.resize(im, (fw, fh), interpolation=cv2.INTER_AREA),
                                   cv2.COLOR_BGR2RGB) for im in imgs])
        m = np.stack([cv2.resize(k.astype(np.uint8), (fw, fh), interpolation=cv2.INTER_NEAREST)
                      for k in masks])[..., None]
        out = self.pipe(images=torch.from_numpy(x).float() / 127.5 - 1.0,
                        masks=torch.from_numpy(m).float(), num_frames=len(imgs), height=fh,
                        width=fw, num_inference_steps=steps or self.steps,
                        generator=torch.Generator(device="cuda").manual_seed(seed),
                        iterations=dil).frames[0]
        return [cv2.cvtColor(np.clip(o * 255 + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
                for o in out]

    def close(self):
        del self.pipe
        if DEVICE == "cuda":
            torch.cuda.empty_cache()


def _pad_4k1(seq):
    """Mirror-pad a frame list to a length of the form 4k+1 (needed by the video model)."""
    need = ((len(seq) - 1 + 3) // 4) * 4 + 1
    ext = list(seq)
    while len(ext) < need:
        ext += seq[::-1][1:] or seq
        ext += seq[1:] or seq
    return ext[:need]


def crop_box(masks, w, h, margin=0.6, min_short=200, full_at=0.8):
    """Area to give the fill model: the removed region plus context, in the model's aspect
    ratio. Small regions are filled zoomed-in (sharper); large ones use the whole frame."""
    u = np.zeros((h, w), bool)
    for m in masks:
        u |= m
    if not u.any():
        return 0, 0, w, h
    x1, y1, x2, y2 = _bbox(u)
    bw, bh = x2 - x1, y2 - y1
    ar = (832 / 480) if w >= h else (480 / 832)
    cw, ch = bw * (1 + 2 * margin), bh * (1 + 2 * margin)
    if cw / ch < ar:
        cw = ch * ar
    else:
        ch = cw / ar
    s = max(1.0, min_short / min(cw, ch))
    cw, ch = cw * s, ch * s
    if cw >= full_at * w or ch >= full_at * h:
        return 0, 0, w, h
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    X1 = int(np.clip(cx - cw / 2, 0, w - cw))
    Y1 = int(np.clip(cy - ch / 2, 0, h - ch))
    return X1, Y1, X1 + int(cw), Y1 + int(ch)


def fill_realistic(frames, final_dir, flags, work, ranges, w, h, filler, window=49, overlap=8,
                   stages=None, seed=42, reuse=None, changed=None, steps=None):
    """Same output format as inpaint(): (chunks, {chunk: (folder, extension)}); the folder
    holds full-size frames with the removed areas filled in."""
    chs = plan_chunks(ranges, window, overlap)
    todo = [c for c, (a, b, _, _) in enumerate(chs) if any(flags[i] for i in range(a, b))]
    results = {}
    if reuse and reuse[0] == chs and changed is not None:  # only repaint what changed
        keep = [c for c in todo if c in reuse[1] and not any(i in changed for i in range(*chs[c][:2]))]
        results.update({c: reuse[1][c] for c in keep})
        todo = [c for c in todo if c not in keep]
    for t, c in enumerate(todo):
        a, b, _, _ = chs[c]
        seq = list(range(a, b))
        ext = _pad_4k1(seq)
        imgs = [cv2.imread(frames[g]) for g in ext]
        masks = [_read_mask(final_dir, g) for g in ext]
        x1, y1, x2, y2 = crop_box(masks, w, h)
        fw, fh = fill_size(x2 - x1, y2 - y1)
        out = filler.fill([im[y1:y2, x1:x2] for im in imgs], [m[y1:y2, x1:x2] for m in masks],
                          fw, fh, seed=seed, steps=steps)
        d = os.path.join(work, "mm_out", f"c{c:04d}_s{seed}")
        os.makedirs(d, exist_ok=True)
        for j in range(len(seq)):
            full = imgs[j].copy()
            full[y1:y2, x1:x2] = cv2.resize(out[j], (x2 - x1, y2 - y1),
                                            interpolation=cv2.INTER_LANCZOS4)
            cv2.imwrite(os.path.join(d, f"{j:04d}.jpg"), full, [cv2.IMWRITE_JPEG_QUALITY, 95])
        results[c] = (d, ".jpg")
        if stages:
            stages.step(t + 1, len(todo))
    return chs, results


def is_static(frames, final_dir, prot_dir, lo, hi, samples=12, max_shift=1.0, max_diff=7.0):
    """True when the camera does not move in frames [lo, hi) (tripod, presentation, interview)."""
    if hi - lo < 8:
        return False
    idx = sorted(set(np.linspace(lo, hi - 1, min(samples, hi - lo)).round().astype(int).tolist()))
    prev = None
    shifts, diffs = [], []
    for i in idx:
        img = cv2.imread(frames[i])
        sw = 320
        sh = max(8, int(round(img.shape[0] * sw / img.shape[1])))
        g = cv2.cvtColor(cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2GRAY).astype(np.float32)
        busy = cv2.resize((_read_mask(final_dir, i) | _read_mask(prot_dir, i)).astype(np.uint8),
                          (sw, sh), interpolation=cv2.INTER_NEAREST)
        busy = cv2.dilate(busy, np.ones((7, 7), np.uint8)) > 0
        if prev is not None:
            (dx, dy), _ = cv2.phaseCorrelate(prev[0], g)
            shifts.append(float(np.hypot(dx, dy)))
            free = ~(busy | prev[1])
            if free.sum() > 100:
                diffs.append(float(np.abs(g - prev[0])[free].mean()))
        prev = (g, busy)
    return bool(shifts) and max(shifts) <= max_shift and (not diffs or np.median(diffs) <= max_diff)


def fill_holes(img, holes, filler=None, steps=None, seed=42):
    """Fill pixels that were never visible (a person who never moved): AI fill if available,
    otherwise classic inpainting."""
    if not holes.any():
        return img
    h, w = holes.shape
    holes = cv2.dilate(holes.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    if filler is not None:
        try:
            x1, y1, x2, y2 = crop_box([holes], w, h)
            fw, fh = fill_size(x2 - x1, y2 - y1)
            out = filler.fill([img[y1:y2, x1:x2]], [holes[y1:y2, x1:x2]], fw, fh, steps=steps,
                              seed=seed)[0]
            res = img.copy()
            patch = cv2.resize(out, (x2 - x1, y2 - y1), interpolation=cv2.INTER_LANCZOS4)
            hm = holes[y1:y2, x1:x2]
            res[y1:y2, x1:x2][hm] = patch[hm]
            return res
        except Exception:
            traceback.print_exc()
    return smooth_fill(img, holes)


def smooth_fill(img, holes):
    """Fallback fill without AI: smooth colours pulled in from all around the hole
    (push-pull pyramid). Looks natural on walls and skies; never streaky."""
    known = (~holes).astype(np.float32)
    if not known.any():
        return img
    pyr = [(img.astype(np.float32) * known[..., None], known)]
    while min(pyr[-1][1].shape) > 8:
        i_, w_ = pyr[-1]
        pyr.append((cv2.pyrDown(i_), cv2.pyrDown(w_)))
    i_, w_ = pyr[-1]
    est = i_ / np.maximum(w_, 1e-6)[..., None]
    if (w_ < 1e-6).any():
        est[w_ < 1e-6] = img[~holes].mean(0)
    for i_, w_ in reversed(pyr[:-1]):
        up = cv2.resize(est, (w_.shape[1], w_.shape[0]), interpolation=cv2.INTER_LINEAR)
        a = np.clip(w_ * 2, 0, 1)[..., None]  # trust pixels that are (mostly) known
        est = i_ / np.maximum(w_, 1e-6)[..., None] * a + up * (1 - a)
    out = img.copy()
    out[holes] = np.clip(est[holes] + 0.5, 0, 255).astype(np.uint8)
    return out


def plate_fill(frames, final_dir, prot_dir, flags, ranges, w, h, filler=None, window=120,
               samples=40, steps=None, seed=42, stages=None, overlap=8):
    """Steady camera: build a clean picture of the empty background from the moments when each
    pixel was not covered by anyone, and reuse it in every frame (sharp, no flicker, fast)."""
    chs = plan_chunks(ranges, window, overlap)  # overlapping windows cross-fade, no jumps
    results = {}
    by_range = {}
    for c, (a, b, sa, sb) in enumerate(chs):
        by_range.setdefault((sa, sb), []).append(c)
    done = 0
    for (sa, sb), cs in by_range.items():
        if not any(flags[i] for i in range(sa, sb)):
            continue
        acc_u = np.zeros((h, w, 3), np.float64)
        cnt_u = np.zeros((h, w), np.float64)
        per = {}
        for c in cs:
            a, b = chs[c][:2]
            lo2, hi2 = max(sa, a - window // 2), min(sb, b + window // 2)
            idx = sorted(set(np.linspace(lo2, hi2 - 1, min(samples, hi2 - lo2)).round().astype(int).tolist()))
            acc = np.zeros((h, w, 3), np.float64)
            cnt = np.zeros((h, w), np.float64)
            for i in idx:
                busy = cv2.dilate((_read_mask(final_dir, i) | _read_mask(prot_dir, i)).astype(np.uint8),
                                  np.ones((7, 7), np.uint8)) > 0
                free = ~busy
                acc[free] += cv2.imread(frames[i])[free]
                cnt[free] += 1
            per[c] = (acc, cnt)
            acc_u += acc
            cnt_u += cnt
        unit_plate = (acc_u / np.maximum(cnt_u, 1)[..., None]).astype(np.uint8)
        unit_plate = fill_holes(unit_plate, cnt_u == 0, filler, steps, seed)
        for c in cs:
            acc, cnt = per[c]
            pl = (acc / np.maximum(cnt, 1)[..., None]).astype(np.uint8)
            hole = cnt == 0
            pl[hole] = unit_plate[hole]
            results[c] = ("plate", pl)
            done += 1
            if stages:
                stages.step(done, len(chs))
    return chs, results


def _merge_fills(parts):
    """Combine (chunks, results) from several fill methods into one."""
    chs, res = [], {}
    for c_list, r in parts:
        off = len(chs)
        chs += c_list
        res.update({k + off: v for k, v in r.items()})
    return chs, res


def _sam2_to(vid_pred, img_pred, device):
    vid_pred.to(device)
    img_pred.model.to(device)
    if DEVICE == "cuda":
        torch.cuda.empty_cache()


# ---------------------------------------------------------------- ProPainter
def _chunks(n, size, overlap):
    out, s = [], 0
    while True:
        e = min(s + size, n)
        out.append((s, e))
        if e >= n:
            return out
        s = e - overlap


def plan_chunks(ranges, size, overlap):
    return [(sa + a, sa + b, sa, sb) for sa, sb in ranges for a, b in _chunks(sb - sa, size, overlap)]


MIN_PP_FRAMES = 12


def inpaint(frames, final_dir, flags, work, pp_dir, ranges, w, h, max_side=960, chunk=120,
            overlap=16, fp16=True, stages=None):
    """ProPainter, one scene piece at a time. Very short pieces are padded by mirroring."""
    s = min(1.0, max_side / max(h, w))
    pw, ph = max(8, int(w * s) // 8 * 8), max(8, int(h * s) // 8 * 8)
    results = {}
    chs = plan_chunks(ranges, chunk, overlap)
    todo = [c for c, (a, b, _, _) in enumerate(chs) if any(flags[i] for i in range(a, b))]
    for t, c in enumerate(todo):
        a, b, _, _ = chs[c]
        seq = list(range(a, b))
        ext = list(seq)
        while len(ext) < MIN_PP_FRAMES:
            ext += seq[::-1][1:] or seq
            ext += seq[1:] or seq
        ext = ext[:max(len(seq), MIN_PP_FRAMES)]
        name = f"c{c:04d}"
        fin = os.path.join(work, "pp_in", name)
        min_ = fin + "_mask"
        out_root = os.path.join(work, "pp_out")
        for d in (fin, min_):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
        for j, g in enumerate(ext):
            img = cv2.resize(cv2.imread(frames[g]), (pw, ph), interpolation=cv2.INTER_AREA)
            cv2.imwrite(os.path.join(fin, f"{j:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 97])
            m = cv2.resize(_read_mask(final_dir, g).astype(np.uint8), (pw, ph),
                           interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(os.path.join(min_, f"{j:05d}.png"), m * 255)
        ok = False
        # OOM fallbacks; never below 320 px on the long side (ProPainter's minimum in practice)
        ratios = [r for r in (1.0, 0.75, 0.5) if r == 1.0 or r * max(pw, ph) >= 320]
        for ratio in ratios:
            cmd = [sys.executable, "inference_propainter.py", "-i", os.path.abspath(fin),
                   "-m", os.path.abspath(min_), "-o", os.path.abspath(out_root),
                   "--save_frames", "--subvideo_length", "80"]
            if fp16 and DEVICE == "cuda":
                cmd.append("--fp16")
            if ratio != 1.0:
                cmd += ["--resize_ratio", str(ratio)]
            r = subprocess.run(cmd, cwd=pp_dir, capture_output=True, text=True)
            if r.returncode == 0:
                ok = True
                break
            tail = (r.stdout + r.stderr)[-1500:]
            killed = r.returncode < 0  # e.g. SIGKILL from the system RAM limit
            if not killed and "out of memory" not in tail.lower():
                raise RuntimeError("ProPainter failed:\n" + tail)
            log("  out of memory; retrying this piece at lower resolution")
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
        if not ok:
            raise RuntimeError("ProPainter ran out of memory at every fallback size. "
                               "Choose the Fast quality setting.")
        results[c] = (os.path.join(out_root, name, "frames"), ".png")
        shutil.rmtree(fin)
        shutil.rmtree(min_)
        if stages:
            stages.step(t + 1, len(todo))
    return chs, results


def _inpainted_frame(g, chs, results, overlap, size):
    acc, wsum = None, 0.0
    for c, (a, b, sa, sb) in enumerate(chs):
        if not (a <= g < b) or c not in results:
            continue
        wgt = 1.0
        if a > sa:
            wgt *= min(1.0, (g - a + 1) / (overlap + 1))
        if b < sb:
            wgt *= min(1.0, (b - g) / (overlap + 1))
        folder, ext = results[c]
        if isinstance(folder, str) and folder == "plate":  # steady camera: clean background
            img = ext.astype(np.float32)
        else:
            img = cv2.imread(os.path.join(folder, f"{g - a:04d}{ext}")).astype(np.float32)
            img = cv2.resize(img, size, interpolation=cv2.INTER_LANCZOS4)
        acc = img * wgt if acc is None else acc + img * wgt
        wsum += wgt
    return acc / wsum


def composite(frames, final_dir, prot_dir, flags, chs, results, out_mp4, fps, lo, hi, w, h,
              overlap=16, feather_px=6, stages=None):
    wr = FFWriter(out_mp4, w, h, fps)
    for g in range(lo, hi):
        orig = cv2.imread(frames[g])
        if not flags.get(g):
            wr.write(orig)
        else:  # blend only around the removed area (fast), matching the frame's brightness
            inp = _inpainted_frame(g, chs, results, overlap, (w, h))
            mb = _read_mask(final_dir, g)
            x1, y1, x2, y2 = (int(v) for v in _bbox(mb))
            pd = 4 * feather_px + 2
            x1, y1, x2, y2 = max(0, x1 - pd), max(0, y1 - pd), min(w, x2 + pd), min(h, y2 + pd)
            mm = mb[y1:y2, x1:x2]
            m = mm.astype(np.float32)
            a = np.maximum(cv2.GaussianBlur(m, (0, 0), feather_px), m) if feather_px > 0 else m
            pr = _read_mask(prot_dir, g)[y1:y2, x1:x2]
            a[pr] = 0.0
            o = orig[y1:y2, x1:x2].astype(np.float32)
            f = inp[y1:y2, x1:x2]
            ring = (cv2.dilate(mm.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & ~mm & ~pr
            if ring.sum() > 50:
                f = f * np.clip((o[ring].mean(0) + 1) / (f[ring].mean(0) + 1), 0.85, 1.18)
            orig = orig.copy()
            orig[y1:y2, x1:x2] = np.clip(o * (1 - a[..., None]) + f * a[..., None] + 0.5, 0,
                                         255).astype(np.uint8)
            wr.write(orig)
        if _PREVIEW is not None and (g - lo) % 12 == 0:
            try:
                _PREVIEW(orig)
            except Exception:
                pass
        if stages:
            stages.step(g - lo + 1, hi - lo)
    wr.close()


# ---------------------------------------------------------------- jobs (saved, resumable)
def _safe_name(src):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(src))[0])[:40]
    return f"{base or 'video'}_{time.strftime('%Y%m%d_%H%M%S')}"


def save_job(st):
    data = {k: v for k, v in st.items() if not k.startswith("_")}
    p = os.path.join(st["job_dir"], JOB_FILE)
    with open(p + ".tmp", "wb") as f:
        pickle.dump(data, f)
    os.replace(p + ".tmp", p)


def _attach(st, cache_root):
    st["cache"] = os.path.join(cache_root, st["name"])
    os.makedirs(st["cache"], exist_ok=True)
    master = os.path.join(st["cache"], "master.mp4")
    if not os.path.exists(master):
        log("Copying the saved master video back from the job folder ...")
        _copy_atomic(os.path.join(st["job_dir"], "master.mp4"), master)
    if st.get("audio") and not os.path.exists(os.path.join(st["cache"], "audio.m4a")):
        _copy_atomic(os.path.join(st["job_dir"], "audio.m4a"), os.path.join(st["cache"], "audio.m4a"))
    st["_video"] = Video(master, st["fps"], st["w"], st["h"], st["cache"])
    st["_unit_of"] = np.zeros(st["n"], np.int32)
    for u, (a, b, _) in enumerate(st["units"]):
        st["_unit_of"][a:b] = u
    st["_tracked"] = {}
    return st


def create_job(src, jobs_root, cache_root, start=0.0, end=0.0, preset="Best", conf=0.25,
               part_seconds=PART_SECONDS):
    """Step 1: master copy, scene cuts, people, part plan. Saved to the job folder."""
    cfg = PRESETS[preset]
    name = _safe_name(src)
    job_dir = os.path.join(jobs_root, name)
    cache = os.path.join(cache_root, name)
    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    S = Stages(["Preparing video", "Saving to job folder", "Finding scenes and people"])
    S.start(0)
    fps, has_audio, _, _, _ = probe(src)
    master = os.path.join(cache, "master.mp4")
    make_master(src, master, fps, start, end)
    audio = extract_audio(src, os.path.join(cache, "audio.m4a"), start, end) if has_audio else None
    _, _, dur, w, h = probe(master)
    S.start(1)
    _copy_atomic(master, os.path.join(job_dir, "master.mp4"))
    if audio:
        _copy_atomic(audio, os.path.join(job_dir, "audio.m4a"))
    S.start(2)
    video = Video(master, fps, w, h, cache)
    scores, boxes = scan(video, cfg["det"], cfg["det_imgsz"], conf,
                         int(round(dur * fps_float(fps))), stages=S)
    n = len(boxes)
    if n == 0:
        raise RuntimeError("No frames decoded - check the start/end times and the video file.")
    shots = shots_from_scores(scores, min_len=max(3, round(0.15 * fps_float(fps))))
    parts = plan_parts(shots, n, max(1, int(round(part_seconds * fps_float(fps)))))
    st = dict(version=3, name=name, job_dir=job_dir, src=os.path.basename(src), start=start,
              end=end, preset=preset, conf=conf, fps=fps, n=n, w=w, h=h,
              audio="audio.m4a" if audio else None, shots=shots, parts=parts,
              units=make_units(shots, parts), boxes=boxes, seeds={}, auto=None, grow=0.012,
              created=time.time())
    save_job(st)
    _attach(st, cache_root)
    log(f"{n} frames, {len(shots)} scene(s), {len(parts)} part(s).", 1.0)
    return st


def load_job(job_dir, cache_root):
    with open(os.path.join(job_dir, JOB_FILE), "rb") as f:
        st = pickle.load(f)
    st["job_dir"] = job_dir  # folder may have been moved/renamed
    return _attach(st, cache_root)


def list_jobs(jobs_root):
    out = []
    for p in sorted(glob.glob(os.path.join(jobs_root, "*", JOB_FILE)), reverse=True):
        try:
            with open(p, "rb") as f:
                st = pickle.load(f)
        except Exception:
            continue
        d = os.path.dirname(p)
        done = sum(1 for k in range(len(st["parts"])) if _part_done_file(d, k))
        out.append(dict(job_dir=d, name=st["name"], src=st["src"],
                        seconds=st["n"] / fps_float(st["fps"]), parts=len(st["parts"]),
                        done=done, final=os.path.exists(final_path(d, st))))
    return out


def unit_label(st, u):
    a, b, k = st["units"][u]
    pieces = [v for v, x in enumerate(st["units"]) if x[2] == k]
    return f"Scene {k + 1}" if len(pieces) == 1 else f"Scene {k + 1}.{pieces.index(u) + 1}"


def scene_seed(st, u):
    if u in st["seeds"]:
        return st["seeds"][u]
    a = (st["auto"] or {}).get(u)
    return None if a is None else (a["frame"], a["box"])


def set_keeper(st, img_pred, frame_idx, x, y, reset_search=True):
    """User clicked (x, y) on frame `frame_idx`: that scene piece keeps this person.
    reset_search=False keeps the other scenes' search results (used for quick fixes)."""
    box, mask = person_at(img_pred, st["_video"][frame_idx], st["boxes"][frame_idx], x, y)
    if box is None:
        return None
    u = int(st["_unit_of"][frame_idx])
    st["seeds"][u] = (int(frame_idx), np.asarray(box, np.float32))
    st.setdefault("seed_src", {}).pop(u, None)
    if reset_search:
        st["auto"] = None  # references changed -> redo the scene search
    save_job(st)
    return mask


def set_absent(st, frame_idx, reset_search=True):
    st["seeds"][int(st["_unit_of"][frame_idx])] = None
    if reset_search:
        st["auto"] = None
    save_job(st)


def _seed_key(seed):
    return None if seed is None else [int(seed[0])] + [round(float(v), 1) for v in seed[1]]


def _ensure_target(st, vid_pred, u, seed):
    """Masks of the kept person in scene piece u (reused if already made for this seed)."""
    lo, hi, _ = st["units"][u]
    tgt = os.path.join(st["cache"], "target")
    os.makedirs(tgt, exist_ok=True)
    key = _seed_key(seed)
    if st["_tracked"].get(u, "none") == key and all(os.path.exists(_mpath(tgt, i)) for i in range(lo, hi)):
        return
    if seed is None:
        for i in range(lo, hi):
            _write_mask(tgt, i, np.zeros((st["h"], st["w"]), bool))
    else:
        st["_video"].ensure(lo, hi)
        track_target(vid_pred, st["_video"], seed[0], seed[1], tgt,
                     os.path.join(st["cache"], "tmp_track"), lo, hi)
    st["_tracked"][u] = key


def save_photos(st, paths):
    """Keep copies of the reference photos in the job folder (used again after a resume)."""
    d = os.path.join(st["job_dir"], "photos")
    os.makedirs(d, exist_ok=True)
    keep = []
    for k, p in enumerate(paths or []):
        dst = os.path.join(d, f"photo_{k:02d}{os.path.splitext(p)[1].lower() or '.jpg'}")
        _copy_atomic(p, dst)
        keep.append(dst)
    st["photos"] = keep
    save_job(st)
    return keep


def anchors_from_photos(st, reid, img_pred, max_anchors=3, min_face=0.45):
    """Find the person from the reference photos (by face) in the first scenes where they
    clearly appear; those scenes become the starting points. Returns how many were found."""
    reid.reset()
    if not sum(bool(reid.add_photo(p)) for p in st.get("photos", [])):
        return -1  # no usable face in the photos
    found = []
    S = Stages(["Looking for your person using the photos"])
    S.start(0)
    for u, (lo, hi, _) in enumerate(st["units"]):
        r = reid.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi, n_samples=4)
        if r and r["how"] == "face" and r["score"] >= min_face:
            found.append(u)
            st["seeds"][u] = (int(r["frame"]), np.asarray(r["box"], np.float32))
            st.setdefault("seed_src", {})[u] = "photo"
        S.step(u + 1, len(st["units"]))
        if len(found) >= max_anchors:
            break
    st["auto"] = None
    save_job(st)
    return len(found)


# ---------------------------------------------------------------- mode: remove some people
def _iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def removal_seeds(st, u):
    """People to remove in scene piece u: the user's choice there, else the search result."""
    if u in st.get("rseeds", {}):
        return st["rseeds"][u]
    return (st.get("rauto") or {}).get(u, [])


def toggle_removal(st, img_pred, frame_idx, x, y, reset_search=True):
    """Click on a person: add them to the people to remove, or take them off again.
    Returns (mask, added) or (None, None) if nobody is there."""
    box, mask = person_at(img_pred, st["_video"][frame_idx], st["boxes"][frame_idx], x, y)
    if box is None:
        return None, None
    u = int(st["_unit_of"][frame_idx])
    cur = list(removal_seeds(st, u))
    same = [k for k, (f, b) in enumerate(cur) if f == frame_idx and _iou(b, box) > 0.5]
    if same:
        cur.pop(same[0])
        added = False
    else:
        cur.append((int(frame_idx), np.asarray(box, np.float32)))
        added = True
    st.setdefault("rseeds", {})[u] = cur
    if reset_search:
        st["rauto"] = None
    save_job(st)
    return mask, added


def clear_removal(st, frame_idx, reset_search=False):
    st.setdefault("rseeds", {})[int(st["_unit_of"][frame_idx])] = []
    if reset_search:
        st["rauto"] = None
    save_job(st)


def _ensure_removal(st, vid_pred, u):
    """Masks of everyone to remove in scene piece u (each person tracked, then combined)."""
    lo, hi, _ = st["units"][u]
    seeds = removal_seeds(st, u)
    tgt = os.path.join(st["cache"], "target")
    os.makedirs(tgt, exist_ok=True)
    key = ["remove"] + [_seed_key(s) for s in seeds]
    if st["_tracked"].get(u, "none") == key and all(os.path.exists(_mpath(tgt, i)) for i in range(lo, hi)):
        return
    for i in range(lo, hi):
        _write_mask(tgt, i, np.zeros((st["h"], st["w"]), bool))
    if seeds:
        st["_video"].ensure(lo, hi)
    one = os.path.join(st["cache"], "target_one")
    for f, box in seeds:
        shutil.rmtree(one, ignore_errors=True)
        track_target(vid_pred, st["_video"], f, box, one, os.path.join(st["cache"], "tmp_track"),
                     lo, hi)
        for i in range(lo, hi):
            _write_mask(tgt, i, _read_mask(tgt, i) | _read_mask(one, i))
    shutil.rmtree(one, ignore_errors=True)
    st["_tracked"][u] = key


def find_targets(st, reid, vid_pred, img_pred):
    """Find every chosen person again in the other scenes (each one separately)."""
    import copy
    picks = [(u, f, b) for u, lst in st.get("rseeds", {}).items() for f, b in lst]
    if not picks:
        raise ValueError("Click on the people to remove first.")
    S = Stages(["Learning what each person looks like", "Searching every scene"])
    S.start(0)
    refs = []
    one = os.path.join(st["cache"], "target_one")
    for t, (u, f, b) in enumerate(picks):
        lo, hi, _ = st["units"][u]
        st["_video"].ensure(lo, hi)
        shutil.rmtree(one, ignore_errors=True)
        track_target(vid_pred, st["_video"], f, b, one, os.path.join(st["cache"], "tmp_track"), lo, hi)
        r = copy.copy(reid)
        r.reset()
        good = [i for i in range(lo, hi) if _read_mask(one, i).sum() >= 400]
        for i in [good[int(round(x))] for x in np.linspace(0, len(good) - 1, min(6, len(good)))]:
            m = _read_mask(one, i)
            r.add_person(cv2.imread(st["_video"][i]), _bbox(m), m)
        refs.append(r)
        S.step(t + 1, len(picks))
    shutil.rmtree(one, ignore_errors=True)
    S.start(1)
    auto = {}
    todo = [u for u in range(len(st["units"])) if u not in st.get("rseeds", {})]
    for t, u in enumerate(todo):
        lo, hi, _ = st["units"][u]
        found = []
        for r in refs:
            res = r.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi)
            if res is None:
                continue
            seed = (int(res["frame"]), np.asarray(res["box"], np.float32))
            if not any(f == seed[0] and _iou(b, seed[1]) > 0.5 for f, b in found):
                found.append(seed)
        auto[u] = found
        S.step(t + 1, len(todo))
    st["rauto"] = auto
    save_job(st)
    n = sum(1 for u in range(len(st["units"])) if removal_seeds(st, u))
    log(f"People to remove were found in {n} of {len(st['units'])} scene piece(s).", 1.0)
    return st


def mask_removal(img_pred, frames, boxes, tgt_dir, raw_dir, prot_dir, lo, hi, stages=None):
    """Remove mode, per frame: the tracked people to remove, completed with their detections;
    every other detected person is protected (never erased)."""
    for d in (raw_dir, prot_dir):
        os.makedirs(d, exist_ok=True)
    seg = {}
    for i in range(lo, hi):
        if i not in seg:
            ks = list(range(i, min(hi, i + SEG_BATCH)))
            got = segment_frames(img_pred, [cv2.imread(frames[k]) for k in ks], [boxes[k] for k in ks])
            seg = dict(zip(ks, got))
        rem = _read_mask(tgt_dir, i)
        prot = np.zeros_like(rem)
        if len(boxes[i]):
            for m in seg[i]:
                if rem.any() and (m & rem).sum() >= 0.3 * max(m.sum(), 1):
                    rem |= m
                else:
                    prot |= m
        prot &= ~rem
        _write_mask(raw_dir, i, rem)
        _write_mask(prot_dir, i, prot)
        if stages:
            stages.step(i - lo + 1, hi - lo)


def find_person(st, reid, vid_pred, img_pred, photos=()):
    """Find the kept person in every scene piece the user did not decide."""
    if not any(v is not None for v in st["seeds"].values()):
        raise ValueError("Click on the person to keep first.")
    tgt = os.path.join(st["cache"], "target")
    user = [u for u, v in st["seeds"].items() if v is not None]
    S = Stages(["Learning what your person looks like", "Searching every scene"])
    S.start(0)
    reid.reset()
    for p in list(photos or ()) + list(st.get("photos", [])):
        reid.add_photo(p)
    for t, u in enumerate(user):
        _ensure_target(st, vid_pred, u, st["seeds"][u])
        lo, hi, _ = st["units"][u]
        good = [i for i in range(lo, hi) if _read_mask(tgt, i).sum() >= 400]
        for i in [good[int(round(x))] for x in np.linspace(0, len(good) - 1, min(6, len(good)))]:
            m = _read_mask(tgt, i)
            reid.add_person(cv2.imread(st["_video"][i]), _bbox(m), m)
        S.step(t + 1, len(user))
    S.start(1)
    auto = {}
    todo = [u for u in range(len(st["units"])) if u not in st["seeds"]]
    for t, u in enumerate(todo):
        lo, hi, _ = st["units"][u]
        auto[u] = reid.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi)
        S.step(t + 1, len(todo))
    st["auto"] = auto
    save_job(st)
    found = sum(1 for u in range(len(st["units"])) if scene_seed(st, u) is not None)
    log(f"Your person is in {found} of {len(st['units'])} scene piece(s).", 1.0)
    return st


def _part_file(job_dir, p, kind=""):
    return os.path.join(job_dir, "parts", f"part_{p:04d}{kind}")


def _part_done_file(job_dir, p):
    return all(os.path.exists(_part_file(job_dir, p, k)) for k in (".mp4", "_check.mp4", ".json"))


def _part_signature(st, p, grow, pad):
    a, b = st["parts"][p]
    us = [u for u, (lo, hi, _) in enumerate(st["units"]) if a <= lo and hi <= b]
    if st.get("mode") == "remove":
        seeds = [[_seed_key(x) for x in removal_seeds(st, u)] for u in us]
    else:
        seeds = [_seed_key(scene_seed(st, u)) for u in us]
    extra = [[_seed_key(x) for x in st.get(k, {}).get(u, [])] for k in ("extra", "keep_extra")
             for u in us]
    return {"range": [a, b], "mode": st.get("mode", "keep"), "seeds": seeds, "extra": extra,
            "opts": st.get("part_opts", {}).get(p, {}), "steps": st.get("steps"),
            "grow": grow, "pad": pad, "preset": st["preset"], "fill": st.get("fill", "realistic")}


def part_is_current(st, p, grow=None, pad=2):
    if not _part_done_file(st["job_dir"], p):
        return False
    try:
        with open(_part_file(st["job_dir"], p, ".json")) as f:
            saved = json.load(f)
    except Exception:
        return False
    return saved == _part_signature(st, p, st["grow"] if grow is None else grow, pad)


def final_path(job_dir, st, check=False):
    base = os.path.splitext(st["src"])[0]
    out_dir = st.get("out_dir") or job_dir
    what = "people removed" if st.get("mode") == "remove" else "one person"
    return os.path.join(out_dir, f"{base} - {what}{' - check' if check else ''}.mp4")


_DET = {}


def _detector(weights):
    if weights not in _DET:
        from ultralytics import YOLO
        _DET.clear()
        _DET[weights] = YOLO(weights)
    return _DET[weights]


def verify_part(st, part_mp4, a, b, prot_dir, final_dir, stride=3, conf=0.35):
    """Self-check of a finished part: people who should not be there. Keep mode: anyone away
    from the kept person. Remove mode: a person seen where someone was removed."""
    cfg = PRESETS[st["preset"]]
    det, w, h = _detector(cfg["det"]), st["w"], st["h"]
    remove_mode = st.get("mode") == "remove"
    out, batch, ids = [], [], []

    def kept_nearby(g, bx):  # tracking dropout of the kept person must not count
        for dg in range(1, 46):
            for gg in (g - dg, g + dg):
                if a <= gg < b:
                    pr = _read_mask(prot_dir, gg)
                    if pr.any():
                        return _iou(bx, _bbox(pr)) > 0.3
        return False

    def flush():
        res = det.predict(batch, classes=[0], conf=conf, imgsz=cfg["det_imgsz"], verbose=False,
                          device=0 if DEVICE == "cuda" else "cpu")
        for g, r in zip(ids, res):
            for bx in r.boxes.xyxy.cpu().numpy().astype(np.float32):
                x1, y1 = max(0, int(bx[0])), max(0, int(bx[1]))
                x2, y2 = min(w, int(bx[2])), min(h, int(bx[3]))
                if x2 - x1 < 4 or y2 - y1 < 4:
                    continue
                pr = _read_mask(prot_dir, g)
                if remove_mode:
                    if (_read_mask(final_dir, g)[y1:y2, x1:x2].mean() > 0.5
                            and pr[y1:y2, x1:x2].mean() < 0.3):
                        out.append((g, bx))
                    continue
                if pr[y1:y2, x1:x2].mean() >= 0.15:
                    continue
                if pr.any() and _iou(bx, _bbox(pr)) >= 0.2:
                    continue
                if not pr.any() and kept_nearby(g, bx):
                    continue
                out.append((g, bx))
        batch.clear()
        ids.clear()

    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", part_mp4, "-f", "rawvideo",
                             "-pix_fmt", "bgr24", "-vsync", "passthrough", "-"],
                            stdout=subprocess.PIPE, bufsize=10 ** 8)
    try:
        for g in range(a, b):
            buf = proc.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            if (g - a) % stride == 0:
                batch.append(np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy())
                ids.append(g)
                if len(batch) == 8:
                    flush()
        if batch:
            flush()
    finally:
        proc.stdout.close()
        proc.wait()
    return out


def _apply_self_fix(st, p, viol, max_per_unit=3):
    """Turn self-check findings into fixes for this part. Returns how many fixes were made."""
    opts = st.setdefault("part_opts", {}).setdefault(p, {})
    if st.get("mode") == "remove":  # leftovers where people were removed: wider masks, repaint
        opts["grow_mult"] = round(opts.get("grow_mult", 1.0) * 1.4, 3)
        opts["seed"] = opts.get("seed", 42) + 1
        return 1
    made = 0
    groups = {}
    for g, bx in viol:  # same person seen in several frames -> one fix
        u = int(st["_unit_of"][g])
        gl = groups.setdefault(u, [])
        for grp in gl:
            if _iou(grp[-1][1], bx) > 0.3:
                grp.append((g, bx))
                break
        else:
            gl.append([(g, bx)])
    for u, gl in groups.items():
        cur = st.setdefault("extra", {}).setdefault(u, [])
        for grp in sorted(gl, key=len, reverse=True)[:max_per_unit]:
            g, bx = grp[len(grp) // 2]
            if not any(f == g and _iou(b2, bx) > 0.5 for f, b2 in cur):
                cur.append((int(g), np.asarray(bx, np.float32)))
                made += 1
    if made:
        opts["grow_mult"] = round(opts.get("grow_mult", 1.0) * 1.15, 3)
    return made


def _track_extra(st, vid_pred, video, key, us, work, dst, minus=None):
    """Track people the user or the self-check pointed out (st[key][unit] = seeds) and add
    them to the masks in dst (minus the pixels in `minus`)."""
    one = os.path.join(work, "extra_one")
    for u in us:
        lo, hi, _ = st["units"][u]
        for f, box in st.get(key, {}).get(u, []):
            shutil.rmtree(one, ignore_errors=True)
            track_target(vid_pred, video, f, box, one, os.path.join(work, "tmp_track"), lo, hi)
            os.makedirs(dst, exist_ok=True)
            for i in range(lo, hi):
                m = _read_mask(one, i)
                if minus:
                    m &= ~_read_mask(minus, i)
                if os.path.exists(_mpath(dst, i)):
                    m |= _read_mask(dst, i)
                _write_mask(dst, i, m)


_FILL = {}


def _get_filler():
    """(fill model or None, close after use). On big GPUs it stays loaded between parts."""
    if not big_gpu():
        return MiniMaxFiller(), True
    if "mm" not in _FILL:
        try:
            _FILL["mm"] = MiniMaxFiller()
        except Exception:
            _FILL["mm"] = None
            raise
    if _FILL["mm"] is None:
        raise RuntimeError("fill model unavailable")
    return _FILL["mm"], False


def _build_part(st, p, vid_pred, img_pred, pp_dir, grow, pad, check):
    """Masks, fill and composite for one part, left in the part work folder.
    Returns the self-check findings (empty if all is well or not checked)."""
    a, b = st["parts"][p]
    video, w, h, fps = st["_video"], st["w"], st["h"], st["fps"]
    us = [u for u, (lo, hi, _) in enumerate(st["units"]) if a <= lo and hi <= b]
    ranges = [tuple(st["units"][u][:2]) for u in us]
    opts = st.get("part_opts", {}).get(p, {})
    grow_eff = grow * opts.get("grow_mult", 1.0)
    steps, seed = opts.get("steps") or st.get("steps"), opts.get("seed", 42)
    cfg = PRESETS[st["preset"]]
    pp_side = 1280 if (st["preset"] == "Best" and big_gpu()) else cfg["pp_max_side"]
    work = os.path.join(st["cache"], "part_work")
    shutil.rmtree(work, ignore_errors=True)
    d = {k: os.path.join(work, k) for k in ("raw", "protect", "inst", "tracked", "final")}
    tgt = os.path.join(st["cache"], "target")
    remove_mode = st.get("mode") == "remove"
    S = Stages(["Tracking the people to remove" if remove_mode else "Tracking your person",
                "Outlining everyone", "Tracking everyone else", "Building masks",
                "Rebuilding background", "Writing video", "Checking the result"],
               outer=(p, len(st["parts"])))
    S.start(0)
    video.ensure(a, b)
    for t, u in enumerate(us):
        if remove_mode:
            _ensure_removal(st, vid_pred, u)
        else:
            _ensure_target(st, vid_pred, u, scene_seed(st, u))
        S.step(t + 1, len(us))
    S.start(1)
    if remove_mode:
        mask_removal(img_pred, video, st["boxes"], tgt, d["raw"], d["protect"], a, b, stages=S)
        _track_extra(st, vid_pred, video, "keep_extra", us, work, d["protect"])
        os.makedirs(d["tracked"], exist_ok=True)
        _track_extra(st, vid_pred, video, "extra", us, work, d["tracked"], minus=d["protect"])
    else:
        mask_others(img_pred, video, st["boxes"], tgt, d["raw"], d["protect"], d["inst"], a, b,
                    stages=S)
        S.start(2)
        track_others(vid_pred, video, d["inst"], d["protect"], d["tracked"],
                     os.path.join(work, "tmp_track"), ranges, stages=S)
        # people the self-check or the user pointed out
        _track_extra(st, vid_pred, video, "extra", us, work, d["tracked"], minus=d["protect"])
    S.start(3)
    flags = finalize_masks(d["raw"], d["tracked"], d["protect"], d["final"], ranges, pad,
                           max(1, round(grow_eff * max(h, w))))
    labels = {}
    for u in us:
        lo, hi, _ = st["units"][u]
        for i in range(lo, hi):
            labels[i] = unit_label(st, u).lower()
    chk = os.path.join(work, "check.mp4")
    make_preview(video, d["final"], d["protect"], chk, fps, a, b, labels.get, w, h)
    S.start(4)
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    need = [r for r in ranges if any(flags[i] for i in range(*r))]
    static = [] if opts.get("no_plate") else [
        r for r in need if is_static(video, d["final"], d["protect"], *r)]
    st.setdefault("plate_ranges", {})[p] = static
    moving = [r for r in need if r not in static]
    if static or moving:
        log(f"  {len(static)} steady-camera and {len(moving)} moving-camera scene piece(s) to fill")
    fills, ov = [], 16
    filler, close_it = None, False
    use_ai = st.get("fill", "realistic") == "realistic" or opts.get("ai")
    offload = use_ai and not big_gpu()
    if offload:
        _sam2_to(vid_pred, img_pred, "cpu")  # free GPU memory for the fill model
    try:
        if use_ai:
            try:
                filler, close_it = _get_filler()
            except Exception as e:  # missing model, download problem ... -> fast fill instead
                traceback.print_exc()
                log(f"  realistic fill unavailable ({e.__class__.__name__}); using the fast fill")
        if static:
            fills.append(plate_fill(video, d["final"], d["protect"], flags, static, w, h, filler,
                                    steps=steps, seed=seed, stages=S))
        done_moving = False
        if moving and filler is not None:
            for win in ((81, 49, 25) if big_gpu() else (49, 25)):
                try:
                    shutil.rmtree(os.path.join(work, "mm_out"), ignore_errors=True)
                    fills.append(fill_realistic(video, d["final"], flags, work, moving, w, h, filler,
                                                window=win, overlap=8, stages=S, seed=seed,
                                                steps=steps))
                    ov, done_moving = 8, True
                    break
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    log("  GPU memory full; retrying with shorter pieces")
    finally:
        if filler is not None and close_it:
            filler.close()
        if offload:
            _sam2_to(vid_pred, img_pred, DEVICE)
    if moving and not done_moving:
        fills.append(inpaint(video, d["final"], flags, work, pp_dir, moving, w, h, pp_side,
                             stages=S))
        ov = 16
    chs, results = _merge_fills(fills)
    S.start(5)
    out = os.path.join(work, "part.mp4")
    composite(video, d["final"], d["protect"], flags, chs, results, out, fps, a, b, w, h,
              overlap=ov, stages=S)
    viol = []
    if check:
        S.start(6)
        viol = verify_part(st, out, a, b, d["protect"], d["final"])
    S.done()
    return viol


def process_part(st, p, vid_pred, img_pred, pp_dir, grow, pad=2, self_check=True):
    a, b = st["parts"][p]
    rep = {"found": 0, "fixed": 0, "left": []}
    for rnd in range(2 if self_check else 1):
        viol = _build_part(st, p, vid_pred, img_pred, pp_dir, grow, pad, check=self_check)
        if rnd == 0:
            rep["found"] = len(viol)
        if not viol:
            break
        frames = sorted({int(g) for g, _ in viol})
        if rnd == 1:  # still there after the automatic fix: show to the user
            rep["left"] = frames[::max(1, len(frames) // 5)][:5]
            log(f"  Self-check: {len(viol)} sighting(s) remain - please check them")
            break
        made = _apply_self_fix(st, p, viol)
        log(f"  Self-check: {len(viol)} sighting(s) of people who should be gone; "
            f"{'fixing this part' if made else 'nothing to change'}")
        save_job(st)
        if not made:
            rep["left"] = frames[::max(1, len(frames) // 5)][:5]
            break
        rep["fixed"] = made
    st.setdefault("selfcheck", {})[p] = rep
    work = os.path.join(st["cache"], "part_work")
    _copy_atomic(os.path.join(work, "part.mp4"), _part_file(st["job_dir"], p, ".mp4"))
    _copy_atomic(os.path.join(work, "check.mp4"), _part_file(st["job_dir"], p, "_check.mp4"))
    with open(_part_file(st["job_dir"], p, ".json") + ".tmp", "w") as f:
        json.dump(_part_signature(st, p, grow, pad), f)
    os.replace(_part_file(st["job_dir"], p, ".json") + ".tmp", _part_file(st["job_dir"], p, ".json"))
    # free local disk: this part's frames and masks are no longer needed
    shutil.rmtree(work, ignore_errors=True)
    st["_video"].drop(a, b)
    tgt = os.path.join(st["cache"], "target")
    for u, (lo, hi, _) in enumerate(st["units"]):
        if a <= lo and hi <= b:
            for i in range(lo, hi):
                try:
                    os.remove(_mpath(tgt, i))
                except FileNotFoundError:
                    pass
            st["_tracked"].pop(u, None)


# ---------------------------------------------------------------- feedback (fix & learn)
def part_of(st, frame):
    return next(k for k, (a, b) in enumerate(st["parts"]) if a <= frame < b)


def log_feedback(st, fb_dir, kind, frame=None, x=None, y=None, text=""):
    """Append one feedback record (and a marked snapshot) to the feedback log."""
    fb_dir = fb_dir or os.path.join(os.path.dirname(st["job_dir"]), "Feedback")
    os.makedirs(fb_dir, exist_ok=True)
    rec = dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), job=st["name"], video=st["src"],
               mode=st.get("mode", "keep"), kind=kind, frame=frame, x=x, y=y, text=text,
               second=None if frame is None else round(frame / fps_float(st["fps"]), 2))
    with open(os.path.join(fb_dir, "feedback.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    if frame is not None and x is not None:
        img = cv2.imread(st["_video"][frame])
        r = max(12, img.shape[1] // 60)
        cv2.circle(img, (int(x), int(y)), r, (0, 0, 255), max(3, r // 4))
        os.makedirs(os.path.join(fb_dir, "pictures"), exist_ok=True)
        cv2.imwrite(os.path.join(fb_dir, "pictures", f"{st['name']}_{frame:06d}_{kind}.jpg"), img)


def add_feedback(st, img_pred, kind, frame, x=None, y=None, text="", fb_dir=None):
    """Apply one correction from the user to the job (the affected part is redone on the
    next run) and log it. kind: person | smudge | edges | note. Returns a message."""
    frame = int(frame)
    u, p = int(st["_unit_of"][frame]), part_of(st, frame)
    opts = st.setdefault("part_opts", {}).setdefault(p, {})
    if kind == "person":
        box, _ = person_at(img_pred, st["_video"][frame], st["boxes"][frame], x, y)
        if box is None:
            return None
        seed = (frame, np.asarray(box, np.float32))
        if st.get("mode") == "remove":
            st.setdefault("rseeds", {})[u] = list(removal_seeds(st, u)) + [seed]
        else:
            st.setdefault("extra", {}).setdefault(u, []).append(seed)
        opts["grow_mult"] = round(opts.get("grow_mult", 1.0) * 1.2, 3)
        msg = "remove the person there"
    elif kind == "wrong":  # this person should stay
        box, _ = person_at(img_pred, st["_video"][frame], st["boxes"][frame], x, y)
        if box is None:
            return None
        if st.get("mode") == "remove":
            st.setdefault("keep_extra", {}).setdefault(u, []).append(
                (frame, np.asarray(box, np.float32)))
        else:
            set_keeper(st, img_pred, frame, x, y, reset_search=False)
        msg = "keep that person"
    elif kind == "smudge":
        opts["steps"] = min(24, (opts.get("steps") or st.get("steps") or 8) + 6)
        opts["seed"] = opts.get("seed", 42) + 1
        opts["ai"] = True
        opts["smudge"] = opts.get("smudge", 0) + 1
        if opts["smudge"] >= 2:  # still smudged: switch method (video model instead of plate)
            opts["no_plate"] = True
        msg = "repaint that area more carefully"
    elif kind == "edges":
        opts["grow_mult"] = round(opts.get("grow_mult", 1.0) * 1.5, 3)
        msg = "remove a wider area around people there"
    else:
        msg = "note saved"
    log_feedback(st, fb_dir, kind, frame, x, y, text)
    save_job(st)
    return msg


def learned_defaults(fb_dir):
    """Settings that adapt to the user's past corrections (the more often a problem was
    reported, the more the defaults lean against it)."""
    counts = {}
    path = os.path.join(fb_dir or "", "feedback.jsonl")
    if fb_dir and os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    k = json.loads(line)["kind"]
                except Exception:
                    continue
                counts[k] = counts.get(k, 0) + 1
    e, pz, sm = (min(counts.get(k, 0), 3) for k in ("edges", "person", "smudge"))
    notes = []
    if e:
        notes.append(f"wider edges (+{round((1.25 ** e - 1) * 100)}%)")
    if pz:
        notes.append("finds more people")
    if sm:
        notes.append("more careful painting")
    return dict(grow=round(0.012 * 1.25 ** e, 4), conf=max(0.15, 0.25 - 0.05 * min(pz, 2)),
                steps=8 + 4 * min(sm, 2), notes=notes, counts=counts)


def join_parts(st):
    """Losslessly join all part videos and add the original audio."""
    n_parts = len(st["parts"])
    outs = []
    for kind, check in (("", False), ("_check", True)):
        lst = os.path.join(st["cache"], f"join{kind}.txt")
        with open(lst, "w") as f:
            for p in range(n_parts):
                path = os.path.abspath(_part_file(st["job_dir"], p, kind + ".mp4"))
                f.write("file '" + path.replace("'", "'\\''") + "'\n")
        local = os.path.join(st["cache"], os.path.basename(final_path(st["job_dir"], st, check)))
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
        audio = os.path.join(st["cache"], "audio.m4a") if st.get("audio") and not check else None
        if audio:
            cmd += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{st['n'] / fps_float(st['fps']):.3f}"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", local + ".tmp.mp4"]
        subprocess.run(cmd, check=True)
        os.replace(local + ".tmp.mp4", local)
        _copy_atomic(local, final_path(st["job_dir"], st, check))
        outs.append(local)
    return outs[0], outs[1]


def remove_others(st, reid, vid_pred, img_pred, pp_dir, grow=0.012, photos=()):
    """Erase everyone except the kept person, part by part (finished parts are skipped,
    so this also resumes an interrupted job). Returns (video, check video) paths."""
    if st.get("mode") == "remove":
        if not any(st.get("rseeds", {}).values()):
            raise ValueError("Click on the people to remove first.")
        if st.get("rauto") is None and len(st["units"]) > len(st.get("rseeds", {})):
            find_targets(st, reid, vid_pred, img_pred)
    else:
        if not any(v is not None for v in st["seeds"].values()):
            raise ValueError("Click on the person to keep first.")
        if st["auto"] is None and len(st["units"]) > len(st["seeds"]):
            find_person(st, reid, vid_pred, img_pred, photos)
    st["grow"] = grow
    save_job(st)
    _PV.update(video=st["_video"], remove=st.get("mode") == "remove")
    TIMINGS.clear()
    t0 = time.time()
    todo = [p for p in range(len(st["parts"])) if not part_is_current(st, p, grow)]
    if todo and len(todo) < len(st["parts"]):
        log(f"{len(st['parts']) - len(todo)} of {len(st['parts'])} part(s) already done; "
            f"processing {len(todo)}.")
    for p in todo:
        process_part(st, p, vid_pred, img_pred, pp_dir, grow)
    final = final_path(st["job_dir"], st)
    local = os.path.join(st["cache"], os.path.basename(final))
    if todo or not os.path.exists(final):
        log("Joining parts and adding audio ...", 0.99)
        out, chk = join_parts(st)
    else:
        chk = os.path.join(st["cache"], os.path.basename(final_path(st["job_dir"], st, True)))
        out = local
        for src_, dst in ((final, out), (final_path(st["job_dir"], st, True), chk)):
            if not os.path.exists(dst):
                _copy_atomic(src_, dst)
    st["timings"] = dict(TIMINGS, total=time.time() - t0, parts_done=len(todo))
    save_job(st)
    log(f"Done: {final}", 1.0)
    return out, chk
