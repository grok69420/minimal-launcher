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
import fcntl
import glob
import json
import math
import os
import pickle
import re
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cuda":  # faster maths on A100 / L4 at no visible quality cost
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    # cuDNN autotuning: measured on the A100 - no faster for the fill model, only adds tuning time
    torch.backends.cudnn.benchmark = os.environ.get("KOP_CUDNN_BENCH", "0") == "1"


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
    "Best": dict(sam2="large", det="yolo11x.pt", det_imgsz=1280, pp_max_side=960,
                 seg="yolo11x-seg.pt"),
    "Balanced": dict(sam2="base_plus", det="yolo11x.pt", det_imgsz=1280, pp_max_side=854,
                     seg="yolo11x-seg.pt"),
    "Fast": dict(sam2="small", det="yolo11m.pt", det_imgsz=640, pp_max_side=640,
                 seg="yolo11m-seg.pt"),
}
PART_SECONDS = 30.0
SCAN_IOU = 0.8
SCAN_THREADS = int(os.environ.get("KOP_SCAN_THREADS", "2"))
PAD = 4                # frames of temporal carry-over of the removal masks
GROW = 0.016           # removal masks are widened by this share of the picture size (hair, blur)
WORKER = False         # True inside a parallel worker process
OFFLOAD_VIDEO = False  # keep tracking frames in CPU memory (parallel workers share the GPU)
FILL_AREA = {"Best": 832 * 480, "Balanced": 640 * 368, "Fast": 512 * 288}
FILL_STEPS = {"Best": 8, "Balanced": 6, "Fast": 4}
# background painting quality levels: (name, working area, steps, frames/s on an A100, stride,
# tiny decoder). Below the model's own size (832x480) the painting shows a checkerboard
# pattern, so every level paints at 832x480; the faster levels paint every 2nd / 3rd frame
# and make the frames between by following the camera movement (no smearing).
# "film": SVOR (also removes shadows/reflections), real background from other frames, matched
# grain - for the best result, no time limit; never chosen automatically.
FILL_LEVELS = [("film", 832 * 480, 12, 1.4, 1, False, "svor"),
               ("sharpest", 832 * 480, 8, 4.0, 1, False), ("sharp", 832 * 480, 6, 5.9, 1, True),
               ("balanced", 832 * 480, 6, 11.0, 2, True), ("fast", 832 * 480, 6, 15.5, 3, True),
               ("fastest", 832 * 480, 6, 20.0, 4, True)]
FILM_FPS = 1.0  # film level, whole job on an A100 incl. the band repaint (measured, see README)
FILL_EFFICIENCY = 0.72  # share of that speed reached with tracking etc. sharing the GPU (measured)
# the engine's share of the 15 minutes; the rest is starting Colab, setup, upload and clicks
TARGET_SECONDS = 12 * 60
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
        flush_masks()
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
    return os.path.join(d, f"{i:06d}.msk")


def _lpath(d, i):  # person labels (small numbers per pixel) stay PNG
    return os.path.join(d, f"{i:06d}.png")


def load_mask(p):
    """Masks are stored as packed bits (8 pixels per byte): ~10x faster than PNG."""
    with open(p, "rb") as f:
        buf = f.read()
    h, w = (int(v) for v in np.frombuffer(buf, np.int32, 2))
    a = np.frombuffer(buf, np.uint8, offset=8).reshape(h, -1)
    return np.unpackbits(a, axis=1, count=w).view(bool)


_IO = ThreadPoolExecutor(6)  # disk writes run beside the GPU work
_PENDING = {}


def _read_mask(d, i):
    p = _mpath(d, i)
    f = _PENDING.get(p)
    if f is not None:
        f.result()
    return load_mask(p)


def _write_now(p, m):
    m = np.asarray(m, bool)
    with open(p + ".tmp", "wb") as f:
        f.write(np.array(m.shape[:2], np.int32).tobytes())
        f.write(np.packbits(m, axis=1).tobytes())
    os.replace(p + ".tmp", p)


def _write_mask(d, i, m):
    p = _mpath(d, i)
    old = _PENDING.pop(p, None)
    if old is not None:
        old.result()
    _PENDING[p] = _IO.submit(_write_now, p, m)
    if len(_PENDING) > 512:
        flush_masks()
    _live_view(d, i, m)


def flush_masks():
    """Wait until all masks are on disk."""
    for f in list(_PENDING.values()):
        f.result()
    _PENDING.clear()


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
                k = load_mask(prot)
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
                    "-preset", "veryfast", "-crf", "14", "-g", "30", "-pix_fmt", "yuv420p", "-an",
                    tmp], check=True)
    os.replace(tmp, out)


class TeeVideo:
    """Writes the master copy and hands the same frames to the scan in one decoding pass."""

    def __init__(self, src, out, fps, start=0.0, end=0.0):
        self.src, self.out, self.fps, self.start, self.end = src, out, fps, start, end
        png = subprocess.run(["ffmpeg", "-v", "error"] + _trim_args(start, end) +
                             ["-i", src, "-map", "0:v:0", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                              "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True).stdout
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Could not read the video.")
        self.h, self.w = img.shape[:2]

    def stream(self):
        tmp = self.out + ".tmp.mp4"
        cmd = (["ffmpeg", "-v", "error", "-y"] + _trim_args(self.start, self.end) +
               ["-i", self.src, "-filter_complex",
                f"[0:v:0]fps={self.fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,split=2[m][s]",
                "-map", "[m]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-g", "30",
                "-pix_fmt", "yuv420p", "-an", tmp,
                "-map", "[s]", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"])
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 8)
        size = self.w * self.h * 3
        try:
            while True:
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                yield np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        finally:
            p.stdout.close()
            rc = p.wait()
        if rc != 0:
            raise RuntimeError("Making the master copy failed.")
        os.replace(tmp, self.out)


MP4_AUDIO = {"aac", "mp3", "ac3", "eac3", "alac", "flac", "opus"}


def extract_audio(src, out, start=0.0, end=0.0):
    """The original sound, copied unchanged (no re-encoding). `out` should end in .mka."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + _trim_args(start, end) +
                       ["-i", src, "-map", "0:a:0", "-vn", "-c:a", "copy", out])
    return out if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0 else None


def audio_args(path):
    """ffmpeg options to put this audio into the MP4: copied when possible, else 320k AAC."""
    codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=codec_name", "-of", "csv=p=0", path],
                           capture_output=True, text=True).stdout.strip()
    return ["-c:a", "copy"] if codec in MP4_AUDIO else ["-c:a", "aac", "-b:a", "320k"]


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

    def extract_many(self, idxs):
        """Decode the video once and keep only the frames in idxs (much faster than seeking
        to hundreds of single frames)."""
        want = {int(i) for i in idxs if not os.path.exists(self.path(int(i)))}
        if not want:
            return
        last, size, jobs = max(want), self.w * self.h * 3, []
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", self.master, "-frames:v", str(last + 1),
                              "-f", "rawvideo", "-pix_fmt", "bgr24", "-vsync", "passthrough", "-"],
                             stdout=subprocess.PIPE, bufsize=10 ** 8)
        try:
            for i in range(last + 1):
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                if i in want:
                    img = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3).copy()
                    jobs.append(_IO.submit(cv2.imwrite, self.path(i), img,
                                           [cv2.IMWRITE_JPEG_QUALITY, 95]))
        finally:
            p.stdout.close()
            p.wait()
        for j in jobs:
            j.result()

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

    def __init__(self, path, w, h, fps, audio_src=None, crf=14, duration=None, preset="fast"):
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if audio_src:
            cmd += ["-i", audio_src, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:a", "aac", "-b:a", "192k"]
            if duration:  # video length decides; audio is trimmed to it, never the reverse
                cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
                "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", path]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, img):
        self.p.stdin.write(np.ascontiguousarray(img).tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg encoding failed")


# ---------------------------------------------------------------- scan: scenes + people
def _poly(p):
    p = np.asarray(p, np.float32).reshape(-1, 1, 2)
    if len(p) > 8:
        p = cv2.approxPolyDP(p, 1.0, True)
    return np.round(p.reshape(-1, 2)).astype(np.int16)


def scan(video, det_weights, imgsz, conf, n_est, stages=None, batch=None, seg_weights=None):
    """One streaming pass: colour-change score per frame (for scene cuts) + person boxes
    (+ person outlines when a segmentation model is given). Returns (scores, boxes, outlines
    or None)."""
    from ultralytics import YOLO
    model = None
    if seg_weights:
        try:
            model = YOLO(seg_weights)
        except Exception as e:  # not downloadable -> boxes only, outlines made later
            log(f"  outline model unavailable ({e.__class__.__name__}); using boxes only")
    segs = [] if model is not None else None
    weights = seg_weights if model is not None else det_weights
    model = model or YOLO(det_weights)
    batch = batch or (32 if DEVICE == "cuda" else 4)
    scores, boxes, buf, prev = [], [], [], None
    # two copies of the model work on alternate batches in threads, so reading the video, the
    # GPU work and turning masks into outlines (CPU) overlap instead of waiting for each other
    models = [model]
    if DEVICE == "cuda" and SCAN_THREADS > 1:
        try:
            models += [YOLO(weights) for _ in range(SCAN_THREADS - 1)]
        except Exception:
            pass
    pool = ThreadPoolExecutor(len(models))
    pending = []

    def predict(m, frames):
        # iou 0.8: in crowds people overlap a lot; the usual 0.7 throws away real people
        res = m.predict(frames, classes=[0], conf=conf, iou=SCAN_IOU, imgsz=imgsz, verbose=False,
                        device=0 if DEVICE == "cuda" else "cpu",
                        quantize=16 if DEVICE == "cuda" else None)
        out = []
        for r in res:
            bx = r.boxes.xyxy.cpu().numpy().astype(np.float32)
            sg = None
            if segs is not None:
                xy = r.masks.xy if r.masks is not None else []
                sg = [_poly(p) for p in xy]
            out.append((bx, sg))
        return out

    def collect(keep=0):
        while len(pending) > keep:
            for bx, sg in pending.pop(0).result():
                boxes.append(bx)
                if segs is not None:
                    segs.append(sg)

    def flush():
        pending.append(pool.submit(predict, models[flush.k % len(models)], list(buf)))
        flush.k += 1
        buf.clear()
        collect(keep=len(models))
    flush.k = 0

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
    collect()
    pool.shutdown()
    return np.asarray(scores, np.float32), boxes, segs


def crowd_frames(boxes, h, min_people=5, max_height=0.3):
    """Wide shots of a crowd: many people, all small (close-ups never qualify - cutting a
    close-up into tiles makes faces look like extra people)."""
    out = []
    for i, b in enumerate(boxes):
        if len(b) >= min_people and np.median(b[:, 3] - b[:, 1]) < max_height * h:
            out.append(i)
    return out


def tile_detect(weights, imgs, conf, iou=0.8, imgsz=960, overlap=0.2):
    """Small people in wide crowd shots: the frame is looked at in 4 overlapping tiles
    (each enlarged), so people far away are found too. Returns [(boxes, outlines)] in
    full-frame pixels; people cut by a tile edge are left to the neighbouring tile."""
    det = _detector(weights)
    h, w = imgs[0].shape[:2]
    tw, th = int(w * (0.5 + overlap / 2)), int(h * (0.5 + overlap / 2))
    offs = [(0, 0), (w - tw, 0), (0, h - th), (w - tw, h - th)]
    res = []
    for img in imgs:
        tiles = [img[y:y + th, x:x + tw] for x, y in offs]
        rr = det.predict(tiles, classes=[0], conf=conf, iou=iou, imgsz=imgsz, verbose=False,
                         device=0 if DEVICE == "cuda" else "cpu",
                         quantize=16 if DEVICE == "cuda" else None)
        bs, ps, ss = [], [], []
        for (x, y), r in zip(offs, rr):
            b = r.boxes.xyxy.cpu().numpy()
            xy = r.masks.xy if r.masks is not None else [None] * len(b)
            for k in range(len(b)):
                x1, y1, x2, y2 = b[k]
                cut = (x1 < 2 and x > 0) or (y1 < 2 and y > 0) or (x2 > tw - 2 and x + tw < w) or \
                      (y2 > th - 2 and y + th < h)
                if cut:
                    continue
                bs.append([x1 + x, y1 + y, x2 + x, y2 + y])
                ss.append(float(r.boxes.conf[k]))
                ps.append(None if xy[k] is None else _poly(np.asarray(xy[k]) + [x, y]))
        res.append((np.asarray(bs, np.float32).reshape(-1, 4), ps, np.asarray(ss, np.float32)))
    return res


def _iou_any(b, boxes, thr=0.5, contain=0.75):
    """True if box b is (almost) the same person as one of boxes."""
    if not len(boxes):
        return False
    x1 = np.maximum(b[0], boxes[:, 0])
    y1 = np.maximum(b[1], boxes[:, 1])
    x2 = np.minimum(b[2], boxes[:, 2])
    y2 = np.minimum(b[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    ab = (b[2] - b[0]) * (b[3] - b[1])
    ao = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    iou = inter / np.maximum(ab + ao - inter, 1e-6)
    return bool((iou > thr).any() or (inter / max(ab, 1e-6) > contain).any())


def add_crowd_people(st, video, a, b, batch=16):
    """Film mode: people the scan missed in wide crowd shots of frames [a, b) are added to
    the scan results (boxes + outlines)."""
    boxes, segs = st["boxes"], st.get("_segs")
    h = st["h"]
    idx = [i for i in crowd_frames(boxes[a:b], h)]
    idx = [a + i for i in idx]
    added = 0
    weights = PRESETS[st["preset"]].get("seg") or PRESETS[st["preset"]]["det"]
    for k in range(0, len(idx), batch):
        part = idx[k:k + batch]
        imgs = [cv2.imread(video[i]) for i in part]
        for i, (tb, tp, ts) in zip(part, tile_detect(weights, imgs, st.get("conf", 0.15))):
            keep_b, keep_p = [], []
            for j in np.argsort(-ts):
                if _iou_any(tb[j], boxes[i]) or (keep_b and _iou_any(tb[j], np.asarray(keep_b))):
                    continue
                keep_b.append(tb[j])
                keep_p.append(tp[j])
            if keep_b:
                boxes[i] = np.concatenate([boxes[i], np.asarray(keep_b, np.float32)])
                if segs is not None:
                    segs[i] = list(segs[i]) + keep_p
                added += len(keep_b)
    if idx:
        log(f"  crowd shots: {added} more people found in {len(idx)} frames")
    return added


def outline_masks(polys, boxes, h, w):
    """Person masks from the outlines found while scanning (box if an outline is missing)."""
    out = []
    for k, b in enumerate(boxes):
        m = np.zeros((h, w), np.uint8)
        p = polys[k] if polys is not None and k < len(polys) else None
        if p is not None and len(p) >= 3:
            cv2.fillPoly(m, [p.reshape(-1, 1, 2).astype(np.int32)], 1)
        if not m.any():
            m[max(0, int(b[1])):int(b[3]), max(0, int(b[0])):int(b[2])] = 1
        out.append(m > 0)
    return out


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
_SAM2_DIR = [None]


def load_sam2(sam2_dir, size="large", ckpt=None):
    _SAM2_DIR[0] = sam2_dir
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
        st = pred.init_state(tmp, offload_video_to_cpu=off or OFFLOAD_VIDEO,
                             offload_state_to_cpu=off, async_loading_frames=True)
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
    flush_masks()


def _segment(img_pred, frames, boxes, segs, ks, imgs):
    """Masks of the detected people in frames ks: scan outlines, else SAM 2. People without
    an outline from the scan are outlined by SAM 2 (instead of erasing their whole box)."""
    if segs is None:
        return segment_frames(img_pred, imgs, [boxes[k] for k in ks])
    out = [outline_masks(segs[k], boxes[k], imgs[j].shape[0], imgs[j].shape[1])
           for j, k in enumerate(ks)]
    miss = [[n for n in range(len(boxes[k])) if not (n < len(segs[k]) and segs[k][n] is not None
                                                       and len(segs[k][n]) >= 3)]
            for k in ks]
    if img_pred is not None and any(miss):
        js = [j for j in range(len(ks)) if miss[j]]
        try:
            got = segment_frames(img_pred, [imgs[j] for j in js],
                                 [np.asarray(boxes[ks[j]])[miss[j]] for j in js])
            for j, ms in zip(js, got):
                for n, m in zip(miss[j], ms):
                    if m.any():
                        out[j][n] = m
        except Exception:
            traceback.print_exc()
    return out


def mask_others(img_pred, frames, boxes, tgt_dir, raw_dir, prot_dir, inst_dir, lo, hi,
                keep_thr=0.3, stages=None, segs=None):
    """Per frame in [lo, hi): segment every detected person; the single detection that
    best matches the tracked person is skipped, all others go into the removal mask
    (and into an instance-label image used to seed tracking)."""
    for d in (raw_dir, prot_dir, inst_dir):
        if d:
            os.makedirs(d, exist_ok=True)
    seg, nxt = {}, None

    def load(ks):
        return ks, [cv2.imread(frames[k]) for k in ks]

    for i in range(lo, hi):
        if i not in seg:  # the next frames are read from disk while the GPU works
            ks = list(range(i, min(hi, i + SEG_BATCH)))
            imgs = nxt.result()[1] if nxt is not None and nxt.result()[0] == ks else load(ks)[1]
            nk = list(range(ks[-1] + 1, min(hi, ks[-1] + 1 + SEG_BATCH)))
            nxt = _IO.submit(load, nk) if nk else None
            got = _segment(img_pred, frames, boxes, segs, ks, imgs)
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
        if inst_dir:  # instance labels: only needed when every other person is tracked too
            lab = np.zeros(tgt.shape, np.uint8)
            for k, m in enumerate(sorted(inst, key=lambda x: -x.sum())[:254]):
                lab[m & ~prot] = k + 1
            _PENDING[_lpath(inst_dir, i)] = _IO.submit(cv2.imwrite, _lpath(inst_dir, i), lab)
        _write_mask(raw_dir, i, other)
        _write_mask(prot_dir, i, prot)
        if stages:
            stages.step(i - lo + 1, hi - lo)
    flush_masks()


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
                lab = cv2.imread(_lpath(inst_dir, s), cv2.IMREAD_GRAYSCALE)
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
    flush_masks()
    shutil.rmtree(tmp, ignore_errors=True)


def _grow(u, grow_px, k, k2):
    """Dilate a mask by grow_px (done at half size for large growths; same result to a pixel or
    two, several times faster)."""
    if grow_px < 8:
        return cv2.dilate(u.astype(np.uint8), k) > 0
    h, w = u.shape
    small = cv2.resize(u.astype(np.uint8), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    small = cv2.dilate((small > 0).astype(np.uint8), k2)
    return (cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST) > 0) | u


def finalize_masks(raw_dir, trk_dir, prot_dir, final_dir, ranges, pad_t=2, grow_px=15):
    """Union of detections + tracks, temporal carry-over inside the scene piece (covers
    flicker) and dilation (hair, motion blur). The kept person's pixels are never
    included. Returns {frame: needs_removal}."""
    os.makedirs(final_dir, exist_ok=True)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1))
    g2 = grow_px // 2 + 1  # a pixel more at half size: never smaller than the full-size growth
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g2 + 1, 2 * g2 + 1))
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
                u = _grow(u, grow_px, k, k2)
            u &= ~_read_mask(prot_dir, i)
            _write_mask(final_dir, i, u)
            flags[i] = bool(u.any())
    flush_masks()
    return flags


def preview_size(w, h, max_side=720):
    s = min(1.0, max_side / max(h, w))
    return int(w * s) // 2 * 2, int(h * s) // 2 * 2


def make_preview(frames, final_dir, prot_dir, out_mp4, fps, lo, hi, label, w, h):
    """Red = will be erased, green = kept person. Check this before trusting the result."""
    pw, ph = preview_size(w, h)
    wr = FFWriter(out_mp4, pw, ph, fps, crf=23, preset="ultrafast")
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
                prov, ctx = ["CPUExecutionProvider"], -1
                try:  # faces on the GPU (~15x faster) when onnxruntime-gpu is installed
                    import onnxruntime as ort
                    if hasattr(ort, "preload_dlls"):
                        ort.preload_dlls()
                    if DEVICE == "cuda" and "CUDAExecutionProvider" in ort.get_available_providers():
                        prov, ctx = ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
                except Exception:
                    pass
                fa = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"],
                                  providers=prov)
                fa.prepare(ctx_id=ctx, det_size=(640, 640))
                self.face = fa
            except Exception as e:  # never block the pipeline on the optional face model
                log(f"  face recognition unavailable ({e}); using appearance only")
        self.reset()

    def reset(self):
        self.ref_faces, self.ref_bodies = [], []
        self._seen = {}  # frame -> (descriptions, H, W): a second search reuses them


    def _faces(self, img):
        if self.face is None:
            return []
        out = []
        for f in self.face.get(img):
            x1, y1, x2, y2 = f.bbox
            if f.det_score >= 0.5 and min(x2 - x1, y2 - y1) >= self.MIN_FACE_PX:
                out.append(f)
        return out

    def _body(self, img, box, mask, embed=True):
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
        if not embed:
            return col, masked
        e = self.emb.embed([masked], imgsz=224, verbose=False)[0].float().cpu().numpy()
        e /= np.linalg.norm(e) + 1e-6
        return col, e

    def _bodies(self, img, boxes, masks):
        """_body for every person of a frame with one batched embedding call."""
        out = [self._body(img, b, m, embed=False) for b, m in zip(boxes, masks)]
        crops = [o[1] for o in out if o is not None]
        if not crops:
            return out
        es = self.emb.embed(crops, imgsz=224, verbose=False)
        res, k = [], 0
        for o in out:
            if o is None:
                res.append(None)
                continue
            e = es[k].float().cpu().numpy()
            e /= np.linalg.norm(e) + 1e-6
            res.append((o[0], e))
            k += 1
        return res

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
        bodies = self._bodies(img, boxes, masks)
        return [{"face": owner[k][1] if k in owner else None, "body": bodies[k]}
                for k in range(len(boxes))]

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

    @staticmethod
    def sample_frames(lo, hi, n_samples=6):
        """Frames to look at in [lo, hi): the middle first, then spread out."""
        inner = list(range(lo + 1, hi - 1)) if hi - lo > 4 else list(range(lo, hi))
        idxs = sorted(set(inner[int(round(t))] for t in
                          np.linspace(0, len(inner) - 1, min(n_samples, len(inner)))))
        mid = (lo + hi) / 2
        return sorted(idxs, key=lambda i: abs(i - mid))

    def find_in_shot(self, img_pred, frames, boxes, lo, hi, n_samples=6, segs=None,
                     closeups=True):
        """Best {frame, box, how, score} for the kept person in frames [lo, hi), or None."""
        cands = []
        seen = getattr(self, "_seen", None)
        if seen is None:
            seen = self._seen = {}
        for i in self.sample_frames(lo, hi, n_samples):
            if not len(boxes[i]):
                continue
            key = (getattr(frames, "dir", id(frames)), i)
            if key not in seen:
                img = cv2.imread(frames[i])
                masks = (outline_masks(segs[i], boxes[i], img.shape[0], img.shape[1])
                         if segs is not None else segment_boxes(img_pred, img, boxes[i]))
                seen[key] = (self.describe(img, boxes[i], masks), img.shape[0], img.shape[1])
            descs, H, W = seen[key]
            for k, d in enumerate(descs):
                b = boxes[i][k]
                cands.append(dict(frame=i, k=k, box=b, face=self.face_sim(d), body=self.body_sim(d),
                                  emb=d["face"], n=len(boxes[i]),
                                  big=(b[3] - b[1]) >= 0.6 * H or
                                  (b[2] - b[0]) * (b[3] - b[1]) >= 0.2 * W * H))
            if any(c["face"] is not None and c["face"] >= self.FACE_MATCH for c in cands):
                break  # the face decides; no need to look further
            fr = [c for c in cands if c["frame"] == i]
            if len(fr) == 1 and fr[0]["body"] >= self.BODY_MATCH + 0.04 and \
                    (fr[0]["face"] is None or fr[0]["face"] >= self.FACE_REJECT):
                break  # only one person here and clearly the right clothes
        if not cands:
            return None
        faced = [c for c in cands if c["face"] is not None and c["face"] >= self.FACE_MATCH]
        if faced:
            c = max(faced, key=lambda c: c["face"])
            return dict(frame=c["frame"], box=c["box"], how="face", score=c["face"], emb=c["emb"])
        ok = [c for c in cands if c["face"] is None or c["face"] >= self.FACE_REJECT]
        if not ok:
            return None
        c = max(ok, key=lambda c: c["body"])
        rivals = [o["body"] for o in cands if o["frame"] == c["frame"] and o["k"] != c["k"]]
        if c["body"] >= self.BODY_MATCH and (not rivals or c["body"] - max(rivals) >= self.BODY_MARGIN):
            return dict(frame=c["frame"], box=c["box"], how="appearance", score=c["body"])
        # a close-up of a single person who is not clearly someone else: keep them. Erasing a
        # face that fills the picture leaves a smear over the whole frame.
        close = [c for c in ok if c["n"] == 1 and c["big"]] if closeups else []
        if close:
            c = max(close, key=lambda c: (c["box"][2] - c["box"][0]) * (c["box"][3] - c["box"][1]))
            return dict(frame=c["frame"], box=c["box"], how="close-up", score=c["body"])
        return None


# ---------------------------------------------------------------- realistic fill (MiniMax-Remover)
MM_CODE = os.environ.get("KOP_MM_CODE", "/content/repos/MiniMax-Remover")
MM_WEIGHTS = os.environ.get("KOP_MM_WEIGHTS", "/content/repos/minimax_weights")


_FILL_AREA = [832 * 480]
MM_FAST = os.environ.get("KOP_MM_FAST", "1") == "1"
TAE = os.environ.get("KOP_TAE", "0") == "1"
TAE_URL = "https://github.com/madebyollin/taehv/raw/main/"
TAE_WEIGHTS = os.environ.get("KOP_TAE_WEIGHTS", "/content/repos/taehv/taew2_1.pth")


def fill_size(w, h, area=None):
    """Working size for the generative fill (the model was trained at 832x480; smaller sizes
    are faster)."""
    area = area or _FILL_AREA[0]
    a, ref = w / h, 832 / 480
    k = (area / (832 * 480)) ** 0.5
    if abs(a - ref) / ref < 0.06:
        return int(round(832 * k / 16)) * 16, int(round(480 * k / 16)) * 16
    if abs(a - 1 / ref) * ref < 0.06:
        return int(round(480 * k / 16)) * 16, int(round(832 * k / 16)) * 16
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
        self.tae = None  # optional tiny decoder (much faster, slightly softer)
        if TAE:
            self.use_tae()

    def use_tae(self, on=True):
        if not on:
            self.tae = None
            return
        if getattr(self, "_tae", None) is not None:
            self.tae = self._tae
            return
        d = os.path.dirname(TAE_WEIGHTS)
        os.makedirs(d, exist_ok=True)
        for name in ("taehv.py", "taew2_1.pth"):
            if not os.path.exists(os.path.join(d, name)):
                subprocess.run(["wget", "-q", "-O", os.path.join(d, name + ".part"),
                                TAE_URL + name], check=True)
                os.replace(os.path.join(d, name + ".part"), os.path.join(d, name))
        if d not in sys.path:
            sys.path.insert(0, d)
        from taehv import TAEHV
        self.tae = self._tae = TAEHV(TAE_WEIGHTS).to("cuda", torch.float16).eval()

    def fill(self, imgs, masks, fw, fh, dil=2, seed=42, steps=None):
        """imgs: BGR frames, masks: bool arrays; len must be 4k+1. Returns BGR frames (fw x fh)."""
        if MM_FAST:
            try:
                with _gpu_lock(_LOCK_ST[0]):  # one painting at a time on the GPU
                    try:
                        return self._fill_gpu(imgs, masks, fw, fh, dil, seed, steps or self.steps)
                    finally:  # give the memory back: the other parts (processes) need it too
                        if WORKER:
                            torch.cuda.empty_cache()
            except torch.cuda.OutOfMemoryError:
                raise
            except Exception:
                traceback.print_exc()
                log("  (fast painting path failed - using the standard one)")
        x = np.stack([cv2.cvtColor(cv2.resize(im, (fw, fh), interpolation=cv2.INTER_AREA),
                                   cv2.COLOR_BGR2RGB) for im in imgs])
        m = np.stack([cv2.resize(k.astype(np.uint8), (fw, fh), interpolation=cv2.INTER_NEAREST)
                      for k in masks])[..., None]
        with _gpu_lock(_LOCK_ST[0]):  # one painting at a time on the GPU
            out = self.pipe(images=torch.from_numpy(x).float() / 127.5 - 1.0,
                            masks=torch.from_numpy(m).float(), num_frames=len(imgs), height=fh,
                            width=fw, num_inference_steps=steps or self.steps,
                            generator=torch.Generator(device="cuda").manual_seed(seed),
                            iterations=dil).frames[0]
        return [cv2.cvtColor(np.clip(o * 255 + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
                for o in out]

    @torch.no_grad()
    def _fill_gpu(self, imgs, masks, fw, fh, dil, seed, steps):
        """Same result as the model's own pipeline, but every step stays on the GPU (the
        pipeline resizes and widens the masks on the CPU, ~15 % of its time) and both
        pictures are encoded in one batch."""
        p, dev, F_ = self.pipe, "cuda", torch.nn.functional
        n = len(imgs)
        x = torch.from_numpy(np.stack(imgs)).to(dev, non_blocking=True)  # n,H,W,3 BGR uint8
        x = x.flip(-1).permute(0, 3, 1, 2).half()  # n,3,H,W RGB
        if x.shape[-2:] != (fh, fw):
            x = F_.interpolate(x, size=(fh, fw), mode="bilinear", antialias=True, align_corners=False)
        x = (x / 127.5 - 1.0).clamp_(-1, 1)
        m = torch.from_numpy(np.stack(masks).view(np.uint8)).to(dev, non_blocking=True).half()
        if m.shape[-2:] != (fh, fw):
            m = F_.interpolate(m[:, None], size=(fh, fw), mode="nearest")[:, 0]
        for _ in range(dil):  # = scipy binary_dilation (4-neighbour cross), as the pipeline does
            q = F_.pad(m[None], (1, 1, 1, 1))[0]
            m = torch.maximum(torch.maximum(q[:, 1:-1, 1:-1], q[:, :-2, 1:-1]),
                              torch.maximum(torch.maximum(q[:, 2:, 1:-1], q[:, 1:-1, :-2]), q[:, 1:-1, 2:]))
        img = x.permute(1, 0, 2, 3)[None]  # 1,3,n,h,w
        m3 = m[None, None].expand(1, 3, n, fh, fw)
        vae = p.vae
        mean = torch.tensor(vae.config.latents_mean).view(1, -1, 1, 1, 1).to(dev, torch.float16)
        istd = 1.0 / torch.tensor(vae.config.latents_std).view(1, -1, 1, 1, 1).to(dev, torch.float16)
        masked_lat = (vae.encode(img * (1 - m3)).latent_dist.mode() - mean) * istd
        mask_lat = (vae.encode(2 * m3 - 1.0).latent_dist.mode() - mean) * istd
        p.scheduler.set_timesteps(steps, device=dev)
        g = torch.Generator(device=dev).manual_seed(seed)
        lat = torch.randn((1, 16, (n - 1) // p.vae_scale_factor_temporal + 1,
                           fh // p.vae_scale_factor_spatial, fw // p.vae_scale_factor_spatial),
                          generator=g, device=dev, dtype=torch.float16)
        for t in p.scheduler.timesteps:
            inp = torch.cat([lat.to(torch.float16), masked_lat, mask_lat], dim=1)
            noise = p.transformer(hidden_states=inp.half(), timestep=t.expand(1))[0]
            lat = p.scheduler.step(noise, t, lat, return_dict=False)[0]
        if self.tae is not None:  # tiny decoder: works on the model's own latents, gives [0, 1]
            video = self.tae.decode_video(lat.half().permute(0, 2, 1, 3, 4), parallel=n <= 49,
                                          show_progress_bar=False)[0, :n]  # n,3,h,w
            out = (video.permute(0, 2, 3, 1).float().clamp(0, 1) * 255 + 0.5).byte()
        else:
            lat = lat.half() / istd + mean
            video = vae.decode(lat, return_dict=False)[0]  # 1,3,n,h,w in [-1, 1]
            out = ((video[0].permute(1, 2, 3, 0).float().clamp(-1, 1) + 1) * 127.5 + 0.5).byte()
        out = out.flip(-1).cpu().numpy()  # n,h,w,3 BGR
        return [np.ascontiguousarray(o) for o in out]

    def close(self):
        del self.pipe
        if DEVICE == "cuda":
            torch.cuda.empty_cache()


SR_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
SR_WEIGHTS = os.environ.get("KOP_SR", "/content/repos/realesr-general-x4v3.pth")
SHARPEN = os.environ.get("KOP_SHARPEN", "0") == "1"  # off: it sharpened the painting's flaws too


class _SRNet(torch.nn.Module):
    """Real-ESRGAN 'general x4 v3' (compact): restores detail in an upscaled picture."""

    def __init__(self, feat=64, conv=32, up=4):
        super().__init__()
        layers = [torch.nn.Conv2d(3, feat, 3, 1, 1), torch.nn.PReLU(feat)]
        for _ in range(conv):
            layers += [torch.nn.Conv2d(feat, feat, 3, 1, 1), torch.nn.PReLU(feat)]
        layers.append(torch.nn.Conv2d(feat, 3 * up * up, 3, 1, 1))
        self.body = torch.nn.ModuleList(layers)
        self.ps = torch.nn.PixelShuffle(up)
        self.up = up

    def forward(self, x):
        o = x
        for layer in self.body:
            o = layer(o)
        return self.ps(o) + torch.nn.functional.interpolate(x, scale_factor=self.up, mode="nearest")


class Sharpener:
    """Brings the painted background (made at a smaller size for speed) up to the video's full
    size with real detail instead of a blurry enlargement."""

    def __init__(self, path=SR_WEIGHTS):
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            subprocess.run(["wget", "-q", "-O", path + ".part", SR_URL], check=True)
            os.replace(path + ".part", path)
        sd = torch.load(path, map_location="cpu")
        sd = sd.get("params", sd.get("params_ema", sd))
        self.net = _SRNet()
        self.net.load_state_dict(sd)
        self.net = self.net.to(DEVICE).half().eval()

    @torch.no_grad()
    def __call__(self, patches, size, batch=8):
        """patches: BGR uint8 frames (all the same size); size: (w, h) wanted. Returns BGR."""
        W, H = size
        out = []
        for i in range(0, len(patches), batch):
            x = torch.from_numpy(np.ascontiguousarray(np.stack(patches[i:i + batch])[..., ::-1]))
            x = x.to(DEVICE).permute(0, 3, 1, 2).half() / 255.0
            y = self.net(x).clamp_(0, 1).float()
            y = torch.nn.functional.interpolate(y, size=(H, W), mode="bilinear", antialias=True,
                                                align_corners=False)
            y = (y * 255 + 0.5).clamp_(0, 255).byte().permute(0, 2, 3, 1).cpu().numpy()
            out += [np.ascontiguousarray(f[..., ::-1]) for f in y]
        return out


_SHARP = {}


def sharpener():
    """Loaded once; None when switched off or not available (then plain enlargement)."""
    if not SHARPEN or DEVICE != "cuda":
        return None
    if "s" not in _SHARP:
        try:
            _SHARP["s"] = Sharpener()
        except Exception:
            traceback.print_exc()
            _SHARP["s"] = None
    return _SHARP["s"]


# ---------------------------------------------------------------- film quality (SVOR)
DEBUG_DIR = os.environ.get("KOP_DEBUG_DIR", "")  # developer: pictures of each blending step
DEBUG_FRAMES = {int(v) for v in os.environ.get("KOP_DEBUG_FRAMES", "").split(",") if v.strip()}
SVOR_CODE = os.environ.get("KOP_SVOR_CODE", "/content/repos/SVOR")
SVOR_BASE = os.environ.get("KOP_SVOR_BASE", "/content/repos/Wan2.1-VACE-1.3B")
SVOR_PROMPT_CACHE = os.environ.get("KOP_SVOR_PROMPT", "/content/repos/svor_prompt.pt")
SVOR_PROMPT = "Remove the target and fill the content appropriately"
SVOR_NEGATIVE = '色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走'  # (as in predict_SVOR.py)
SVOR_STEPS = int(os.environ.get("KOP_SVOR_STEPS", "12"))  # 12 looked as good as 20 (measured)
SVOR_GUIDANCE = float(os.environ.get("KOP_SVOR_GUIDANCE", "6.0"))
SVOR_CFG_SHARE = float(os.environ.get("KOP_SVOR_CFG_SHARE", "0.4"))  # guidance on the first 40% of steps: same picture, 1.34x faster (measured)


class _Embeds(list):
    """Prompt embeddings in the list form the SVOR pipeline expects (it reads .shape[0])."""
    shape = (1,)


class _DtypeOnly(torch.nn.Module):
    """Stands in for the 11 GB text encoder: the prompt is always the same, so its result is
    computed once and kept on disk."""

    def __init__(self, dtype):
        super().__init__()
        self.p = torch.nn.Parameter(torch.zeros(1, dtype=dtype), requires_grad=False)

    @property
    def dtype(self):
        return self.p.dtype

    @property
    def device(self):
        return self.p.device


def svor_prompt_embeds(dtype=torch.bfloat16):
    """(positive, negative) prompt embeddings; computed once with the text encoder."""
    if os.path.exists(SVOR_PROMPT_CACHE):
        d = torch.load(SVOR_PROMPT_CACHE, map_location="cpu")
        return d["pos"].to(dtype), d["neg"].to(dtype)
    if SVOR_CODE not in sys.path:
        sys.path.insert(0, SVOR_CODE)
    from omegaconf import OmegaConf
    from transformers import AutoTokenizer
    from videox_fun.models import WanT5EncoderModel
    cfg = OmegaConf.load(os.path.join(SVOR_CODE, "config/wan2.1/wan_civitai.yaml"))
    tk = cfg["text_encoder_kwargs"]
    tok = AutoTokenizer.from_pretrained(os.path.join(SVOR_BASE, tk.get("tokenizer_subpath")))
    te = WanT5EncoderModel.from_pretrained(os.path.join(SVOR_BASE, tk.get("text_encoder_subpath")),
                                           additional_kwargs=OmegaConf.to_container(tk))
    te = te.to("cuda", dtype).eval()
    out = []
    with torch.no_grad():
        for text in (SVOR_PROMPT, SVOR_NEGATIVE):
            ti = tok([text], padding="max_length", max_length=512, truncation=True,
                     add_special_tokens=True, return_tensors="pt")
            n = int(ti.attention_mask.gt(0).sum())
            e = te(ti.input_ids.to("cuda"), attention_mask=ti.attention_mask.to("cuda"))[0]
            out.append(e[0, :n].to("cpu", dtype).clone())
    del te
    torch.cuda.empty_cache()
    torch.save({"pos": out[0], "neg": out[1]}, SVOR_PROMPT_CACHE)
    return out[0], out[1]


def ensure_svor():
    """The film engine is downloaded in the background after the app opens; wait for it (or
    download it now if nobody started it). One download at a time (file lock)."""
    root = os.path.dirname(SVOR_CODE)
    os.makedirs(root, exist_ok=True)
    ready = os.path.join(root, ".svor_ready")
    if os.path.exists(ready):
        return
    log("  waiting for the film quality engine to finish downloading ...")
    with open(os.path.join(root, ".svor_setup.lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            if not os.path.exists(ready):
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "setup_svor.sh")
                subprocess.run(["bash", script], check=True, stdout=subprocess.DEVNULL)
                open(ready, "w").close()
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


class SVORFiller:
    """Film quality: SVOR (Wan2.1-VACE 1.3B + Xiaomi's removal LoRAs, CVPR 2026 winner).
    Also removes the shadows and reflections people leave, and copes with imperfect masks."""

    def __init__(self, steps=SVOR_STEPS, guidance=SVOR_GUIDANCE):
        if os.path.isdir("/content"):
            ensure_svor()
        if SVOR_CODE not in sys.path:
            sys.path.insert(0, SVOR_CODE)
        from diffusers import FlowMatchEulerDiscreteScheduler
        from omegaconf import OmegaConf
        from videox_fun.models import AutoencoderKLWan, VaceWanModel
        from videox_fun.pipeline import SVORPipeline
        from videox_fun.utils.lora_utils import merge_lora
        from videox_fun.utils.utils import filter_kwargs
        dt = torch.bfloat16
        pos, neg = svor_prompt_embeds(dt)
        cfg = OmegaConf.load(os.path.join(SVOR_CODE, "config/wan2.1/wan_civitai.yaml"))
        tr = VaceWanModel.from_pretrained(
            os.path.join(SVOR_BASE, cfg["transformer_additional_kwargs"].get("transformer_subpath", "./")),
            transformer_additional_kwargs=OmegaConf.to_container(cfg["transformer_additional_kwargs"]),
            low_cpu_mem_usage=True, torch_dtype=dt)
        vae = AutoencoderKLWan.from_pretrained(
            os.path.join(SVOR_BASE, cfg["vae_kwargs"].get("vae_subpath", "vae")),
            additional_kwargs=OmegaConf.to_container(cfg["vae_kwargs"])).to(dt)
        sch = FlowMatchEulerDiscreteScheduler(
            **filter_kwargs(FlowMatchEulerDiscreteScheduler, OmegaConf.to_container(cfg["scheduler_kwargs"])))
        pipe = SVORPipeline(transformer=tr, vae=vae, tokenizer=None, text_encoder=_DtypeOnly(dt),
                            scheduler=sch)
        loras = [os.path.join(SVOR_CODE, "models", f"remove_model_stage{k}.safetensors") for k in (1, 2)]
        if not all(os.path.exists(f) for f in loras):
            loras = sorted(glob.glob(os.path.join(SVOR_CODE, "models", "*.safetensors")))
        for f in loras:
            pipe = merge_lora(pipe, f, 1.0, transformer_only=True)
        self.pipe = pipe.to("cuda")
        self.pos, self.neg = pos.to("cuda"), neg.to("cuda")
        self.steps, self.guidance = steps, guidance
        self.tae = None

    def use_tae(self, on=True):  # (the tiny decoder is for the quick levels only)
        self.tae = None

    @torch.no_grad()
    def fill(self, imgs, masks, fw, fh, dil=6, seed=43, steps=None):
        """imgs: BGR frames, masks: bool arrays; len 4k+1 (<= 81). Returns BGR frames (fw x fh)."""
        n = len(imgs)
        k = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        x = np.stack([cv2.cvtColor(cv2.resize(im, (fw, fh), interpolation=cv2.INTER_AREA),
                                   cv2.COLOR_BGR2RGB) for im in imgs]).astype(np.float32)
        m = np.stack([cv2.resize(cv2.dilate(mk.view(np.uint8), k, iterations=dil).astype(np.float32),
                                 (fw, fh), interpolation=cv2.INTER_LINEAR) for mk in masks])
        m = (m >= 0.5).astype(np.float32)
        x = x * (1 - m[..., None]) + 128.0 * m[..., None]
        video = torch.from_numpy(x).permute(3, 0, 1, 2)[None] / 127.5 - 1.0  # 1,3,n,h,w
        mask = torch.from_numpy(m)[None, None]  # 1,1,n,h,w
        cfg = self.guidance > 1.0
        if SVOR_CFG_SHARE < 1.0 and cfg:
            with _gpu_lock(_LOCK_ST[0]):
                try:
                    out = self._loop(video, mask, fh, fw, steps or self.steps, seed)
                finally:
                    if WORKER:
                        torch.cuda.empty_cache()
            out = out[0].permute(1, 2, 3, 0).float().clamp(0, 1).cpu().numpy()
            return [cv2.cvtColor((o * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR) for o in out[:n]]
        with _gpu_lock(_LOCK_ST[0]):
            try:
                out = self.pipe(
                    None, height=fh, width=fw, video=video, mask_video=mask,
                    num_inference_steps=steps or self.steps, guidance_scale=self.guidance,
                    generator=torch.Generator(device="cuda").manual_seed(seed),
                    prompt_embeds=_Embeds([self.pos]),
                    negative_prompt_embeds=_Embeds([self.neg]) if cfg else None,
                    context_scale=1.0).videos
            finally:
                if WORKER:
                    torch.cuda.empty_cache()
        out = out[0].permute(1, 2, 3, 0).float().clamp(0, 1).numpy()  # n,h,w,3 RGB
        return [cv2.cvtColor((o * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR) for o in out[:n]]

    @torch.no_grad()
    def _loop(self, video, mask, fh, fw, steps, seed):
        """The SVOR pipeline's denoising, but the guidance (two model passes per step) only in
        the first SVOR_CFG_SHARE of the steps - they decide what fills the gap; the later steps
        only refine detail and run once."""
        p = self.pipe
        dev, dt = "cuda", torch.bfloat16
        sch = p.scheduler
        sch.set_timesteps(steps, device=dev, mu=1)
        ts = sch.timesteps
        video = video.to(dev, dt)
        mask = mask.to(dev, dt)
        z0 = p.vace_encode_frames(video, None, masks=mask)
        m0 = p.vace_encode_masks(mask, None)
        z = p.vace_latent(z0, m0).to(dev, dt)
        shape = list(z0.shape)
        shape[1] = shape[1] // 2
        g = torch.Generator(device=dev).manual_seed(seed)
        lat = torch.randn(shape, generator=g, device=dev, dtype=dt)
        tr = p.transformer
        seq_len = math.ceil((shape[3] * shape[4]) / (tr.config.patch_size[1] * tr.config.patch_size[2])
                            * shape[2])
        z2 = torch.cat([z] * 2)
        n_cfg = max(1, int(round(steps * SVOR_CFG_SHARE)))
        for i, t in enumerate(ts):
            with torch.autocast("cuda", dtype=dt):
                if i < n_cfg:
                    out = tr(x=torch.cat([lat] * 2), context=[self.neg, self.pos], t=t.expand(2),
                             seq_len=seq_len, vace_context=z2, vace_context_scale=1.0)
                    un, co = out.chunk(2)
                    noise = un + self.guidance * (co - un)
                else:
                    noise = tr(x=lat, context=[self.pos], t=t.expand(1), seq_len=seq_len,
                               vace_context=z, vace_context_scale=1.0)
            lat = sch.step(noise, t, lat, return_dict=False)[0]
        frames = p.vae.decode(lat.to(p.vae.dtype)).sample
        return (frames / 2 + 0.5).clamp(0, 1)

    def close(self):
        del self.pipe
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


def figure_judge(det_weights, conf=0.35, every=6, inside=0.5):
    """Returns judge(painted_frames, masks) -> how many person-like figures the painter made
    inside the removed areas (looked at every `every`-th frame)."""
    det = _detector(det_weights)

    def judge(out, masks):
        idx = list(range(0, len(out), every))
        res = det.predict([out[i] for i in idx], classes=[0], conf=conf, imgsz=640, verbose=False,
                          device=0 if DEVICE == "cuda" else "cpu",
                          quantize=16 if DEVICE == "cuda" else None)
        n = 0
        for i, r in zip(idx, res):
            fh, fw = out[i].shape[:2]
            m = cv2.resize(masks[i].view(np.uint8), (fw, fh), interpolation=cv2.INTER_NEAREST)
            for b in r.boxes.xyxy.cpu().numpy().astype(int):
                x1, y1, x2, y2 = max(0, b[0]), max(0, b[1]), min(fw, b[2]), min(fh, b[3])
                if x2 > x1 and y2 > y1 and m[y1:y2, x1:x2].mean() >= inside:
                    n += 1
        return n
    return judge


def fill_realistic(frames, final_dir, flags, work, ranges, w, h, filler, window=49, overlap=8,
                   stages=None, seed=42, reuse=None, changed=None, steps=None, stride=1,
                   prot_dir=None, refine=None, band=0.06, judge=None, retries=2):
    """Same output format as inpaint(): (chunks, {chunk: (folder, extension)}); the folder
    holds full-size frames with the removed areas filled in."""
    chs = plan_chunks(ranges, window, overlap)
    todo = [c for c, (a, b, _, _) in enumerate(chs) if any(flags[i] for i in range(a, b))]
    results = {}
    if reuse and reuse[0] == chs and changed is not None:  # only repaint what changed
        keep = [c for c in todo if c in reuse[1] and not any(i in changed for i in range(*chs[c][:2]))]
        results.update({c: reuse[1][c] for c in keep})
        todo = [c for c in todo if c not in keep]
    def painted(a, b):  # the frames given to the model (every `stride`-th, ends included)
        sub = list(range(a, b))[::stride]
        if sub[-1] != b - 1:
            sub.append(b - 1)
        return sub

    def load(c):
        a, b, _, _ = chs[c]
        ext = _pad_4k1(painted(a, b))
        prots = ([_read_mask(prot_dir, g) if os.path.exists(_mpath(prot_dir, g)) else None
                  for g in ext] if (refine is not None and prot_dir) else None)
        return ([cv2.imread(frames[g]) for g in ext], [_read_mask(final_dir, g) for g in ext],
                prots)

    def refine_band(out, imgs, masks, prots, box, fw, fh):
        """The film painter also fades out people it was not asked to remove when they stand
        next to removed ones; around the kept person the background is therefore painted
        again by a painter that keeps everything outside its mask (no halos)."""
        x1, y1, x2, y2 = box
        cw, ch = x2 - x1, y2 - y1
        r = max(5, int(band * max(w, h)))
        k = np.ones((r, r), np.uint8)
        bands = []
        for m, p in zip(masks, prots):
            mc = m[y1:y2, x1:x2]
            if p is None or not p.any():
                bands.append(np.zeros_like(mc))
                continue
            bands.append(mc & (cv2.dilate(p[y1:y2, x1:x2].view(np.uint8), k) > 0))
        if sum(int(bb.sum()) for bb in bands) < 200:
            return out
        mixed = []
        for o, im, m in zip(out, imgs, masks):
            up = cv2.resize(o, (cw, ch), interpolation=cv2.INTER_LINEAR)
            src = im[y1:y2, x1:x2].copy()
            mc = m[y1:y2, x1:x2]
            src[mc] = up[mc]
            mixed.append(src)
        ref = refine.fill(mixed, bands, fw, fh, seed=seed, steps=8)
        res = []
        for o, rf, bb in zip(out, ref, bands):
            a = cv2.resize(bb.astype(np.float32), (fw, fh), interpolation=cv2.INTER_AREA)
            a = cv2.GaussianBlur(a, (0, 0), 2.0)
            a = np.clip(a * 1.5, 0, 1)[..., None]
            res.append(np.clip(o * (1 - a) + rf * a + 0.5, 0, 255).astype(np.uint8))
        return res

    def save(path, img, patch, box):
        x1, y1, x2, y2 = box
        img = img.copy()
        if patch.shape[:2] != (y2 - y1, x2 - x1):
            patch = cv2.resize(patch, (x2 - x1, y2 - y1), interpolation=cv2.INTER_LANCZOS4)
        img[y1:y2, x1:x2] = patch
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])

    def between(path, g, k, t, sub, imgs, masks, out, box, fw, fh):
        """Frame g between painted frames sub[k] and sub[k+1]: both paintings are moved with
        the camera to frame g, then cross-faded (blending without moving them smears)."""
        base = cv2.imread(frames[g])
        mg = _read_mask(final_dir, g)
        x1, y1, x2, y2 = box
        P = np.array([[fw / (x2 - x1), 0, -x1 * fw / (x2 - x1)],
                      [0, fh / (y2 - y1), -y1 * fh / (y2 - y1)], [0, 0, 1]])
        Pi = np.linalg.inv(P)
        warped = []
        for kk in (k, k + 1):
            H = camera_motion(imgs[kk], base, masks[kk], mg)
            o = out[kk]
            if H is not None:
                o = cv2.warpPerspective(o, P @ H @ Pi, (fw, fh), flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_REPLICATE)
            warped.append(o)
        save(path, base, cv2.addWeighted(warped[0], 1 - t, warped[1], t, 0), box)

    writes = []
    nxt = _IO.submit(load, todo[0]) if todo else None
    for t, c in enumerate(todo):
        a, b, _, _ = chs[c]
        imgs, masks, prots = nxt.result()
        nxt = _IO.submit(load, todo[t + 1]) if t + 1 < len(todo) else None
        x1, y1, x2, y2 = crop_box(masks, w, h)
        fw, fh = fill_size(x2 - x1, y2 - y1)
        crops, cms = [im[y1:y2, x1:x2] for im in imgs], [m[y1:y2, x1:x2] for m in masks]
        out = filler.fill(crops, cms, fw, fh, seed=seed, steps=steps)
        if judge is not None:  # film: figures painted into the gap? paint again, keep the best
            try:
                bad = judge(out, cms)
                for k in range(retries):
                    if bad == 0:
                        break
                    alt = filler.fill(crops, cms, fw, fh, seed=seed + 101 * (k + 1), steps=steps)
                    nb = judge(alt, cms)
                    log(f"  piece {c}: {bad} painted figure(s) -> repainted: {nb}")
                    if nb < bad:
                        out, bad = alt, nb
            except torch.cuda.OutOfMemoryError:
                raise
            except Exception:
                traceback.print_exc()
        if refine is not None and prots is not None:
            try:
                out = refine_band(out, imgs, masks, prots, (x1, y1, x2, y2), fw, fh)
            except torch.cuda.OutOfMemoryError:
                raise
            except Exception:
                traceback.print_exc()
        sh = sharpener() if (x2 - x1) > 1.25 * fw else None
        if sh is not None:  # full-size detail instead of a blurry enlargement
            out = sh(out, (x2 - x1, y2 - y1))
        d = os.path.join(work, "mm_out", f"c{c:04d}_s{seed}")
        os.makedirs(d, exist_ok=True)
        sub = painted(a, b)
        pos = {g: k for k, g in enumerate(sub)}
        for j, g in enumerate(range(a, b)):
            path = os.path.join(d, f"{j:04d}.jpg")
            if g in pos:
                writes.append(_IO.submit(save, path, imgs[pos[g]], out[pos[g]], (x1, y1, x2, y2)))
            else:  # between two painted frames
                k = max(k for k, x in enumerate(sub) if x < g)
                t = (g - sub[k]) / (sub[k + 1] - sub[k])
                writes.append(_IO.submit(between, path, g, k, t, sub, imgs, masks, out,
                                         (x1, y1, x2, y2), fw, fh))
        results[c] = (d, ".jpg")
        if stages:
            stages.step(t + 1, len(todo))
    for f in writes:
        f.result()
    return chs, results


def camera_motion(a_img, b_img, a_mask, b_mask, size=480):
    """How the picture moves from frame a to frame b (3x3, in full-size pixels), measured on
    the background only (people masked out). None when it cannot be measured reliably."""
    h, w = a_img.shape[:2]
    s = size / max(h, w)
    sw, sh = max(8, int(round(w * s))), max(8, int(round(h * s)))
    ga = cv2.cvtColor(cv2.resize(a_img, (sw, sh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b_img, (sw, sh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    busy = cv2.resize((a_mask | b_mask).view(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST)
    free = cv2.erode((1 - busy).astype(np.uint8), np.ones((5, 5), np.uint8))
    pts = cv2.goodFeaturesToTrack(ga, 400, 0.01, 6, mask=free)
    if pts is None or len(pts) < 12:
        return None
    nb, ok, _ = cv2.calcOpticalFlowPyrLK(ga, gb, pts, None, winSize=(21, 21), maxLevel=3)
    ok = ok.ravel() == 1
    if ok.sum() < 12:
        return None
    H, inl = cv2.findHomography(pts[ok], nb[ok], cv2.RANSAC, 2.0)
    if H is None or inl is None or inl.sum() < 10:
        return None
    S = np.diag([s, s, 1.0])
    return np.linalg.inv(S) @ H @ S


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
    """The painted frame g (uint8); where two painted pieces overlap they are cross-faded."""
    imgs, wts = [], []
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
            img = np.asarray(ext)
            if img.dtype != np.uint8:
                img = np.clip(img + 0.5, 0, 255).astype(np.uint8)
        else:
            img = cv2.imread(os.path.join(folder, f"{g - a:04d}{ext}"))
            if (img.shape[1], img.shape[0]) != tuple(size):
                img = cv2.resize(img, size, interpolation=cv2.INTER_LANCZOS4)
        imgs.append(img)
        wts.append(wgt)
    if len(imgs) == 1:
        return imgs[0]
    out, tot = imgs[0], wts[0]
    for img, wgt in zip(imgs[1:], wts[1:]):
        out = cv2.addWeighted(out, tot / (tot + wgt), img, wgt / (tot + wgt), 0)
        tot += wgt
    return out


class CameraPath:
    """Camera movement between neighbouring frames of each scene piece (measured on the
    background only), so any frame of a shot can be laid over any other."""

    def __init__(self, frames, final_dir, prot_dir, ranges, threads=6):
        self.frames, self.final, self.prot = frames, final_dir, prot_dir
        self.unit = {}
        jobs = []
        for r, (a, b) in enumerate(ranges):
            for i in range(a, b):
                self.unit[i] = r
            jobs += [(i, i + 1) for i in range(a, b - 1)]
        self.step = {}
        self._cache = {}
        self._lock = __import__("threading").Lock()

        def measure(ij):
            i, j = ij
            return ij, camera_motion(self.img(i), self.img(j), self.busy(i), self.busy(j))
        with ThreadPoolExecutor(threads) as ex:
            for (i, j), H in ex.map(measure, jobs):
                self.step[i] = H
        self._cache.clear()

    def _get(self, key, make, keep=160):
        with self._lock:
            v = self._cache.get(key)
        if v is None:
            v = make()
            with self._lock:
                if len(self._cache) > keep:
                    for k in list(self._cache)[:keep // 4]:
                        del self._cache[k]
                self._cache[key] = v
        return v

    def img(self, i):
        return self._get(("i", i), lambda: cv2.imread(self.frames[i]))

    def busy(self, i):
        def make():
            m = _read_mask(self.final, i)
            if os.path.exists(_mpath(self.prot, i)):
                m = m | _read_mask(self.prot, i)
            return m
        return self._get(("b", i), make)

    def between(self, j, g):
        """3x3 that moves frame j onto frame g, or None (other scene, or not measurable)."""
        if self.unit.get(j) != self.unit.get(g):
            return None
        H = np.eye(3)
        if j < g:
            for i in range(j, g):
                if self.step.get(i) is None:
                    return None
                H = self.step[i] @ H
        else:  # j -> j-1 -> ... -> g
            for i in range(j - 1, g - 1, -1):
                if self.step.get(i) is None:
                    return None
                H = np.linalg.inv(self.step[i]) @ H
        return H


def real_fill(path, g, orig, hole, painted, prot, gate=True, reach=36, step=4, tol=20, give_up=6):
    """Puts real background into the removed area where it can be seen in other frames of
    the shot (moved along with the camera). Only pixels that were free of people there, that
    line up with this frame around the area, and (gate) agree with the painting in their
    overall colour are used - so no misplaced shadows or ghosts. Works on the removed area's
    box only. Returns (frame, share of the area filled with real background)."""
    h, w = hole.shape
    need_full = hole & ~prot
    if need_full.sum() < 50:
        return painted, 0.0
    x1, y1, x2, y2 = (int(v) for v in _bbox(need_full))
    pd = 24
    x1, y1, x2, y2 = max(0, x1 - pd), max(0, y1 - pd), min(w, x2 + pd), min(h, y2 + pd)
    cw, ch = x2 - x1, y2 - y1
    T = np.array([[1, 0, -x1], [0, 1, -y1], [0, 0, 1]], np.float64)
    need = need_full[y1:y2, x1:x2]
    hl, pr = hole[y1:y2, x1:x2], prot[y1:y2, x1:x2]
    o = orig[y1:y2, x1:x2]
    pc = painted[y1:y2, x1:x2]
    total = int(need.sum())
    ring_src = (cv2.dilate(hl.view(np.uint8), np.ones((25, 25), np.uint8)) > 0) & ~hl & ~pr
    sm = (max(8, cw // 4), max(8, ch // 4))  # colour agreement is judged at 1/4 size
    p_small = cv2.GaussianBlur(cv2.resize(pc, sm, interpolation=cv2.INTER_AREA), (0, 0), 1.0).astype(np.int16)
    out = pc.copy()
    taken = np.zeros_like(need)
    order = sorted((j for d in range(step, reach + 1, step) for j in (g - d, g + d)),
                   key=lambda j: abs(j - g))
    tried = 0
    for j in order:
        H = path.between(j, g)
        if H is None:
            continue
        tried += 1
        if tried > give_up and not taken.any():
            break  # nothing usable nearby: this frame is painted only
        Hc = T @ H
        wj = cv2.warpPerspective(path.img(j), Hc, (cw, ch), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT)
        free = cv2.warpPerspective((~path.busy(j)).view(np.uint8), Hc, (cw, ch),
                                   flags=cv2.INTER_NEAREST, borderValue=0)
        free = cv2.erode(free, np.ones((5, 5), np.uint8)) > 0
        take = need & free & ~taken
        if take.sum() < 20:
            continue
        ring = ring_src & free
        if ring.sum() < 300:
            continue
        d = np.abs(wj.astype(np.int16) - o)[ring].max(1)
        if np.median(d) > 14:  # does not line up (parallax, lighting change)
            continue
        gain = np.clip((o[ring].mean(0) + 1) / (wj[ring].mean(0) + 1), 0.8, 1.25)
        wj = np.clip(wj * gain + 0.5, 0, 255).astype(np.uint8)
        if gate:
            w_small = cv2.GaussianBlur(cv2.resize(wj, sm, interpolation=cv2.INTER_AREA), (0, 0), 1.0)
            agree = (np.abs(w_small.astype(np.int16) - p_small).max(2) < tol).view(np.uint8)
            take &= cv2.resize(agree, (cw, ch), interpolation=cv2.INTER_NEAREST) > 0
        if take.any():
            out[take] = wj[take]
            taken |= take
        if (need & ~taken).sum() < 50:
            break
    if not taken.any():
        return painted, 0.0
    a = cv2.GaussianBlur(taken.astype(np.float32), (0, 0), 1.5)[..., None]  # soft seam
    res = painted.copy()
    res[y1:y2, x1:x2] = np.clip(out.astype(np.float32) * a + pc.astype(np.float32) * (1 - a) + 0.5,
                                0, 255).astype(np.uint8)
    return res, float(taken.sum()) / total


def guided_alpha(img, mask, r=4, eps=1e-3):
    """Soft edge of a mask that follows the picture's own edges (guided filter, He et al.):
    hair and motion-blurred outlines get partial values instead of a hard cut."""
    I = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    p = mask.astype(np.float32)
    k = (2 * r + 1, 2 * r + 1)
    mI, mp = cv2.boxFilter(I, -1, k), cv2.boxFilter(p, -1, k)
    cIp = cv2.boxFilter(I * p, -1, k) - mI * mp
    vI = cv2.boxFilter(I * I, -1, k) - mI * mI
    a = cIp / (vI + eps)
    b = mp - a * mI
    q = cv2.boxFilter(a, -1, k) * I + cv2.boxFilter(b, -1, k)
    return np.clip(q, 0.0, 1.0)


def match_grain(f, o, region, ring, rng):
    """Adds the video's own fine noise/grain to the painted area (painted pixels are cleaner
    than real footage, which gives them away)."""
    if ring.sum() < 200 or region.sum() < 50:
        return f
    go = cv2.cvtColor(o, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gf = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    so = float((go - cv2.GaussianBlur(go, (0, 0), 1.2))[ring].std())
    sf = float((gf - cv2.GaussianBlur(gf, (0, 0), 1.2))[region].std())
    add = (max(0.0, so * so - sf * sf)) ** 0.5
    if add < 0.6:
        return f
    nz = cv2.GaussianBlur(rng.standard_normal(f.shape[:2]).astype(np.float32), (0, 0), 0.6)
    nz *= add / max(1e-3, float(nz.std()))
    out = f.astype(np.float32)
    out[region] += nz[region][:, None]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def composite(frames, final_dir, prot_dir, flags, chs, results, out_mp4, fps, lo, hi, w, h,
              overlap=16, feather_px=9, stages=None, film=None):
    """Final frames of the part: the painted background blended in where people were removed.
    Several frames are prepared at once in threads (OpenCV releases the GIL); written in order.
    film: {"ranges": scene pieces, "gate": bool, "effects": bool} - real background from other
    frames, the painter's shadow/reflection removal outside the masks, matched grain."""
    path = None
    share, miss = [], {}  # miss: scene piece -> frames in a row without usable real background
    if film:
        try:
            path = CameraPath(frames, final_dir, prot_dir, film["ranges"])
        except Exception:
            traceback.print_exc()

    def make(g):
        orig = cv2.imread(frames[g])
        if not flags.get(g):
            return orig
        # blend only around the removed area (fast), matching the frame's brightness
        inp = _inpainted_frame(g, chs, results, overlap, (w, h))
        mb = _read_mask(final_dir, g)
        if not mb.any():
            return orig
        dbg = DEBUG_DIR and g in DEBUG_FRAMES
        if dbg:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            cv2.imwrite(os.path.join(DEBUG_DIR, f"{g:06d}_a_painted.jpg"), inp)
            vis = orig.copy()
            vis[mb] = (0.5 * vis[mb] + [0, 0, 127]).astype(np.uint8)
            cv2.imwrite(os.path.join(DEBUG_DIR, f"{g:06d}_b_mask.jpg"), vis)
        u = path.unit.get(g) if path is not None else None
        if path is not None and not (miss.get(u, 0) >= 3 and g % 8):
            try:
                prot_full = _read_mask(prot_dir, g)
                inp, got = real_fill(path, g, orig, mb, inp, prot_full, gate=film.get("gate", True))
                share.append(got)
                miss[u] = 0 if got > 0.01 else miss.get(u, 0) + 1
            except Exception:
                traceback.print_exc()
        if film and film.get("effects"):  # shadows/reflections the painter removed next to people
            q = 4  # judged at 1/4 size
            sw_, sh_ = w // q, h // q
            r = max(3, int(0.06 * max(w, h)) // q)
            near = cv2.dilate(cv2.resize(mb.view(np.uint8), (sw_, sh_), interpolation=cv2.INTER_NEAREST),
                              np.ones((r, r), np.uint8)) > 0
            dd = np.abs(cv2.resize(inp, (sw_, sh_), interpolation=cv2.INTER_AREA).astype(np.int16) -
                        cv2.resize(orig, (sw_, sh_), interpolation=cv2.INTER_AREA)).max(2).astype(np.float32)
            dd = cv2.GaussianBlur(dd, (0, 0), 1.0)
            eff = ((dd > 21.0) & near).view(np.uint8)
            if eff.any():
                eff = cv2.resize(eff, (w, h), interpolation=cv2.INTER_NEAREST) > 0
                mb = mb | (eff & ~_read_mask(prot_dir, g))
        x1, y1, x2, y2 = (int(v) for v in _bbox(mb))
        pd = 4 * feather_px + 2
        x1, y1, x2, y2 = max(0, x1 - pd), max(0, y1 - pd), min(w, x2 + pd), min(h, y2 + pd)
        mm = mb[y1:y2, x1:x2]
        m8 = mm.view(np.uint8)
        if feather_px > 0:  # soft edge outside the removed area, computed at 1/4 size
            sh_, sw_ = max(1, (y2 - y1) // 4), max(1, (x2 - x1) // 4)
            sm = cv2.resize(m8.astype(np.float32), (sw_, sh_), interpolation=cv2.INTER_AREA)
            sm = cv2.GaussianBlur(sm, (0, 0), feather_px / 4)
            a = cv2.resize(sm, (x2 - x1, y2 - y1), interpolation=cv2.INTER_LINEAR)
            a = cv2.max(a, m8.astype(np.float32))
        else:
            a = m8.astype(np.float32)
        pr = _read_mask(prot_dir, g)[y1:y2, x1:x2]
        if film and pr.any():  # soft, picture-guided edge of the kept person (no fringe)
            keep = guided_alpha(orig[y1:y2, x1:x2], pr)
            keep = np.where(cv2.erode(pr.view(np.uint8), np.ones((5, 5), np.uint8)) > 0, 1.0, keep)
            keep *= cv2.dilate(pr.view(np.uint8), np.ones((5, 5), np.uint8)) > 0  # at most 2 px out
            a *= (1.0 - keep)
        else:
            a[pr] = 0.0
        o = orig[y1:y2, x1:x2]
        f = inp[y1:y2, x1:x2]
        ring = cv2.dilate(m8, np.ones((9, 9), np.uint8)) & ~m8 & ~pr.view(np.uint8)
        if cv2.countNonZero(ring) > 50:
            mo, mf = cv2.mean(o, mask=ring)[:3], cv2.mean(f, mask=ring)[:3]
            gain = np.clip((np.array(mo) + 1) / (np.array(mf) + 1), 0.85, 1.18)
            if np.abs(gain - 1).max() > 0.004:
                f = cv2.transform(f, np.diag(gain).astype(np.float32))
        if film:
            f = match_grain(f, o, a > 0.5, ring.view(bool), np.random.default_rng(g))
        orig = orig.copy()
        orig[y1:y2, x1:x2] = cv2.blendLinear(f, o, a, 1.0 - a)
        if dbg:
            cv2.imwrite(os.path.join(DEBUG_DIR, f"{g:06d}_c_real.jpg"), inp)
            cv2.imwrite(os.path.join(DEBUG_DIR, f"{g:06d}_d_final.jpg"), orig)
        return orig

    wr = FFWriter(out_mp4, w, h, fps, crf=13, preset="veryfast")
    cpus = os.cpu_count() or 2
    pool = ThreadPoolExecutor(max(1, min(6, cpus // 3)) if film else max(1, min(3, cpus // 4)))
    futs, nxt = {}, lo
    for g in range(lo, hi):
        while nxt < hi and nxt < g + 12:
            futs[nxt] = pool.submit(make, nxt)
            nxt += 1
        orig = futs.pop(g).result()
        wr.write(orig)
        if _PREVIEW is not None and (g - lo) % 12 == 0:
            try:
                _PREVIEW(orig)
            except Exception:
                pass
        if stages:
            stages.step(g - lo + 1, hi - lo)
    pool.shutdown()
    wr.close()
    if share:
        log(f"  real background used for {100 * float(np.mean(share)):.0f}% of the removed area")


# ---------------------------------------------------------------- jobs (saved, resumable)
def _safe_name(src):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(src))[0])[:40]
    return f"{base or 'video'}_{time.strftime('%Y%m%d_%H%M%S')}"


def save_job(st):
    if st.get("_worker"):
        return
    data = {k: v for k, v in st.items() if not k.startswith("_")}
    p = os.path.join(st["job_dir"], JOB_FILE)
    with open(p + ".tmp", "wb") as f:
        pickle.dump(data, f)
    os.replace(p + ".tmp", p)


OUTLINES_FILE = "outlines.pkl"


def _attach(st, cache_root):
    st["cache"] = os.path.join(cache_root, st["name"])
    os.makedirs(st["cache"], exist_ok=True)
    master = os.path.join(st["cache"], "master.mp4")
    if not os.path.exists(master):
        log("Copying the saved master video back from the job folder ...")
        _copy_atomic(os.path.join(st["job_dir"], "master.mp4"), master)
    if st.get("audio") and not os.path.exists(os.path.join(st["cache"], st["audio"])):
        _copy_atomic(os.path.join(st["job_dir"], st["audio"]), os.path.join(st["cache"], st["audio"]))
    st["_video"] = Video(master, st["fps"], st["w"], st["h"], st["cache"])
    st["_unit_of"] = np.zeros(st["n"], np.int32)
    for u, (a, b, _) in enumerate(st["units"]):
        st["_unit_of"][a:b] = u
    st["_tracked"] = {}
    st["_segs"] = None
    op = os.path.join(st["job_dir"], OUTLINES_FILE)
    if os.path.exists(op):
        with open(op, "rb") as f:
            st["_segs"] = pickle.load(f)
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
    TIMINGS.clear()
    S.start(0)
    fps, has_audio, src_dur, _, _ = probe(src)
    master = os.path.join(cache, "master.mp4")
    audio = extract_audio(src, os.path.join(cache, "audio.mka"), start, end) if has_audio else None
    tee = TeeVideo(src, master, fps, start, end)
    dur = max(0.0, (min(end, src_dur) if end else src_dur) - (start or 0))
    S.start(2)  # the master copy is written while the scan reads the same frames
    scores, boxes, segs = scan(tee, cfg["det"], cfg["det_imgsz"], conf,
                               int(round(dur * fps_float(fps))), stages=S,
                               seg_weights=cfg.get("seg"))
    _, _, dur, w, h = probe(master)
    if (w, h) != (tee.w, tee.h):
        raise RuntimeError(f"Master copy size {w}x{h} differs from {tee.w}x{tee.h}.")
    S.start(1)
    _copy_atomic(master, os.path.join(job_dir, "master.mp4"))
    if audio:
        _copy_atomic(audio, os.path.join(job_dir, "audio.mka"))
    if segs is not None:
        with open(os.path.join(job_dir, OUTLINES_FILE), "wb") as f:
            pickle.dump(segs, f)
    n = len(boxes)
    if n == 0:
        raise RuntimeError("No frames decoded - check the start/end times and the video file.")
    shots = shots_from_scores(scores, min_len=max(3, round(0.15 * fps_float(fps))))
    parts = plan_parts(shots, n, max(1, int(round(part_seconds * fps_float(fps)))))
    st = dict(version=3, name=name, job_dir=job_dir, src=os.path.basename(src), start=start,
              end=end, preset=preset, conf=conf, fps=fps, n=n, w=w, h=h,
              audio="audio.mka" if audio else None, shots=shots, parts=parts,
              units=make_units(shots, parts), boxes=boxes, seeds={}, auto=None, grow=GROW,
              created=time.time())
    save_job(st)
    _attach(st, cache_root)
    log(f"{n} frames, {len(shots)} scene(s), {len(parts)} part(s).", 1.0)
    S.done()
    st["prep"] = {k: round(v, 1) for k, v in TIMINGS.items()}
    save_job(st)
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


def _tmp(st, name):
    """Scratch folder of this process (parallel workers must not share them)."""
    return os.path.join(st["cache"], f"{name}_{os.getpid()}")


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
                     _tmp(st, "tmp_track"), lo, hi)
    flush_masks()
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
    one = _tmp(st, "target_one")
    for f, box in seeds:
        shutil.rmtree(one, ignore_errors=True)
        track_target(vid_pred, st["_video"], f, box, one, _tmp(st, "tmp_track"),
                     lo, hi)
        for i in range(lo, hi):
            _write_mask(tgt, i, _read_mask(tgt, i) | _read_mask(one, i))
    shutil.rmtree(one, ignore_errors=True)
    flush_masks()
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
    one = _tmp(st, "target_one")
    for t, (u, f, b) in enumerate(picks):
        lo, hi, _ = st["units"][u]
        st["_video"].ensure(lo, hi)
        shutil.rmtree(one, ignore_errors=True)
        track_target(vid_pred, st["_video"], f, b, one, _tmp(st, "tmp_track"), lo, hi)
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
    st["_video"].extract_many([i for u in todo for i in ReID.sample_frames(*st["units"][u][:2])])
    for t, u in enumerate(todo):
        lo, hi, _ = st["units"][u]
        found = []
        for r in refs:
            res = r.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi,
                                 segs=st.get("_segs"), closeups=False)
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


def mask_removal(img_pred, frames, boxes, tgt_dir, raw_dir, prot_dir, lo, hi, stages=None,
                 segs=None):
    """Remove mode, per frame: the tracked people to remove, completed with their detections;
    every other detected person is protected (never erased)."""
    for d in (raw_dir, prot_dir):
        os.makedirs(d, exist_ok=True)
    seg, nxt = {}, None

    def load(ks):
        return ks, [cv2.imread(frames[k]) for k in ks]

    for i in range(lo, hi):
        if i not in seg:  # the next frames are read from disk while the GPU works
            ks = list(range(i, min(hi, i + SEG_BATCH)))
            imgs = nxt.result()[1] if nxt is not None and nxt.result()[0] == ks else load(ks)[1]
            nk = list(range(ks[-1] + 1, min(hi, ks[-1] + 1 + SEG_BATCH)))
            nxt = _IO.submit(load, nk) if nk else None
            got = _segment(img_pred, frames, boxes, segs, ks, imgs)
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
    flush_masks()


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
        areas = {i: int(_read_mask(tgt, i).sum()) for i in range(lo, hi)}
        good = [i for i in range(lo, hi) if areas[i] >= 400]
        spread = [good[int(round(x))] for x in np.linspace(0, len(good) - 1, min(8, len(good)))]
        largest = sorted(good, key=lambda i: -areas[i])[:4]  # biggest views show the face best
        for i in sorted(set(spread + largest)):
            m = _read_mask(tgt, i)
            reid.add_person(cv2.imread(st["_video"][i]), _bbox(m), m)
        S.step(t + 1, len(user))
    S.start(1)
    auto = {}
    todo = [u for u in range(len(st["units"])) if u not in st["seeds"]]
    st["_video"].extract_many([i for u in todo for i in ReID.sample_frames(*st["units"][u][:2])])
    for t, u in enumerate(todo):
        lo, hi, _ = st["units"][u]
        auto[u] = reid.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi,
                                    segs=st.get("_segs"))
        S.step(t + 1, len(todo))
    # second look: faces of the person found clearly in other scenes (other lighting, make-up,
    # angles) become references too; scenes not settled by a face are searched again
    learned = [r["emb"] for r in auto.values()
               if r and r["how"] == "face" and r["score"] >= 0.5 and r.get("emb") is not None]
    if learned:
        reid.ref_faces.extend(learned[:40])
        again = [u for u in todo if auto[u] is None or auto[u]["how"] != "face"]
        for u in again:
            lo, hi, _ = st["units"][u]
            r = reid.find_in_shot(img_pred, st["_video"], st["boxes"], lo, hi,
                                  segs=st.get("_segs"))
            if r is not None and (auto[u] is None or r["how"] == "face"):
                auto[u] = r
        log(f"  learned {len(learned)} more look(s) of your person; searched "
            f"{len(again)} scene piece(s) again")
    for r in auto.values():
        if r:
            r.pop("emb", None)
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


def part_is_current(st, p, grow=None, pad=PAD):
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
        if len(_DET) >= 3:  # a few small models stay loaded (detector, outline model)
            _DET.pop(next(iter(_DET)))
        _DET[weights] = YOLO(weights)
    return _DET[weights]


def verify_part(st, part_mp4, a, b, prot_dir, final_dir, stride=4, conf=0.45):
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
        res = det.predict(batch, classes=[0], conf=conf, imgsz=min(cfg["det_imgsz"], 640),
                          verbose=False,
                          device=0 if DEVICE == "cuda" else "cpu")
        for g, r in zip(ids, res):
            for bx in r.boxes.xyxy.cpu().numpy().astype(np.float32):
                x1, y1 = max(0, int(bx[0])), max(0, int(bx[1]))
                x2, y2 = min(w, int(bx[2])), min(h, int(bx[3]))
                if x2 - x1 < 4 or y2 - y1 < 4:
                    continue
                pr = _read_mask(prot_dir, g)
                painted = _read_mask(final_dir, g)[y1:y2, x1:x2].mean()
                if remove_mode:
                    if painted > 0.5 and pr[y1:y2, x1:x2].mean() < 0.3:
                        out.append((g, bx, True))
                    continue
                if pr[y1:y2, x1:x2].mean() >= 0.15:
                    continue
                if pr.any() and _iou(bx, _bbox(pr)) >= 0.2:
                    continue
                if not pr.any() and kept_nearby(g, bx):
                    continue
                # painted: a figure in the repainted area; else a real person left over
                out.append((g, bx, painted >= 0.4))
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


def _apply_self_fix(st, p, viol, max_per_unit=3, max_repaint=0.0, min_left=3):
    """Turn self-check findings into fixes for this part. Left-over people are tracked and
    removed; figures painted into the background are painted again with wider masks (only
    when they are in a limited share of the part, to keep the time). Returns (fixes made,
    frames to repaint)."""
    opts = st.setdefault("part_opts", {}).setdefault(p, {})
    a, b = st["parts"][p]
    made, repaint = 0, set()
    pf = sorted({int(v[0]) for v in viol if v[2]})
    if pf and len(pf) * 4 <= max_repaint * (b - a):  # self-check looks at every 4th frame
        opts["seed"] = opts.get("seed", 42) + 1
        repaint = {i for g in pf for i in range(max(a, g - 12), min(b, g + 13))}
        made += 1
    if sum(1 for v in viol if not v[2]) < min_left:  # a stray detection or two: not worth a redo
        return made, repaint
    groups = {}
    for g, bx, painted in viol:  # same person seen in several frames -> one fix
        if painted:
            continue
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
    return made, repaint


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


def _fill_level(st, opts=None):
    name = (opts or {}).get("fill_level") or st.get("fill_level")
    for lv in FILL_LEVELS:
        if lv[0] == name:
            return lv
    want = {"Best": "sharpest", "Balanced": "sharp"}.get(st["preset"], "fast")
    return next(lv for lv in FILL_LEVELS if lv[0] == want)


def fill_frames_estimate(st):
    """Frames that will need background painting (from the people found while scanning)."""
    n = 0
    for u, (lo, hi, _) in enumerate(st["units"]):
        if st.get("mode") == "remove":
            if removal_seeds(st, u):
                n += sum(1 for i in range(lo, hi) if len(st["boxes"][i]))
        else:
            k = 1 if scene_seed(st, u) is not None else 0
            n += sum(1 for i in range(lo, hi) if len(st["boxes"][i]) > k)
    return n


def choose_fill_level(st, elapsed):
    """The sharpest background painting that still lets the whole job finish within
    TARGET_SECONDS (estimated from the number of frames to paint)."""
    big = big_gpu()
    frames = fill_frames_estimate(st)
    scale = 1.0 if big else 0.35
    # masks (tracking) of the parts run beside the painting; painting starts after the first part
    first = st["parts"][0][1] - st["parts"][0][0] if st["parts"] else 0
    mask_s = st["n"] / (25.0 if big else 6.0)

    def est(lv):
        paint = frames / (lv[3] * scale * FILL_EFFICIENCY)
        return elapsed + max(mask_s, first / (8.0 if big else 2.0) + paint) + 60

    for lv in FILL_LEVELS:
        if lv[0] != "film" and est(lv) <= TARGET_SECONDS:
            return lv[0], est(lv), frames
    return FILL_LEVELS[-1][0], est(FILL_LEVELS[-1]), frames


def _work_dir(st, p):
    return os.path.join(st["cache"], f"part_work_{p:04d}")


FILL_SLOTS = [1]
_LOCK_ST = [None]


@contextlib.contextmanager
def _gpu_lock(st):
    """Limits how many parallel workers run the fill model at once (GPU memory)."""
    if not WORKER or st is None:
        yield
        return
    files = [open(os.path.join(st["cache"], f"gpu_fill_{k}.lock"), "w") for k in range(FILL_SLOTS[0])]
    got = None
    try:
        while got is None:
            for f in files:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    got = f
                    break
                except BlockingIOError:
                    continue
            if got is None:
                time.sleep(0.3)
        yield
    finally:
        if got is not None:
            fcntl.flock(got, fcntl.LOCK_UN)
        for f in files:
            f.close()


_FILL = {}


def _get_filler(kind="mm"):
    """(fill model or None, close after use). On big GPUs it stays loaded between parts.
    kind: "mm" (MiniMax-Remover, quick levels) or "svor" (film quality)."""
    make = SVORFiller if kind == "svor" else MiniMaxFiller

    def load():
        for attempt in range(4):  # another part may be using the GPU memory right now
            try:
                return make()
            except torch.cuda.OutOfMemoryError:
                if attempt == 3:
                    raise
                torch.cuda.empty_cache()
                log("  GPU memory busy - waiting to load the painter ...")
                time.sleep(30)
    if not big_gpu():
        return load(), True
    if _FILL.get(kind) is None:
        try:
            _FILL[kind] = load()
        except torch.cuda.OutOfMemoryError:
            _FILL.pop(kind, None)  # try again for the next part
            raise
        except Exception:
            _FILL[kind] = None
            raise
    if _FILL[kind] is None:
        raise RuntimeError("fill model unavailable")
    return _FILL[kind], False


def _part_masks(st, p, vid_pred, img_pred, grow, pad):
    """First half of a part: tracking, outlines and final masks (in the part work folder).
    Returns what the second half needs."""
    a, b = st["parts"][p]
    video, w, h, fps = st["_video"], st["w"], st["h"], st["fps"]
    us = [u for u, (lo, hi, _) in enumerate(st["units"]) if a <= lo and hi <= b]
    ranges = [tuple(st["units"][u][:2]) for u in us]
    opts = st.get("part_opts", {}).get(p, {})
    grow_eff = grow * opts.get("grow_mult", 1.0)
    lv = _fill_level(st, opts)
    stride = lv[4] if len(lv) > 4 else 1
    tae = bool(lv[5]) if len(lv) > 5 else False
    engine = lv[6] if len(lv) > 6 else "mm"
    steps = (max(lv[2], opts.get("steps") or 0) if engine == "svor"
             else opts.get("steps") or st.get("steps") or lv[2])
    seed = opts.get("seed", 42)
    _FILL_AREA[0] = lv[1]
    cfg = PRESETS[st["preset"]]
    pp_side = 1280 if (st["preset"] == "Best" and big_gpu()) else cfg["pp_max_side"]
    work = _work_dir(st, p)
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
    if engine == "svor" and not remove_mode:  # film: also the small people in crowd shots
        try:
            add_crowd_people(st, video, a, b)
        except Exception:
            traceback.print_exc()
    if remove_mode:
        mask_removal(img_pred, video, st["boxes"], tgt, d["raw"], d["protect"], a, b, stages=S,
                     segs=st.get("_segs"))
        _track_extra(st, vid_pred, video, "keep_extra", us, work, d["protect"])
        os.makedirs(d["tracked"], exist_ok=True)
        _track_extra(st, vid_pred, video, "extra", us, work, d["tracked"], minus=d["protect"])
    else:
        mask_others(img_pred, video, st["boxes"], tgt, d["raw"], d["protect"],
                    d["inst"] if opts.get("track_all") else None, a, b,
                    stages=S, segs=st.get("_segs"))
        S.start(2)
        if opts.get("track_all"):  # slow: SAM 2 follows every other person
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
    preview = _IO.submit(make_preview, video, d["final"], d["protect"], chk, fps, a, b,
                         labels.get, w, h)
    S.done()
    if WORKER and DEVICE == "cuda":  # tracking memory back to the GPU pool for the painting
        torch.cuda.empty_cache()
    return dict(a=a, b=b, video=video, w=w, h=h, fps=fps, us=us, ranges=ranges, opts=opts,
                preview=preview,
                steps=steps, seed=seed, pp_side=pp_side, work=work, d=d, S=S, flags=flags,
                stride=stride, tae=tae, engine=engine)


def _part_fill(st, p, ctx, vid_pred, img_pred, pp_dir, check):
    """Second half of a part: rebuild the background, write the part video, self-check.
    Returns the self-check findings (empty if all is well or not checked)."""
    a, b, video, w, h, fps = (ctx[k] for k in ("a", "b", "video", "w", "h", "fps"))
    ranges, opts, steps, seed = ctx["ranges"], ctx["opts"], ctx["steps"], ctx["seed"]
    pp_side, work, d, S, flags = ctx["pp_side"], ctx["work"], ctx["d"], ctx["S"], ctx["flags"]
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
                filler, close_it = _get_filler(ctx.get("engine", "mm"))
                if hasattr(filler, "use_tae"):
                    try:
                        filler.use_tae(ctx.get("tae", False))
                    except Exception:  # tiny decoder not available: the normal one is used
                        traceback.print_exc()
                        filler.use_tae(False)
            except Exception as e:  # missing model, download problem ... -> fast fill instead
                traceback.print_exc()
                log(f"  realistic fill unavailable ({e.__class__.__name__}); using the fast fill")
        if static:
            fills.append(plate_fill(video, d["final"], d["protect"], flags, static, w, h, filler,
                                    steps=steps, seed=seed, stages=S))
        done_moving = False
        if moving and filler is not None:
            k = ctx.get("stride", 1)
            # 49 painted frames per piece: 81 at 832x480 ran out of memory with 3 parts at once
            wins = (81, 49, 25) if ctx.get("engine") == "svor" else (49 * k, 25 * k, 13 * k)
            for win in wins:
                try:
                    if ctx.get("mm_prev") is None:
                        shutil.rmtree(os.path.join(work, "mm_out"), ignore_errors=True)
                    refine = judge = None
                    if ctx.get("engine") == "svor":
                        try:
                            judge = figure_judge(PRESETS[st["preset"]]["det"])
                        except Exception:
                            traceback.print_exc()
                    if ctx.get("engine") == "svor":  # (also keeps the people who stay in remove mode)
                        try:
                            refine, _ = _get_filler("mm")
                            refine.use_tae(False)
                        except Exception:
                            traceback.print_exc()
                    res = fill_realistic(video, d["final"], flags, work, moving, w, h, filler,
                                         window=win, overlap=8, stages=S, seed=seed, steps=steps,
                                         reuse=ctx.get("mm_prev"), changed=ctx.get("changed"),
                                         stride=ctx.get("stride", 1), prot_dir=d["protect"],
                                         refine=refine, judge=judge)
                    ctx["mm_prev"] = res
                    fills.append(res)
                    ov, done_moving = 8, True
                    break
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    if ctx.get("engine") == "svor" and not ctx.get("_oom_wait"):
                        ctx["_oom_wait"] = True  # another part is painting: wait, same pieces
                        log("  GPU memory busy; waiting a moment, then painting again")
                        time.sleep(45)
                        try:
                            res = fill_realistic(video, d["final"], flags, work, moving, w, h,
                                                 filler, window=win, overlap=8, stages=S, seed=seed,
                                                 steps=steps, reuse=ctx.get("mm_prev"),
                                                 changed=ctx.get("changed"),
                                                 stride=ctx.get("stride", 1), prot_dir=d["protect"],
                                                 refine=refine, judge=judge)
                            ctx["mm_prev"] = res
                            fills.append(res)
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
        with _gpu_lock(st):
            fills.append(inpaint(video, d["final"], flags, work, pp_dir, moving, w, h, pp_side,
                                 stages=S))
        ov = 16
    chs, results = _merge_fills(fills)
    S.start(5)
    out = os.path.join(work, "part.mp4")
    film = ({"ranges": ranges, "gate": True, "effects": True}
            if ctx.get("engine") == "svor" else None)
    composite(video, d["final"], d["protect"], flags, chs, results, out, fps, a, b, w, h,
              overlap=ov, stages=S, film=film)
    viol = []
    if check:
        S.start(6)
        viol = verify_part(st, out, a, b, d["protect"], d["final"])
    S.done()
    return viol


def _part_remask(st, p, ctx, vid_pred, viol, grow, pad, repaint=()):
    """After the self-check: add the people it found to the existing masks; only the
    moments that changed are painted again."""
    a, b, video, w, h, d, work, us, ranges, S = (ctx[k] for k in (
        "a", "b", "video", "w", "h", "d", "work", "us", "ranges", "S"))
    opts = st.get("part_opts", {}).get(p, {})
    S.start(2)
    changed = set(repaint)
    if st.get("mode") != "remove" and any(not v[2] for v in viol):
        shutil.rmtree(d["tracked"], ignore_errors=True)
        os.makedirs(d["tracked"], exist_ok=True)
        _track_extra(st, vid_pred, video, "extra", us, work, d["tracked"], minus=d["protect"])
        flush_masks()
        changed |= {i for i in range(a, b) if os.path.exists(_mpath(d["tracked"], i))
                    and _read_mask(d["tracked"], i).any()}
    S.start(3)
    grow_eff = grow * opts.get("grow_mult", 1.0)
    grow_px = max(1, round(grow_eff * max(h, w)))
    ctx["flags"] = finalize_masks(d["raw"], d["tracked"], d["protect"], d["final"], ranges, pad,
                                  grow_px)
    if repaint:  # wider masks where figures were painted in (edges of people left visible)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow_px + 1, grow_px + 1))
        for i in sorted(repaint):
            m = _read_mask(d["final"], i)
            if m.any():
                m = (cv2.dilate(m.astype(np.uint8), k) > 0) & ~_read_mask(d["protect"], i)
                _write_mask(d["final"], i, m)
        flush_masks()
    if changed:  # the check video shows the added people too
        labels = {i: unit_label(st, u).lower() for u in us for i in range(*st["units"][u][:2])}
        make_preview(video, d["final"], d["protect"], os.path.join(work, "check.mp4"), ctx["fps"],
                     a, b, labels.get, w, h)
    S.done()
    ctx.update(changed=changed, seed=opts.get("seed", 42))
    return ctx


def _build_part(st, p, vid_pred, img_pred, pp_dir, grow, pad, check, ctx=None):
    """Masks, fill and composite for one part (ctx: masks made beforehand)."""
    ctx = ctx or _part_masks(st, p, vid_pred, img_pred, grow, pad)
    return _part_fill(st, p, ctx, vid_pred, img_pred, pp_dir, check)


def process_part(st, p, vid_pred, img_pred, pp_dir, grow, pad=PAD, self_check=True, ctx=None):
    a, b = st["parts"][p]
    rep = {"found": 0, "fixed": 0, "left": []}
    viol, repaint = [], set()
    for rnd in range(2 if self_check else 1):
        if rnd == 0:
            ctx = ctx or _part_masks(st, p, vid_pred, img_pred, grow, pad)
        else:
            ctx = _part_remask(st, p, ctx, vid_pred, viol, grow, pad, repaint)
        viol = _part_fill(st, p, ctx, vid_pred, img_pred, pp_dir, check=self_check)
        if rnd == 0:
            rep["found"] = len(viol)
            rep["painted"] = sum(1 for v in viol if v[2])
        rep["samples"] = [(int(v[0]), [int(x) for x in v[1][:4]], bool(v[2]))
                          for v in viol[::max(1, len(viol) // 8)][:8]]
        if not viol:
            break
        frames = sorted({int(v[0]) for v in viol})
        if rnd == 1:  # still there after the automatic fix: show to the user
            rep["left"] = frames[::max(1, len(frames) // 5)][:5]
            log(f"  Self-check: {len(viol)} sighting(s) remain - please check them")
            break
        late = (_fill_level(st)[0] != "film" and  # film quality: always fix what the check finds
                time.time() - st.get("t_start", time.time()) > 0.5 * TARGET_SECONDS)
        made, repaint = (0, set()) if late else _apply_self_fix(st, p, viol)
        n_p = sum(1 for v in viol if v[2])
        log(f"  Self-check: {len(viol) - n_p} left-over person sighting(s), {n_p} figure(s) "
            f"painted in; {'fixing this part' if made else 'no time to fix' if late else 'nothing to change'}")
        save_job(st)
        if not made:
            rep["left"] = frames[::max(1, len(frames) // 5)][:5]
            break
        rep["fixed"] = made
    st.setdefault("selfcheck", {})[p] = rep
    if ctx.get("preview") is not None:
        ctx["preview"].result()  # check video finished
    work = _work_dir(st, p)
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
        opts["steps"] = min(24, (opts.get("steps") or st.get("steps")
                                 or FILL_STEPS.get(st["preset"], 8)) + 4)
        opts["seed"] = opts.get("seed", 42) + 1
        opts["ai"] = True
        opts["smudge"] = opts.get("smudge", 0) + 1
        names = [lv[0] for lv in FILL_LEVELS]
        cur = names.index(_fill_level(st, opts)[0])
        opts["fill_level"] = names[max(0, cur - 1)]
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
    return dict(grow=round(GROW * 1.25 ** e, 4), conf=max(0.10, 0.15 - 0.025 * min(pz, 2)),
                extra_steps=4 * min(sm, 2), notes=notes, counts=counts)


# ---------------------------------------------------------------- parallel parts
def n_workers(n_todo):
    """How many parts to process at the same time (GPU memory and CPU cores allow ~3 on an
    A100 40 GB). KOP_WORKERS overrides."""
    n = int(os.environ.get("KOP_WORKERS", "0") or 0)
    if n:
        return max(1, min(n, n_todo))
    if DEVICE != "cuda":
        return 1
    mem = torch.cuda.get_device_properties(0).total_memory
    n = 3 if mem > 35e9 else 2 if mem > 20e9 else 1
    return max(1, min(n, n_todo, (os.cpu_count() or 2) // 2))


def run_parallel(st, todo, n_w, vid_pred, img_pred, pp_dir, grow):
    """Process parts in n_w worker processes; show their combined progress and pictures;
    merge what they changed (self-check fixes) back into the job."""
    flush_masks()
    if DEVICE == "cuda":  # the scan and search leave GPU memory cached: give it to the workers
        __import__("gc").collect()
        torch.cuda.empty_cache()
    c = st["cache"]
    for f in glob.glob(os.path.join(c, "status_w*")) + glob.glob(os.path.join(c, "preview_w*")) + \
            glob.glob(os.path.join(c, "result_*")) + glob.glob(os.path.join(c, "timings_w*")):
        os.remove(f)
    groups = [todo[k::n_w] for k in range(n_w)]
    log(f"Working on {n_w} parts at the same time ...", 0.0)
    _sam2_to(vid_pred, img_pred, "cpu")  # the workers need the GPU memory
    procs = []
    try:
        for k, g in enumerate(groups):
            lf = open(os.path.join(c, f"worker_{k}.log"), "w")
            cmd = [sys.executable, os.path.abspath(__file__), "--worker", st["job_dir"],
                   os.path.dirname(c), _SAM2_DIR[0] or "", pp_dir, str(grow), str(k),
                   ",".join(str(p) for p in g)]
            procs.append((subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                           env=dict(os.environ, PYTHONUNBUFFERED="1",
                                                    PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")),
                          lf))
        shown = 0.0
        while any(pr.poll() is None for pr, _ in procs):
            time.sleep(1.0)
            done = sum(1 for p in todo if os.path.exists(os.path.join(c, f"result_{p}.pkl")))
            run, texts = 0.0, []
            for k in range(n_w):
                try:
                    with open(os.path.join(c, f"status_w{k}.json")) as f:
                        j = json.load(f)
                except Exception:
                    continue
                if j.get("p") is not None and not os.path.exists(os.path.join(c, f"result_{j['p']}.pkl")):
                    run += min(max(j.get("f", 0.0), 0.0), 1.0)
                    texts.append(j.get("text", ""))
            if _PROGRESS is not None:
                try:
                    _PROGRESS(min(0.99, (done + run) / len(todo)),
                              f"{n_w} parts at the same time · " + " | ".join(texts[:3]))
                except Exception:
                    pass
            pv = sorted(glob.glob(os.path.join(c, "preview_w*.jpg")), key=os.path.getmtime)
            if pv and _PREVIEW is not None and os.path.getmtime(pv[-1]) > shown:
                shown = os.path.getmtime(pv[-1])
                img = cv2.imread(pv[-1])
                if img is not None:
                    try:
                        _PREVIEW(img)
                    except Exception:
                        pass
    finally:
        for pr, lf in procs:
            if pr.poll() is None:
                pr.wait()
            lf.close()
        _sam2_to(vid_pred, img_pred, DEVICE)
    for k, (pr, _) in enumerate(procs):
        if pr.returncode != 0:
            with open(os.path.join(c, f"worker_{k}.log")) as f:
                tail = f.read()[-3000:]
            log(f"A parallel worker stopped (code {pr.returncode}); its parts are redone one by "
                f"one.\n{tail}")
    for p in todo:
        rp_ = os.path.join(c, f"result_{p}.pkl")
        if not os.path.exists(rp_):
            continue
        with open(rp_, "rb") as f:
            r = pickle.load(f)
        for u, v in r["extra"].items():
            st.setdefault("extra", {})[u] = v
        if r["part_opts"] is not None:
            st.setdefault("part_opts", {})[p] = r["part_opts"]
        st.setdefault("selfcheck", {})[p] = r["selfcheck"]
        st.setdefault("plate_ranges", {})[p] = r["plate_ranges"]
    for k in range(n_w):
        try:
            with open(os.path.join(c, f"timings_w{k}.json")) as f:
                for name, v in json.load(f).items():
                    TIMINGS[name] = TIMINGS.get(name, 0.0) + v
        except Exception:
            pass
    save_job(st)


def _worker_main(job_dir, cache_root, sam2_dir, pp_dir, grow, wid, parts):
    """One parallel worker: processes its parts with its own models."""
    global WORKER, OFFLOAD_VIDEO
    WORKER, OFFLOAD_VIDEO = True, True
    if os.environ.get("KOP_PRESETS"):  # test settings handed down by the main process
        PRESETS.update(json.loads(os.environ["KOP_PRESETS"]))
    st = load_job(job_dir, cache_root)
    st["_worker"] = True
    c, n = st["cache"], len(st["parts"])
    vid_pred, img_pred = load_sam2(sam2_dir, PRESETS[st["preset"]]["sam2"])
    cur, last = {"p": None}, {"s": 0.0, "v": 0.0}

    def _atomic_json(path, obj):
        with open(path + ".tmp", "w") as f:
            json.dump(obj, f)
        os.replace(path + ".tmp", path)

    def prog(frac, text):
        if time.time() - last["s"] < 0.5 or cur["p"] is None:
            return
        last["s"] = time.time()
        pf = (frac * n - cur["p"]) if frac is not None else None
        try:
            old = {}
            if pf is None and os.path.exists(os.path.join(c, f"status_w{wid}.json")):
                with open(os.path.join(c, f"status_w{wid}.json")) as f:
                    old = json.load(f)
            _atomic_json(os.path.join(c, f"status_w{wid}.json"),
                         {"p": cur["p"], "f": pf if pf is not None else old.get("f", 0.0),
                          "text": text})
        except Exception:
            pass

    def prev(img):
        if time.time() - last["v"] < 2.0:
            return
        last["v"] = time.time()
        path = os.path.join(c, f"preview_w{wid}.jpg")
        cv2.imwrite(path + ".tmp.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        os.replace(path + ".tmp.jpg", path)

    set_progress(prog)
    set_preview(prev)
    _PV.update(video=st["_video"], remove=st.get("mode") == "remove")
    _LOCK_ST[0] = st
    for p in parts:
        cur["p"] = p
        process_part(st, p, vid_pred, img_pred, pp_dir, grow)
        a, b = st["parts"][p]
        us = [u for u, (lo, hi, _) in enumerate(st["units"]) if a <= lo and hi <= b]
        res = {"extra": {u: st["extra"][u] for u in us if u in st.get("extra", {})},
               "part_opts": st.get("part_opts", {}).get(p),
               "selfcheck": st.get("selfcheck", {}).get(p),
               "plate_ranges": st.get("plate_ranges", {}).get(p)}
        path = os.path.join(c, f"result_{p}.pkl")
        with open(path + ".tmp", "wb") as f:
            pickle.dump(res, f)
        os.replace(path + ".tmp", path)
    _atomic_json(os.path.join(c, f"timings_w{wid}.json"), TIMINGS)


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
        audio = os.path.join(st["cache"], st["audio"]) if st.get("audio") and not check else None
        if audio:
            cmd += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0"] + audio_args(audio) + [
                    "-t", f"{st['n'] / fps_float(st['fps']):.3f}"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", local + ".tmp.mp4"]
        subprocess.run(cmd, check=True)
        os.replace(local + ".tmp.mp4", local)
        _copy_atomic(local, final_path(st["job_dir"], st, check))
        outs.append(local)
    return outs[0], outs[1]


def remove_others(st, reid, vid_pred, img_pred, pp_dir, grow=None, photos=()):
    """Erase everyone except the kept person, part by part (finished parts are skipped,
    so this also resumes an interrupted job). Returns (video, check video) paths."""
    grow = grow or GROW
    if st.get("mode") == "remove":
        if not any(st.get("rseeds", {}).values()):
            raise ValueError("Click on the people to remove first.")
        if st.get("rauto") is None and len(st["units"]) > len(st.get("rseeds", {})):
            t = time.time()
            find_targets(st, reid, vid_pred, img_pred)
            st.setdefault("prep", {})["Finding the people in every scene"] = round(time.time() - t, 1)
    else:
        if not any(v is not None for v in st["seeds"].values()):
            raise ValueError("Click on the person to keep first.")
        if st["auto"] is None and len(st["units"]) > len(st["seeds"]):
            t = time.time()
            find_person(st, reid, vid_pred, img_pred, photos)
            st.setdefault("prep", {})["Finding your person in every scene"] = round(time.time() - t, 1)
    st["grow"] = grow
    st["t_start"] = time.time() - sum((st.get("prep") or {}).values())  # job clock
    save_job(st)
    _PV.update(video=st["_video"], remove=st.get("mode") == "remove")
    TIMINGS.clear()
    t0 = time.time()
    todo = [p for p in range(len(st["parts"])) if not part_is_current(st, p, grow)]
    if todo and len(todo) < len(st["parts"]):
        log(f"{len(st['parts']) - len(todo)} of {len(st['parts'])} part(s) already done; "
            f"processing {len(todo)}.")
    if todo and not st.get("fill_level") and st.get("fill", "realistic") == "realistic":
        name, est, frames = choose_fill_level(st, sum((st.get("prep") or {}).values()))
        st["fill_level"], st["fill_auto"] = name, True
        log(f"Background painting: {name} ({frames} frames to paint; about "
            f"{round(est / 60)} min in total)")
        save_job(st)
    n_w = n_workers(len(todo))
    if todo and _fill_level(st)[0] == "film":
        n_w = min(n_w, int(os.environ.get("KOP_FILM_WORKERS", "2")))  # two painters per part
        frames = fill_frames_estimate(st)
        est = frames / (FILM_FPS if big_gpu() else FILM_FPS * 0.3)
        log(f"Film quality: {frames} frames to paint; about {max(1, round(est / 60))} min "
            f"(an estimate) - it is worth it.")
    if n_w > 1:
        run_parallel(st, todo, n_w, vid_pred, img_pred, pp_dir, grow)
    for p in todo:  # sequential (and whatever a parallel worker could not finish)
        if n_w == 1 or not part_is_current(st, p, grow):
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
    st["timings"] = dict(TIMINGS, total=time.time() - t0, parts_done=len(todo), workers=n_w)
    save_job(st)
    log(f"Done: {final}", 1.0)
    return out, chk


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--worker":
    _a = sys.argv[2:]
    _worker_main(_a[0], _a[1], _a[2], _a[3], float(_a[4]), int(_a[5]),
                 [int(x) for x in _a[6].split(",") if x])
