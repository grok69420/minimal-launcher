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

import cv2
import numpy as np
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
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


def set_progress(fn):
    """fn(fraction_or_None, text) - used by the web app to show progress."""
    global _PROGRESS
    _PROGRESS = fn


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
        self.i = i
        log(f"{self._pre()}{i + 1}/{len(self.names)} {self.names[i]} ...",
            self._f(i / len(self.names)))

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
    cv2.imwrite(_mpath(d, i), m.astype(np.uint8) * 255)


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
def scan(video, det_weights, imgsz, conf, n_est, stages=None, batch=8):
    """One streaming pass: colour-change score per frame (for scene cuts) + person boxes."""
    from ultralytics import YOLO
    model = YOLO(det_weights)
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
        st = pred.init_state(tmp, offload_video_to_cpu=True, offload_state_to_cpu=True)
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
    for i in range(lo, hi):
        tgt = _read_mask(tgt_dir, i)
        other = np.zeros_like(tgt)
        prot = tgt.copy()
        inst = []
        if len(boxes[i]):
            masks = segment_boxes(img_pred, cv2.imread(frames[i]), boxes[i])
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
        results[c] = os.path.join(out_root, name, "frames")
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
        img = cv2.imread(os.path.join(results[c], f"{g - a:04d}.png")).astype(np.float32)
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
        else:
            inp = _inpainted_frame(g, chs, results, overlap, (w, h))
            m = _read_mask(final_dir, g).astype(np.float32)
            a = np.maximum(cv2.GaussianBlur(m, (0, 0), feather_px), m) if feather_px > 0 else m
            a[_read_mask(prot_dir, g)] = 0.0
            out = orig.astype(np.float32) * (1 - a[..., None]) + inp * a[..., None]
            wr.write(np.clip(out + 0.5, 0, 255).astype(np.uint8))
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
    st["seeds"][int(st["_unit_of"][frame_idx])] = (int(frame_idx), np.asarray(box, np.float32))
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


def find_person(st, reid, vid_pred, img_pred, photos=()):
    """Find the kept person in every scene piece the user did not decide."""
    if not any(v is not None for v in st["seeds"].values()):
        raise ValueError("Click on the person to keep first.")
    tgt = os.path.join(st["cache"], "target")
    user = [u for u, v in st["seeds"].items() if v is not None]
    S = Stages(["Learning what your person looks like", "Searching every scene"])
    S.start(0)
    reid.reset()
    for p in photos or ():
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
    return {"range": [a, b], "seeds": [_seed_key(scene_seed(st, u)) for u in us],
            "grow": grow, "pad": pad, "preset": st["preset"]}


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
    return os.path.join(job_dir, f"{base}_one_person{'_check' if check else ''}.mp4")


def process_part(st, p, vid_pred, img_pred, pp_dir, grow, pad=2):
    a, b = st["parts"][p]
    video, w, h, fps = st["_video"], st["w"], st["h"], st["fps"]
    us = [u for u, (lo, hi, _) in enumerate(st["units"]) if a <= lo and hi <= b]
    ranges = [tuple(st["units"][u][:2]) for u in us]
    cfg = PRESETS[st["preset"]]
    pp_side = cfg["pp_max_side"]
    if DEVICE == "cuda" and st["preset"] == "Best" and \
            torch.cuda.get_device_properties(0).total_memory > 20e9:
        pp_side = 1280  # L4 / A100 have room for sharper fills
    work = os.path.join(st["cache"], "part_work")
    shutil.rmtree(work, ignore_errors=True)
    d = {k: os.path.join(work, k) for k in ("raw", "protect", "inst", "tracked", "final")}
    tgt = os.path.join(st["cache"], "target")
    S = Stages(["Tracking your person", "Outlining everyone else", "Tracking everyone else",
                "Building masks", "Rebuilding background", "Writing video"],
               outer=(p, len(st["parts"])))
    S.start(0)
    video.ensure(a, b)
    for t, u in enumerate(us):
        _ensure_target(st, vid_pred, u, scene_seed(st, u))
        S.step(t + 1, len(us))
    S.start(1)
    mask_others(img_pred, video, st["boxes"], tgt, d["raw"], d["protect"], d["inst"], a, b,
                stages=S)
    S.start(2)
    track_others(vid_pred, video, d["inst"], d["protect"], d["tracked"],
                 os.path.join(work, "tmp_track"), ranges, stages=S)
    S.start(3)
    flags = finalize_masks(d["raw"], d["tracked"], d["protect"], d["final"], ranges, pad,
                           max(1, round(grow * max(h, w))))
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
    chs, results = inpaint(video, d["final"], flags, work, pp_dir, ranges, w, h, pp_side,
                           stages=S)
    S.start(5)
    out = os.path.join(work, "part.mp4")
    composite(video, d["final"], d["protect"], flags, chs, results, out, fps, a, b, w, h,
              stages=S)
    _copy_atomic(out, _part_file(st["job_dir"], p, ".mp4"))
    _copy_atomic(chk, _part_file(st["job_dir"], p, "_check.mp4"))
    with open(_part_file(st["job_dir"], p, ".json") + ".tmp", "w") as f:
        json.dump(_part_signature(st, p, grow, pad), f)
    os.replace(_part_file(st["job_dir"], p, ".json") + ".tmp", _part_file(st["job_dir"], p, ".json"))
    # free local disk: this part's frames and masks are no longer needed
    shutil.rmtree(work, ignore_errors=True)
    video.drop(a, b)
    for u in us:
        lo, hi, _ = st["units"][u]
        for i in range(lo, hi):
            try:
                os.remove(_mpath(tgt, i))
            except FileNotFoundError:
                pass
        st["_tracked"].pop(u, None)


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
    if not any(v is not None for v in st["seeds"].values()):
        raise ValueError("Click on the person to keep first.")
    if st["auto"] is None and len(st["units"]) > len(st["seeds"]):
        find_person(st, reid, vid_pred, img_pred, photos)
    st["grow"] = grow
    save_job(st)
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
        out, chk = local, local.replace("_one_person.mp4", "_one_person_check.mp4")
        for src_, dst in ((final, out), (final_path(st["job_dir"], st, True), chk)):
            if not os.path.exists(dst):
                _copy_atomic(src_, dst)
    log(f"Done: {final}", 1.0)
    return out, chk
