"""Keep One Person - simple step-by-step web app.

Google Drive > Keep One Person            put your video and photos of the person here
Google Drive > Keep One Person > Finished  finished videos appear here

Steps: 1 your video (+ photos) -> 2 who to keep (skipped when photos work) -> 3 check
scenes -> working (live view) -> done. Unfinished videos can be continued later."""
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

import cv2
import gradio as gr
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import remove_people as rp  # noqa: E402

SAM2_DIR = os.environ.get("KOP_SAM2_DIR", "/content/repos/sam2")
PP_DIR = os.environ.get("KOP_PP_DIR", "/content/repos/ProPainter")
CACHE = os.environ.get("KOP_CACHE", "/content/kop_cache")
DRIVE_ROOT = os.environ.get("KOP_DRIVE_ROOT", "/content/drive/MyDrive/Keep One Person")
EMB = os.environ.get("KOP_EMB", "yolo11s-cls.pt")
PART_SECONDS = float(os.environ.get("KOP_PART_SECONDS", rp.PART_SECONDS))
CKPT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/"
LEGACY_INPUT = os.path.join(os.path.dirname(DRIVE_ROOT), "KeepOnePerson_input")
LEGACY_JOBS = os.path.join(os.path.dirname(DRIVE_ROOT), "KeepOnePerson")
FILLS = ["Realistic (AI-painted background)", "Fast (smoother, quicker)"]
MODES = ["Keep one person - remove everyone else", "Remove some people - keep everyone else"]
GREEN, RED = np.array([0, 220, 0]), np.array([0, 0, 235])
FB_KINDS = {"A person is still here": "person", "Smudged or blurry here": "smudge",
            "Outline or shadow of a person is visible": "edges",
            "Wrong person - this one should stay": "wrong"}


def is_remove(st):
    return st is not None and st.get("mode") == "remove"
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MAX_VIEW = 1280
_M = {}


# ---------------------------------------------------------------- places
def drive_ok():
    return os.path.isdir(os.path.dirname(DRIVE_ROOT))


def jobs_root():
    d = os.path.join(DRIVE_ROOT, "In progress (automatic)") if drive_ok() else CACHE
    os.makedirs(d, exist_ok=True)
    return d


def out_root():
    return os.path.join(DRIVE_ROOT if drive_ok() else CACHE, "Finished")


def drive_inputs():
    """Videos and photos in Google Drive > Keep One Person (older folder name also works)."""
    vids, pics = [], []
    for d in (DRIVE_ROOT, LEGACY_INPUT):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if f.lower().endswith(VIDEO_EXT):
                    vids.append(p)
                elif f.lower().endswith(PHOTO_EXT):
                    pics.append(p)
    return vids, pics


def unfinished_jobs():
    jobs = []
    for root in {jobs_root(), LEGACY_JOBS}:
        if os.path.isdir(root):
            try:
                jobs += rp.list_jobs(root)
            except Exception:
                pass
    return [j for j in jobs if not j["final"]]


def job_choices():
    return [(f"{j['src']} ({_mmss(j['seconds'])}) - {j['done']} of {j['parts']} parts done",
             j["job_dir"]) for j in unfinished_jobs()]


# ---------------------------------------------------------------- models
def auto_preset(seconds):
    """Best for videos up to 3 minutes, Balanced (faster) for longer ones."""
    return "Best" if seconds <= 180 else "Balanced"


def fb_dir():
    return os.path.join(DRIVE_ROOT if drive_ok() else CACHE, "Feedback")


def models(preset):
    """SAM 2 (size depends on quality) + person recognition, loaded once and reused."""
    size = rp.PRESETS[preset]["sam2"]
    if _M.get("size") != size:
        _M.pop("vid", None)
        _M.pop("img", None)
        if rp.DEVICE == "cuda":
            torch.cuda.empty_cache()
        name = rp.SAM2_MODELS[size][0]
        ck = os.path.join(SAM2_DIR, "checkpoints", name)
        if not os.path.exists(ck):
            rp.log("Downloading an AI model ...")
            urllib.request.urlretrieve(CKPT_URL + name, ck + ".part")
            os.replace(ck + ".part", ck)
        _M["vid"], _M["img"] = rp.load_sam2(SAM2_DIR, size)
        _M["size"] = size
    if "reid" not in _M:
        _M["reid"] = rp.ReID(emb_weights=EMB)
    return _M["vid"], _M["img"], _M["reid"]


# ---------------------------------------------------------------- small helpers
def _dur(sec):
    sec = int(sec)
    if sec < 90:
        return "1 min"
    if sec < 3600:
        return f"{round(sec / 60)} min"
    return f"{sec // 3600} h {round(sec % 3600 / 60)} min"


def _mmss(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _took(sec):
    sec = int(round(sec))
    return f"{sec // 60} min {sec % 60} s" if sec >= 60 else f"{sec} s"


def _progress_to(progress):
    rp.set_progress(lambda f, t: progress(f, desc=t.strip()))


def _fail(e):
    traceback.print_exc()
    raise gr.Error(str(e) or e.__class__.__name__)


def _need(st):
    if st is None:
        raise gr.Error("Please start again from step 1.")


def show(step):
    """Visibility of the five screens: 0 video, 1 who, 2 check, 3 working, 4 done."""
    return [gr.update(visible=(k == step)) for k in range(5)]


def render(st, i, mask=None):
    img = cv2.imread(st["_video"][i])
    u = int(st["_unit_of"][i])
    col = RED if is_remove(st) else GREEN
    tgt = os.path.join(st["cache"], "target", f"{i:06d}.png")
    if mask is None and st["_tracked"].get(u) is not None and os.path.exists(tgt):
        mask = cv2.imread(tgt, cv2.IMREAD_GRAYSCALE) > 127
    if mask is not None and mask.any():
        img[mask] = (0.45 * img[mask] + 0.55 * col).astype(np.uint8)
    t = max(3, img.shape[1] // 300)
    seeds = rp.removal_seeds(st, u) if is_remove(st) else [rp.scene_seed(st, u)]
    for seed in seeds:
        if seed is not None and seed[0] == i:
            b = seed[1]
            cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                          tuple(int(c) for c in col), t)
    s = min(1.0, MAX_VIEW / max(img.shape[:2]))
    st["_view_scale"] = s
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def scene_status(st, u):
    if is_remove(st):
        n = len(rp.removal_seeds(st, u))
        mine = u in st.get("rseeds", {})
        return (f"✔ {n} to remove" + (" (your choice)" if mine else "")) if n else "nobody removed"
    if u in st["seeds"]:
        if st["seeds"][u] is None:
            return "nobody kept"
        return "✔ found by photo" if st.get("seed_src", {}).get(u) == "photo" else "✔ your choice"
    a = (st["auto"] or {}).get(u)
    return "✘ not here - everyone removed" if a is None else "✔ found"


def gallery(st):
    items = []
    for u, (a, b, _) in enumerate(st["units"]):
        if is_remove(st):
            seeds = rp.removal_seeds(st, u)
            i = seeds[0][0] if seeds else (a + b) // 2
            marks, col = [s[1] for s in seeds if s[0] == i], (0, 0, 235)
        else:
            seed = rp.scene_seed(st, u)
            i = seed[0] if seed is not None else (a + b) // 2
            marks, col = ([seed[1]] if seed is not None else []), (0, 220, 0)
        img = cv2.imread(st["_video"][i])
        for bx in marks:
            x1, y1, x2, y2 = map(int, bx)
            cv2.rectangle(img, (x1, y1), (x2, y2), col, max(4, img.shape[1] // 120))
        s = 360 / img.shape[1]
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        items.append((cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                      f"{rp.unit_label(st, u)} {scene_status(st, u)}"))
    return items


def _frame_note(st, i):
    return f"{_mmss(i / rp.fps_float(st['fps']))}  ·  {rp.unit_label(st, int(st['_unit_of'][i]))}"


def _check_text(st, by_photo=False):
    if is_remove(st):
        n = sum(1 for u in range(len(st["units"])) if rp.removal_seeds(st, u))
        return (f"People to remove (red boxes) were found in **{n} of {len(st['units'])}** "
                "scene(s). **Wrong?** Click that scene, then click a person to add or take them "
                "off. **Right?** Press **Start**.")
    n_ok = sum(1 for u in range(len(st["units"])) if rp.scene_seed(st, u) is not None)
    how = "Using your photos, your person" if by_photo else "Your person"
    return (f"{how} was found in **{n_ok} of {len(st['units'])}** scene(s) - green box. "
            "Where they are not found, everyone is removed. **Wrong?** Click that scene to fix "
            "it. **Right?** Press **Start**.")


def _done_text(st):
    where = ("Saved in your Google Drive › **Keep One Person › Finished**." if drive_ok()
             else "Download it below.")
    fps = rp.fps_float(st["fps"])
    lines = ["### ✅ Finished!", where]
    t = st.get("timings") or {}
    if t.get("parts_done"):
        prep = sum((st.get("prep") or {}).values())
        par = f", {t['workers']} parts at the same time" if t.get("workers", 1) > 1 else ""
        lines.append(f"⏱ Took **{_took(prep + t['total'])}** for {_took(st['n'] / fps)} of video "
                     f"(preparing {_took(prep)}, removing {_took(t['total'])}{par}).")
    sc = list((st.get("selfcheck") or {}).values())
    left = sorted(g for r in sc for g in r.get("left", []))
    if left:
        when = ", ".join(_mmss(g / fps) for g in left[:5])
        lines.append(f"⚠️ The self-check still sees someone at **{when}** - please look there, "
                     "and if so press **No, fix something**.")
    elif any(r.get("fixed") for r in sc):
        lines.append("🔎 The self-check found leftover people and fixed them automatically.")
    elif sc:
        lines.append("🔎 Self-check: no leftover people found.")
    steps = {k: v for k, v in t.items() if k not in ("total", "parts_done", "workers") and v >= 1}
    steps.update({k: v for k, v in (st.get("prep") or {}).items() if v >= 1})
    if steps:
        lines.append("<small>Time per step: " + " · ".join(
            f"{k.lower()} {_took(v)}" for k, v in sorted(steps.items(), key=lambda kv: -kv[1]))
            + "</small>")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- live view while working
def _bar(frac, n=24):
    k = int(round(frac * n))
    return "▓" * k + "░" * (n - k)


def _status(box, t0):
    frac = min(max(box["frac"], 0.0), 1.0)
    el = time.time() - t0
    left = f" · about **{_dur(el / frac * (1 - frac))}** left" if frac > 0.03 else ""
    return (f"**{box['text']}**\n\n`{_bar(frac)}`  {round(frac * 100)}%{left}\n\n"
            "Keep this tab open. If Colab disconnects, start the notebook again and press "
            "**Continue**.")


def run_live(fn, *args):
    """Run fn in the background; yield (status text, latest finished frame) every 2 s.
    The generator's return value is fn's result."""
    box = {"frac": 0.0, "text": "Starting …", "img": None, "done": False, "err": None,
           "res": None}
    t0 = time.time()

    def prog(f, t):
        if f is not None:
            box["frac"] = f
        box["text"] = t.strip().rstrip(" .")

    def prev(img):
        s = 720 / img.shape[1]
        box["img"] = cv2.cvtColor(cv2.resize(img, None, fx=s, fy=s), cv2.COLOR_BGR2RGB)

    def work():
        try:
            box["res"] = fn(*args)
        except Exception as e:
            traceback.print_exc()
            box["err"] = e
        finally:
            box["done"] = True

    rp.set_progress(prog)
    rp.set_preview(prev)
    th = threading.Thread(target=work, daemon=True)
    th.start()
    while not box["done"]:
        time.sleep(2)
        yield _status(box, t0), box["img"]
    rp.set_preview(None)
    if box["err"] is not None:
        raise gr.Error(str(box["err"]) or box["err"].__class__.__name__)
    return box["res"]


# ---------------------------------------------------------------- screen 0: your video
def on_page():
    ch = job_choices()
    vids, pics = drive_inputs()
    if drive_ok():
        os.makedirs(DRIVE_ROOT, exist_ok=True)
        note = ("💾 Work is saved in Google Drive › Keep One Person. Tip: put your video and "
                "photos there - they will show up here.")
    else:
        note = "⚠️ Google Drive is not connected: if Colab disconnects, unfinished work is lost."
    ld = rp.learned_defaults(fb_dir())
    if ld["notes"]:
        note += "\n\n🧠 Learned from your corrections: " + ", ".join(ld["notes"]) + "."
    found = (f"📁 **In your Google Drive › Keep One Person:** {len(vids)} video(s) and "
             f"{len(pics)} photo(s) of the person.") if vids else ""
    return (gr.update(visible=bool(ch)), gr.update(choices=ch, value=ch[0][1] if ch else None),
            note, gr.update(visible=bool(vids)), found,
            gr.update(choices=[(os.path.basename(v), v) for v in vids],
                      value=vids[0] if vids else None, visible=len(vids) > 1),
            gr.update(open=True))


def on_video_uploaded(path):
    """Show a picture and the details of the uploaded video (any format: the browser cannot
    play every video, e.g. H.265 phone videos, but the app reads them all)."""
    if not path:
        return "", gr.update(value=None, visible=False)
    try:
        fps, has_audio, dur, w, h = rp.probe(path)
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name", "-of", "csv=p=0", path],
                               capture_output=True, text=True).stdout.strip().upper()
        png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{min(1.0, dur / 2):.2f}", "-i", path,
                              "-frames:v", "1", "-vf", "scale=-2:360", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True).stdout
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return ("⚠️ This file could not be read as a video. Please choose another file.",
                gr.update(value=None, visible=False))
    info = (f"✅ **Video ready:** {os.path.basename(path)} · {_mmss(dur)} · {w}×{h} · "
            f"{rp.fps_float(fps):.0f} fps · {codec or 'video'} · "
            f"{'with sound' if has_audio else 'no sound'}. Press **Next**.")
    if img is None:
        return info, gr.update(value=None, visible=False)
    return info, gr.update(value=cv2.cvtColor(img, cv2.COLOR_BGR2RGB), visible=True)


def on_use_drive(vid_path, fill, start, end, mode, progress=gr.Progress()):
    vids, pics = drive_inputs()
    return on_next1(None, vid_path or (vids[0] if vids else None), start, end, pics, fill,
                    mode, progress)


def on_next1(video, path, start, end, photos=None, fill=None, mode=None, progress=gr.Progress()):
    src = (path or "").strip() if isinstance(path, str) else path
    src = src or video
    if not src or not os.path.exists(src):
        raise gr.Error("Please choose a video first.")
    if end and start and end <= start:
        raise gr.Error("The end time must be after the start time (or 0 for the whole video).")
    _progress_to(progress)
    try:
        secs = rp.probe(src)[2] - (start or 0)
        if end:
            secs = min(secs, end - (start or 0))
        preset = auto_preset(secs)
        ld = rp.learned_defaults(fb_dir())  # adapts to the corrections you made before
        st = rp.create_job(src, jobs_root(), CACHE, start or 0, end or 0, preset, ld["conf"],
                           PART_SECONDS)
        st["grow"] = ld["grow"]
        st["steps"] = (rp.FILL_STEPS[preset] + ld["extra_steps"]) if ld["extra_steps"] else None
        st["fill"] = "fast" if (fill or "").startswith("Fast") else "realistic"
        st["mode"] = "remove" if (mode or "").startswith("Remove") else "keep"
        st["out_dir"] = out_root()
        rp.save_job(st)
        vid, img_pred, reid = models(preset)
        found = None
        if is_remove(st):
            photos = None  # photos describe the person to keep
        if photos:
            rp.save_photos(st, photos)
            found = rp.anchors_from_photos(st, reid, img_pred)
            if found and found > 0:
                rp.find_person(st, reid, vid, img_pred)
    except Exception as e:
        _fail(e)
    counts = [len(b) for b in st["boxes"]]
    i = int(np.argmax(counts)) if max(counts) else 0
    if found and found > 0:  # photos worked: straight to the check
        return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), "", _frame_note(st, i),
                gr.update(interactive=False), gallery(st), _check_text(st, True)] + show(2)
    head = "**Click on the person you want to keep.** Not in this picture? Use the arrows."
    if is_remove(st):
        head = ("**Click on every person you want to remove** (they turn red; click again to "
                "undo). Use the arrows to find people who appear later.")
    elif photos:
        head = ("The photos did not clearly match anyone in the video, so please **click on the "
                "person you want to keep.**" if found == 0 else
                "No face was found in the photos, so please **click on the person you want to keep.**")
    return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), head,
            _frame_note(st, i), gr.update(interactive=False), gr.update(), gr.update()] + show(1)


# ---------------------------------------------------------------- screen 1: who to keep
def on_move(st, i, delta):
    _need(st)
    step = max(1, int(round(rp.fps_float(st["fps"]))))  # one second per arrow press
    i = int(np.clip(int(i) + delta * step, 0, st["n"] - 1))
    return render(st, i), gr.update(value=i), _frame_note(st, i)


def on_slide(st, i):
    _need(st)
    return render(st, int(i)), _frame_note(st, int(i))


def on_click(st, i, evt: gr.SelectData):
    _need(st)
    i = int(i)
    x, y = evt.index[0] / st["_view_scale"], evt.index[1] / st["_view_scale"]
    try:
        _, img_pred, _ = models(st["preset"])
        if is_remove(st):
            mask, added = rp.toggle_removal(st, img_pred, i, x, y)
        else:
            mask = rp.set_keeper(st, img_pred, i, x, y)
    except Exception as e:
        _fail(e)
    if mask is None:
        return st, render(st, i), "No person there - please click directly on someone.", \
            gr.update(interactive=_has_choice(st))
    if is_remove(st):
        n = sum(len(v) for v in st.get("rseeds", {}).values())
        return st, render(st, i, mask if added else None), \
            (f"🔴 **{n} person(s) will be removed.** Click more people (also at other moments), "
             "or press **Next**."), gr.update(interactive=n > 0)
    return st, render(st, i, mask), \
        "✅ **This person (green) will be kept.** Press **Next** - or click someone else.", \
        gr.update(interactive=True)


def _has_choice(st):
    if is_remove(st):
        return any(st.get("rseeds", {}).values())
    return any(v is not None for v in st["seeds"].values())


def on_next2(st, progress=gr.Progress()):
    _need(st)
    if len(st["units"]) <= 1:  # nothing to check: start right away
        st["_go"] = True
        return [st, gr.update(), ""] + show(3)
    _progress_to(progress)
    try:
        vid, img_pred, reid = models(st["preset"])
        if is_remove(st):
            rp.find_targets(st, reid, vid, img_pred)
        else:
            rp.find_person(st, reid, vid, img_pred)
    except Exception as e:
        _fail(e)
    return [st, gallery(st), _check_text(st)] + show(2)


# ---------------------------------------------------------------- screen 2: check scenes
def on_pick_scene(st, evt: gr.SelectData):
    _need(st)
    u = int(evt.index)
    a, b, _ = st["units"][u]
    if is_remove(st):
        seeds = rp.removal_seeds(st, u)
        i = seeds[0][0] if seeds else (a + b) // 2
        msg = (f"**{rp.unit_label(st, u)}:** click a person to add or take them off the people "
               "to remove.")
        label = "Remove nobody in this scene"
    else:
        seed = rp.scene_seed(st, u)
        i = seed[0] if seed is not None else (a + b) // 2
        msg = f"**{rp.unit_label(st, u)}:** click the person to keep here, or press the button."
        label = "Nobody to keep in this scene"
    return (gr.update(visible=True), render(st, i), gr.update(minimum=a, maximum=b - 1, value=i),
            msg, gr.update(value=label))


def on_fix_click(st, i, evt: gr.SelectData):
    _need(st)
    i = int(i)
    x, y = evt.index[0] / st["_view_scale"], evt.index[1] / st["_view_scale"]
    try:
        _, img_pred, _ = models(st["preset"])
        if is_remove(st):
            mask, added = rp.toggle_removal(st, img_pred, i, x, y, reset_search=False)
        else:
            mask = rp.set_keeper(st, img_pred, i, x, y, reset_search=False)
    except Exception as e:
        _fail(e)
    if mask is None:
        return st, gr.update(), render(st, i), "No person there - click directly on someone.", \
            gr.update()
    if is_remove(st):  # stay open: more people may need adding in this scene
        return st, gr.update(), render(st, i, mask if added else None), \
            ("Added ✔ - click more, or pick another scene." if added else "Taken off ✔"), gallery(st)
    return st, gr.update(visible=False), render(st, i, mask), "Fixed ✔", gallery(st)


def on_nobody(st, i):
    _need(st)
    if is_remove(st):
        rp.clear_removal(st, int(i))
    else:
        rp.set_absent(st, int(i), reset_search=False)
    return st, gr.update(visible=False), gallery(st)


# ---------------------------------------------------------------- screen 3: working (live)
def _remove(st):
    vid, img_pred, reid = models(st["preset"])
    return rp.remove_others(st, reid, vid, img_pred, PP_DIR, st.get("grow", 0.012))


def on_start(st):
    """Generator: live status + newest finished frame, then the finished screen."""
    _need(st)
    if not _has_choice(st):
        raise gr.Error("Please click on the people first.")
    keep = [gr.update()] * 5
    res = None
    gen = run_live(_remove, st)
    while True:
        try:
            txt, img = next(gen)
        except StopIteration as stop:
            res = stop.value
            break
        yield keep + [txt, img] + [gr.update()] * 8
    out, chk = res
    st["_out"] = out
    st["_ver"] = st.get("_ver", 0) + 1
    disp = os.path.join(os.path.dirname(out), f"view_{st['_ver']}.mp4")
    try:
        os.link(out, disp)  # new name so the player never shows an older version
    except OSError:
        disp = out
    st["_fixes"] = []
    yield [st, disp, gr.update(value=out), gr.update(value=chk), _done_text(st), "", None] + \
        show(4) + [gr.update(visible=False), "", gr.update(interactive=False)]


def on_maybe_start(st):
    if st is None or not st.pop("_go", False):
        yield [gr.update()] * 15
        return
    yield from on_start(st)


def on_continue(job_dir, progress=gr.Progress()):
    """Open an unfinished job: back to choosing the person, or straight to work."""
    if not job_dir:
        raise gr.Error("Choose the video to continue.")
    _progress_to(progress)
    try:
        st = rp.load_job(job_dir, CACHE)
        st.setdefault("out_dir", out_root())
        models(st["preset"])
    except Exception as e:
        _fail(e)
    counts = [len(b) for b in st["boxes"]]
    i = int(np.argmax(counts)) if max(counts) else 0
    if not _has_choice(st):
        head = ("**Click on every person you want to remove.**" if is_remove(st) else
                "**Click on the person you want to keep.**")
        return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), head,
                _frame_note(st, i), gr.update(interactive=False)] + show(1)
    st["_go"] = True
    return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), "", _frame_note(st, i),
            gr.update(interactive=False)] + show(3)


# ---------------------------------------------------------------- screen 4: done + fixes
def _out_frame(st, i, mark=None):
    """Picture number i of the finished video (exact), optionally with a marked spot."""
    fps = rp.fps_float(st["fps"])
    png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, (i - 0.5) / fps):.4f}",
                          "-i", st["_out"], "-frames:v", "1", "-f", "image2pipe", "-vcodec",
                          "png", "-"], capture_output=True).stdout
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(st["_video"][i])
    for (x, y) in (mark or []):
        r = max(14, img.shape[1] // 50)
        cv2.circle(img, (int(x), int(y)), r, (0, 220, 255), max(3, r // 4))
    s = min(1.0, MAX_VIEW / max(img.shape[:2]))
    st["_fb_scale"] = s
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def on_perfect(st):
    _need(st)
    rp.log_feedback(st, fb_dir(), "perfect")
    return "🙏 Thanks - noted.", gr.update(visible=False)


def on_fix_open(st):
    _need(st)
    left = sorted(g for r in (st.get("selfcheck") or {}).values() for g in r.get("left", []))
    i = left[0] if left else 0
    return (gr.update(visible=True), _out_frame(st, i),
            gr.update(maximum=st["n"] - 1, value=i), "")


def on_fb_slide(st, i):
    return _out_frame(st, int(i))


def on_fb_click(st, i, kind, note, evt: gr.SelectData):
    _need(st)
    i = int(i)
    x, y = evt.index[0] / st["_fb_scale"], evt.index[1] / st["_fb_scale"]
    try:
        _, img_pred, _ = models(st["preset"])
        msg = rp.add_feedback(st, img_pred, FB_KINDS.get(kind, "note"), i, x, y, note or "",
                              fb_dir())
    except Exception as e:
        _fail(e)
    if msg is None:
        return (st, _out_frame(st, i), "No person found there - click directly on the person.",
                gr.update(interactive=bool(st.get("_fixes"))), gr.update())
    fps = rp.fps_float(st["fps"])
    st.setdefault("_fixes", []).append(f"{_mmss(i / fps)} - {msg}")
    lst = "**Fixes to make:**\n" + "\n".join(f"{k + 1}. {t}" for k, t in enumerate(st["_fixes"]))
    lst += "\n\nAdd more, or press **Redo with these fixes** (only the affected parts are redone)."
    return st, _out_frame(st, i, [(x, y)]), lst, gr.update(interactive=True), ""


def on_restart():
    ch = job_choices()
    return [None, None, None, gr.update(visible=bool(ch)), gr.update(choices=ch)] + show(0)


# ---------------------------------------------------------------- layout
CSS = """
.gradio-container {max-width: 980px !important; margin: auto;}
#big-title h1 {font-size: 2em; margin-bottom: 0;}
.step-head p, .step-head h3 {font-size: 1.15em;}
"""

with gr.Blocks(title="Keep One Person") as demo:
    state = gr.State(None)
    gr.Markdown("# 🎬 Keep One Person\nRemove people from a video as if they had never been "
                "there - keep just one person, or remove the ones you choose. The sound stays "
                "as it was.", elem_id="big-title")

    with gr.Column(visible=True) as p0:
        with gr.Group(visible=False) as resume_box:
            gr.Markdown("### ⏯ Continue an unfinished video")
            with gr.Row():
                resume_dd = gr.Dropdown(show_label=False, choices=[], scale=4)
                resume_btn = gr.Button("Continue ▶", variant="primary", scale=1)
        gr.Markdown("### Step 1 · Your video", elem_classes="step-head")
        mode_in = gr.Radio(MODES, value=MODES[0], show_label=False)
        with gr.Group(visible=False) as drive_box:
            drive_md = gr.Markdown()
            drive_dd = gr.Dropdown(show_label=False, choices=[], visible=False)
            drive_btn = gr.Button("Start with these files ▶", variant="primary", size="lg")
        with gr.Accordion("Upload your video (and photos)", open=True) as upload_acc:
            vid_in = gr.File(label="Your video (any format: mp4, mov, mkv, avi, phone videos ...)",
                             file_types=["video", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
                                         ".mts", ".m2ts", ".3gp", ".wmv", ".flv", ".mpg"],
                             type="filepath")
            vid_info = gr.Markdown()
            vid_thumb = gr.Image(show_label=False, interactive=False, type="numpy", height=240,
                                 visible=False)
            photos_in = gr.File(label="Photos of the person to keep (optional, 'Keep one person' "
                                      "only - with photos the app finds them by itself)", file_count="multiple",
                                file_types=["image"], type="filepath")
            next1 = gr.Button("Next ▶", variant="primary", size="lg")
        with gr.Accordion("More options", open=False):
            path_in = gr.Textbox(label="Or the path of a video file",
                                 placeholder="/content/drive/MyDrive/Keep One Person/video.mp4")
            with gr.Row():
                start_in = gr.Number(label="Only from second", value=0, minimum=0)
                end_in = gr.Number(label="…to second (0 = to the end)", value=0, minimum=0)
            fill_in = gr.Radio(FILLS, value=FILLS[0], label="How to fill where people were")
        store_note = gr.Markdown()

    with gr.Column(visible=False) as p1:
        gr.Markdown("### Step 2 · Choose the people", elem_classes="step-head")
        head1 = gr.Markdown()
        view = gr.Image(show_label=False, interactive=False, type="numpy")
        with gr.Row():
            back_btn = gr.Button("◀ 1 second back")
            note1 = gr.Markdown()
            fwd_btn = gr.Button("1 second forward ▶")
        frame_sl = gr.Slider(0, 1, value=0, step=1, label="Or drag to any moment")
        next2 = gr.Button("Next ▶", variant="primary", size="lg", interactive=False)

    with gr.Column(visible=False) as p2:
        gr.Markdown("### Step 3 · Check each scene", elem_classes="step-head")
        head2 = gr.Markdown()
        gal = gr.Gallery(show_label=False, columns=4, fit_columns=False, object_fit="contain",
                         height="auto", allow_preview=False)
        with gr.Column(visible=False) as fix_box:
            fix_head = gr.Markdown()
            fix_view = gr.Image(show_label=False, interactive=False, type="numpy")
            fix_sl = gr.Slider(0, 1, value=0, step=1, label="Move within this scene")
            nobody_btn = gr.Button("Nobody to keep in this scene")
        start_btn = gr.Button("Start ▶", variant="primary", size="lg")

    with gr.Column(visible=False) as p3:
        gr.Markdown("### Working on your video", elem_classes="step-head")
        work_md = gr.Markdown("Starting …")
        live_img = gr.Image(label="Live view: green = kept, red = being removed (then the "
                                  "finished picture)", interactive=False, type="numpy",
                            height=360)
        go_btn = gr.Button("Try again ▶", size="sm")

    with gr.Column(visible=False) as p4:
        done_md = gr.Markdown()
        out_vid = gr.Video(show_label=False)
        dl_btn = gr.DownloadButton("⬇ Download the video", variant="primary", size="lg")
        gr.Markdown("### Is it right?", elem_classes="step-head")
        with gr.Row():
            ok_btn = gr.Button("✅ Yes, perfect")
            fix_btn = gr.Button("✏️ No, fix something", variant="primary")
        thanks_md = gr.Markdown()
        with gr.Column(visible=False) as fb_box:
            gr.Markdown("**1.** Move the slider to the problem. **2.** Choose what is wrong. "
                        "**3.** Click on that spot in the picture.")
            fb_sl = gr.Slider(0, 1, step=1, value=0, label="Moment in the video")
            fb_kind = gr.Radio(list(FB_KINDS), value=list(FB_KINDS)[0], show_label=False)
            fb_view = gr.Image(show_label=False, interactive=False, type="numpy")
            fb_note = gr.Textbox(label="Anything else? (optional - type it before clicking)",
                                 placeholder="e.g. the shadow on the left wall is still there")
            fb_list = gr.Markdown()
            redo_btn = gr.Button("Redo with these fixes ▶", variant="primary", size="lg",
                                 interactive=False)
        chk_btn = gr.DownloadButton("Download the check video (red = removed, green = kept)",
                                    size="sm")
        new_btn = gr.Button("Make another video")

    steps = [p0, p1, p2, p3, p4]
    run_outs = [state, out_vid, dl_btn, chk_btn, done_md, work_md, live_img] + steps + \
        [fb_box, fb_list, redo_btn]

    demo.load(on_page, None,
              [resume_box, resume_dd, store_note, drive_box, drive_md, drive_dd, upload_acc])
    n1_outs = [state, view, frame_sl, head1, note1, next2, gal, head2] + steps
    drive_btn.click(on_use_drive, [drive_dd, fill_in, start_in, end_in, mode_in], n1_outs)
    vid_in.change(on_video_uploaded, [vid_in], [vid_info, vid_thumb])
    next1.click(on_next1, [vid_in, path_in, start_in, end_in, photos_in, fill_in, mode_in],
                n1_outs)
    back_btn.click(lambda st, i: on_move(st, i, -1), [state, frame_sl], [view, frame_sl, note1])
    fwd_btn.click(lambda st, i: on_move(st, i, +1), [state, frame_sl], [view, frame_sl, note1])
    frame_sl.release(on_slide, [state, frame_sl], [view, note1])
    view.select(on_click, [state, frame_sl], [state, view, head1, next2])
    next2.click(on_next2, [state], [state, gal, head2] + steps).then(
        on_maybe_start, [state], run_outs)
    gal.select(on_pick_scene, [state], [fix_box, fix_view, fix_sl, fix_head, nobody_btn])
    fix_sl.release(lambda st, i: render(st, int(i)), [state, fix_sl], [fix_view])
    fix_view.select(on_fix_click, [state, fix_sl], [state, fix_box, fix_view, fix_head, gal])
    nobody_btn.click(on_nobody, [state, fix_sl], [state, fix_box, gal])
    start_btn.click(lambda: show(3), None, steps).then(on_start, [state], run_outs)
    go_btn.click(on_start, [state], run_outs)
    resume_btn.click(on_continue, [resume_dd],
                     [state, view, frame_sl, head1, note1, next2] + steps).then(
        on_maybe_start, [state], run_outs)
    ok_btn.click(on_perfect, [state], [thanks_md, fb_box])
    fix_btn.click(on_fix_open, [state], [fb_box, fb_view, fb_sl, thanks_md])
    fb_sl.release(on_fb_slide, [state, fb_sl], [fb_view])
    fb_view.select(on_fb_click, [state, fb_sl, fb_kind, fb_note],
                   [state, fb_view, fb_list, redo_btn, fb_note])
    redo_btn.click(lambda: show(3), None, steps).then(on_start, [state], run_outs)
    new_btn.click(on_restart, None, [state, vid_in, photos_in, resume_box, resume_dd] + steps)

if __name__ == "__main__":
    demo.queue().launch(share=True, debug=True, css=CSS, allowed_paths=[CACHE, DRIVE_ROOT])
