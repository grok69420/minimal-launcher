"""Keep One Person - simple step-by-step web app.
Step 1 choose a video -> Step 2 click the person to keep -> (Step 3 check scenes) ->
working -> done. Progress of long videos is saved to Google Drive and can be continued."""
import os
import sys
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
DRIVE_JOBS = os.environ.get("KOP_DRIVE_JOBS", "/content/drive/MyDrive/KeepOnePerson")
EMB = os.environ.get("KOP_EMB", "yolo11s-cls.pt")
PART_SECONDS = float(os.environ.get("KOP_PART_SECONDS", rp.PART_SECONDS))
CKPT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/"
MAX_VIEW = 1280
QUALITY = ["Automatic", "Best", "Balanced", "Fast"]
DRIVE_INPUT = os.environ.get("KOP_DRIVE_INPUT", "/content/drive/MyDrive/KeepOnePerson_input")
FILLS = ["Realistic (AI-generated background, slower)", "Fast (smoother, quicker)"]
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

_M = {}


# ---------------------------------------------------------------- helpers
def drive_ok():
    return os.path.isdir(os.path.dirname(DRIVE_JOBS))


def jobs_root():
    root = DRIVE_JOBS if drive_ok() else CACHE
    os.makedirs(root, exist_ok=True)
    return root


def models(preset):
    """SAM 2 (size depends on quality) + person re-ID, loaded once and reused."""
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


def _progress_to(progress):
    t0 = time.time()

    def cb(frac, text):
        if frac is not None and frac > 0.03:
            left = (time.time() - t0) / frac * (1 - frac)
            text = f"{text}  ·  about {_dur(left)} left"
        progress(frac, desc=text)

    rp.set_progress(cb)


def _dur(sec):
    sec = int(sec)
    if sec < 60:
        return "1 min"
    if sec < 3600:
        return f"{round(sec / 60)} min"
    return f"{sec // 3600} h {round(sec % 3600 / 60)} min"


def _mmss(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _fail(e):
    traceback.print_exc()
    raise gr.Error(str(e) or e.__class__.__name__)


def _need(st):
    if st is None:
        raise gr.Error("Please start again from step 1.")


def show(step):
    """Visibility for the five step panels."""
    return [gr.update(visible=(k == step)) for k in range(5)]


def unfinished_jobs():
    try:
        jobs = rp.list_jobs(jobs_root())
    except Exception:
        return []
    return [j for j in jobs if not j["final"]]


def job_choices():
    return [(f"{j['src']} ({_mmss(j['seconds'])}) - {j['done']} of {j['parts']} parts done",
             j["job_dir"]) for j in unfinished_jobs()]


# ---------------------------------------------------------------- drawing
def render(st, i, mask=None):
    img = cv2.imread(st["_video"][i])
    u = int(st["_unit_of"][i])
    tgt = os.path.join(st["cache"], "target", f"{i:06d}.png")
    if mask is None and st["_tracked"].get(u) is not None and os.path.exists(tgt):
        mask = cv2.imread(tgt, cv2.IMREAD_GRAYSCALE) > 127
    if mask is not None and mask.any():
        img[mask] = (0.45 * img[mask] + 0.55 * np.array([0, 220, 0])).astype(np.uint8)
    seed = rp.scene_seed(st, u)
    if seed is not None and seed[0] == i:
        b, t = seed[1], max(3, img.shape[1] // 300)
        cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 220, 0), t)
    s = min(1.0, MAX_VIEW / max(img.shape[:2]))
    st["_view_scale"] = s
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def scene_status(st, u):
    if u in st["seeds"]:
        if st["seeds"][u] is None:
            return "nobody kept"
        return "✔ found by photo" if st.get("seed_src", {}).get(u) == "photo" else "✔ your choice"
    a = (st["auto"] or {}).get(u)
    return "✘ not found - everyone removed" if a is None else "✔ found"


def gallery(st):
    items = []
    for u, (a, b, _) in enumerate(st["units"]):
        seed = rp.scene_seed(st, u)
        i = seed[0] if seed is not None else (a + b) // 2
        img = cv2.imread(st["_video"][i])
        if seed is not None:
            x1, y1, x2, y2 = map(int, seed[1])
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 0), max(4, img.shape[1] // 120))
        s = 360 / img.shape[1]
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        items.append((cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                      f"{rp.unit_label(st, u)} {scene_status(st, u)}"))
    return items


def _frame_note(st, i):
    s = i / rp.fps_float(st["fps"])
    return f"Time {_mmss(s)}  ·  {rp.unit_label(st, int(st['_unit_of'][i]))}"


# ---------------------------------------------------------------- step 1: choose video
def drive_inputs():
    """Videos and photos the user put in Google Drive > KeepOnePerson_input."""
    if not os.path.isdir(DRIVE_INPUT):
        return [], []
    files = sorted(os.listdir(DRIVE_INPUT))
    vids = [os.path.join(DRIVE_INPUT, f) for f in files if f.lower().endswith(VIDEO_EXT)]
    pics = [os.path.join(DRIVE_INPUT, f) for f in files if f.lower().endswith(PHOTO_EXT)]
    return vids, pics


def on_page():
    ch = job_choices()
    note = ("Your work is saved to Google Drive, so long videos can be continued later."
            if drive_ok() else "⚠️ Google Drive is not connected: if Colab disconnects, "
                               "work on long videos is lost.")
    if drive_ok():
        os.makedirs(DRIVE_INPUT, exist_ok=True)
    vids, pics = drive_inputs()
    found = (f"📁 **Found in your Google Drive** (folder *KeepOnePerson_input*): "
             f"{len(vids)} video(s) and {len(pics)} photo(s).") if vids else ""
    return (gr.update(visible=bool(ch)), gr.update(choices=ch, value=ch[0][1] if ch else None),
            note, gr.update(visible=bool(vids)), found,
            gr.update(choices=[(os.path.basename(v), v) for v in vids],
                      value=vids[0] if vids else None))


def on_use_drive(vid_path, quality, fill, start, end, progress=gr.Progress()):
    _, pics = drive_inputs()
    return on_next1(None, vid_path, quality, start, end, pics, fill, progress)


def on_next1(video, path, quality, start, end, photos=None, fill=None, progress=gr.Progress()):
    src = (path or "").strip() or video
    if not src or not os.path.exists(src):
        raise gr.Error("Please choose a video first.")
    if end and start and end <= start:
        raise gr.Error("The end time must be after the start time (or 0 for the whole video).")
    _progress_to(progress)
    try:
        preset = quality
        if quality == "Automatic":
            secs = rp.probe(src)[2] - (start or 0)
            if end:
                secs = min(secs, end - (start or 0))
            preset = "Best" if secs <= 180 else "Balanced"
        st = rp.create_job(src, jobs_root(), CACHE, start or 0, end or 0, preset, 0.25,
                           PART_SECONDS)
        st["fill"] = "fast" if (fill or "").startswith("Fast") else "realistic"
        rp.save_job(st)
        vid, img_pred, reid = models(preset)
        found = None
        if photos:
            rp.save_photos(st, photos)
            found = rp.anchors_from_photos(st, reid, img_pred)
            if found and found > 0:
                rp.find_person(st, reid, vid, img_pred)
    except Exception as e:
        _fail(e)
    counts = [len(b) for b in st["boxes"]]
    i = int(np.argmax(counts)) if max(counts) else 0
    if found and found > 0:  # photos worked: go straight to the scene check
        n_ok = sum(1 for u in range(len(st["units"])) if rp.scene_seed(st, u) is not None)
        head2 = (f"Using your photos, your person was found in **{n_ok} of {len(st['units'])}** "
                 "scene(s) (green box). In the others everyone is removed. **Wrong?** Click that "
                 "scene to fix it. **All good?** Press **Start**.")
        return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), "", _frame_note(st, i),
                gr.update(interactive=False), gallery(st), head2] + show(2)
    head = "**Click on the person you want to keep.** (Not in this picture? Use the arrows.)"
    if photos:
        head = ("The photos did not match anyone in the video clearly enough, so please "
                "**click on the person you want to keep.**" if found == 0 else
                "No face was found in the photos, so please **click on the person you want to keep.**")
    return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i), head,
            _frame_note(st, i), gr.update(interactive=False), gr.update(), gr.update()] + show(1)


# ---------------------------------------------------------------- step 2: pick the person
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
        mask = rp.set_keeper(st, img_pred, i, x, y)
    except Exception as e:
        _fail(e)
    if mask is None:
        return st, render(st, i), "No person there - please click directly on someone.", \
            gr.update(interactive=False)
    return st, render(st, i, mask), \
        "✅ **This person (green) will be kept.** Press **Next** - or click someone else to change.", \
        gr.update(interactive=True)


def on_next2(st, progress=gr.Progress()):
    _need(st)
    if len(st["shots"]) <= 1:  # one continuous scene: nothing to check, start right away
        st["_go"] = True
        return [st, gr.update(), ""] + show(3)
    _progress_to(progress)
    try:
        vid, img_pred, reid = models(st["preset"])
        rp.find_person(st, reid, vid, img_pred)
    except Exception as e:
        _fail(e)
    miss = sum(1 for u in range(len(st["units"])) if rp.scene_seed(st, u) is None)
    head = (f"Your video has **{len(st['shots'])} scenes**. The green box shows who is kept in each. "
            + (f"In {miss} scene(s) your person was not found, so everyone there is removed. "
               if miss else "")
            + "**Wrong?** Click that scene to fix it. **All good?** Press **Start**.")
    return [st, gallery(st), head] + show(2)


# ---------------------------------------------------------------- step 3: check scenes
def on_pick_scene(st, evt: gr.SelectData):
    _need(st)
    u = int(evt.index)
    seed = rp.scene_seed(st, u)
    a, b, _ = st["units"][u]
    i = seed[0] if seed is not None else (a + b) // 2
    st["_fix_unit"] = u
    return (gr.update(visible=True), render(st, i), gr.update(minimum=a, maximum=b - 1, value=i),
            f"**{rp.unit_label(st, u)}:** click the person to keep here, or press "
            "*Nobody to keep here*.")


def on_fix_click(st, i, evt: gr.SelectData):
    _need(st)
    i = int(i)
    x, y = evt.index[0] / st["_view_scale"], evt.index[1] / st["_view_scale"]
    try:
        _, img_pred, _ = models(st["preset"])
        mask = rp.set_keeper(st, img_pred, i, x, y, reset_search=False)
    except Exception as e:
        _fail(e)
    if mask is None:
        return st, gr.update(), render(st, i), "No person there - click directly on someone.", \
            gr.update()
    return st, gr.update(visible=False), render(st, i, mask), "Fixed ✔", gallery(st)


def on_nobody(st, i):
    _need(st)
    rp.set_absent(st, int(i), reset_search=False)
    return st, gr.update(visible=False), gallery(st)


# ---------------------------------------------------------------- step 4: work
def on_start(st, progress=gr.Progress()):
    _need(st)
    if not any(v is not None for v in st["seeds"].values()):
        raise gr.Error("Please click on the person to keep first.")
    _progress_to(progress)
    try:
        vid, img_pred, reid = models(st["preset"])
        out, chk = rp.remove_others(st, reid, vid, img_pred, PP_DIR, st.get("grow", 0.012))
    except Exception as e:
        _fail(e)
    where = (" A copy is in your Google Drive, folder **KeepOnePerson**." if drive_ok() else "")
    return [st, out, gr.update(value=out), gr.update(value=chk),
            "### ✅ Finished!" + where, WORK_NOTE] + show(4)


def on_maybe_start(st, progress=gr.Progress()):
    """Runs right after step 2 for one-scene videos (no scene check needed)."""
    if st is None or not st.pop("_go", False):
        return [gr.update()] * 6 + [gr.update()] * 5
    return on_start(st, progress)


def on_continue(job_dir, progress=gr.Progress()):
    if not job_dir:
        raise gr.Error("Choose the video to continue.")
    _progress_to(progress)
    try:
        st = rp.load_job(job_dir, CACHE)
        vid, img_pred, reid = models(st["preset"])
    except Exception as e:
        _fail(e)
    if not any(v is not None for v in st["seeds"].values()):
        counts = [len(b) for b in st["boxes"]]
        i = int(np.argmax(counts)) if max(counts) else 0
        return [st, render(st, i), gr.update(maximum=st["n"] - 1, value=i),
                "**Click on the person you want to keep.**", _frame_note(st, i),
                gr.update(interactive=False), None, gr.update(), gr.update(), "",
                WORK_NOTE] + show(1)
    try:
        out, chk = rp.remove_others(st, reid, vid, img_pred, PP_DIR, st.get("grow", 0.012))
    except Exception as e:
        _fail(e)
    where = (" A copy is in your Google Drive, folder **KeepOnePerson**." if drive_ok() else "")
    return [st, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), out,
            gr.update(value=out), gr.update(value=chk), "### ✅ Finished!" + where,
            WORK_NOTE] + show(4)


def on_restart():
    ch = job_choices()
    return [None, None, ""] + [gr.update(visible=bool(ch)), gr.update(choices=ch)] + show(0)


# ---------------------------------------------------------------- layout
WORK_NOTE = ("Keep this Colab tab open. The bar below shows what is happening and about how "
             "long is left. If Colab disconnects, start the notebook again and press **Continue**.")

CSS = """
.gradio-container {max-width: 980px !important; margin: auto;}
#big-title h1 {font-size: 2em; margin-bottom: 0;}
.step-head p {font-size: 1.15em;}
"""

with gr.Blocks(title="Keep One Person") as demo:
    state = gr.State(None)
    gr.Markdown("# 🎬 Keep One Person\nRemove everyone from a video except the person you choose.",
                elem_id="big-title")

    # step 0: choose video
    with gr.Column(visible=True) as p0:
        with gr.Group(visible=False) as resume_box:
            gr.Markdown("### ⏯ Continue an unfinished video")
            with gr.Row():
                resume_dd = gr.Dropdown(show_label=False, choices=[], scale=4)
                resume_btn = gr.Button("Continue", variant="primary", scale=1)
        gr.Markdown("### Step 1 of 3 - Choose your video", elem_classes="step-head")
        with gr.Group(visible=False) as drive_box:
            drive_md = gr.Markdown()
            with gr.Row():
                drive_dd = gr.Dropdown(show_label=False, choices=[], scale=4)
                drive_btn = gr.Button("Use these files ▶", variant="primary", scale=1)
        vid_in = gr.Video(label="Drop your video here, or click to choose a file", sources=["upload"],
                          height=260)
        photos_in = gr.File(label="Photos of the person to keep (optional - then the app finds "
                                  "them by itself)", file_count="multiple",
                            file_types=["image"], type="filepath")
        with gr.Accordion("More options", open=False):
            path_in = gr.Textbox(label="Video file on Google Drive (best for big files)",
                                 placeholder="/content/drive/MyDrive/my_video.mp4")
            quality_in = gr.Radio(QUALITY, value="Automatic", label="Quality",
                                  info="Automatic: Best for short videos, Balanced for long ones.")
            fill_in = gr.Radio(FILLS, value=FILLS[0], label="How to fill where people were",
                               info="Realistic paints in believable background (needs more time).")
            with gr.Row():
                start_in = gr.Number(label="Only from second", value=0, minimum=0)
                end_in = gr.Number(label="…to second (0 = to the end)", value=0, minimum=0)
        store_note = gr.Markdown()
        next1 = gr.Button("Next →", variant="primary", size="lg")

    # step 1: pick the person
    with gr.Column(visible=False) as p1:
        gr.Markdown("### Step 2 of 3 - Choose the person to keep", elem_classes="step-head")
        head1 = gr.Markdown()
        view = gr.Image(show_label=False, interactive=False, type="numpy")
        with gr.Row():
            back_btn = gr.Button("◀ 1 second back")
            note1 = gr.Markdown()
            fwd_btn = gr.Button("1 second forward ▶")
        frame_sl = gr.Slider(0, 1, value=0, step=1, label="Or drag to any moment")
        next2 = gr.Button("Next →", variant="primary", size="lg", interactive=False)

    # step 2: check scenes
    with gr.Column(visible=False) as p2:
        gr.Markdown("### Step 3 of 3 - Check each scene", elem_classes="step-head")
        head2 = gr.Markdown()
        gal = gr.Gallery(show_label=False, columns=4, fit_columns=False, object_fit="contain",
                         height="auto", allow_preview=False)
        with gr.Column(visible=False) as fix_box:
            fix_head = gr.Markdown()
            fix_view = gr.Image(show_label=False, interactive=False, type="numpy")
            fix_sl = gr.Slider(0, 1, value=0, step=1, label="Move within this scene")
            nobody_btn = gr.Button("Nobody to keep in this scene")
        start_btn = gr.Button("Start ▶", variant="primary", size="lg")

    # step 3: working (progress shows here)
    with gr.Column(visible=False) as p3:
        gr.Markdown("### Working on your video …", elem_classes="step-head")
        work_md = gr.Markdown(WORK_NOTE)
        go_btn = gr.Button("Try again ▶", size="sm")

    # step 4: done
    with gr.Column(visible=False) as p4:
        done_md = gr.Markdown()
        out_vid = gr.Video(show_label=False)
        dl_btn = gr.DownloadButton("⬇ Download the video", variant="primary", size="lg")
        chk_btn = gr.DownloadButton("Download the check video (red = removed, green = kept)",
                                    size="sm")
        new_btn = gr.Button("Start a new video")

    steps = [p0, p1, p2, p3, p4]

    demo.load(on_page, None, [resume_box, resume_dd, store_note, drive_box, drive_md, drive_dd])
    n1_outs = [state, view, frame_sl, head1, note1, next2, gal, head2] + steps
    next1.click(on_next1, [vid_in, path_in, quality_in, start_in, end_in, photos_in, fill_in],
                n1_outs)
    drive_btn.click(on_use_drive, [drive_dd, quality_in, fill_in, start_in, end_in], n1_outs)
    back_btn.click(lambda st, i: on_move(st, i, -1), [state, frame_sl], [view, frame_sl, note1])
    fwd_btn.click(lambda st, i: on_move(st, i, +1), [state, frame_sl], [view, frame_sl, note1])
    frame_sl.release(on_slide, [state, frame_sl], [view, note1])
    view.select(on_click, [state, frame_sl], [state, view, head1, next2])
    run_outs = [state, out_vid, dl_btn, chk_btn, done_md, work_md] + steps
    next2.click(on_next2, [state], [state, gal, head2] + steps).then(
        on_maybe_start, [state], run_outs)
    gal.select(on_pick_scene, [state], [fix_box, fix_view, fix_sl, fix_head])
    fix_sl.release(lambda st, i: render(st, int(i)), [state, fix_sl], [fix_view])
    fix_view.select(on_fix_click, [state, fix_sl], [state, fix_box, fix_view, fix_head, gal])
    nobody_btn.click(on_nobody, [state, fix_sl], [state, fix_box, gal])
    start_btn.click(lambda: show(3), None, steps).then(on_start, [state], run_outs)
    go_btn.click(on_start, [state], run_outs)
    resume_btn.click(lambda: show(3), None, steps).then(
        on_continue, [resume_dd],
        [state, view, frame_sl, head1, note1, next2, out_vid, dl_btn, chk_btn, done_md,
         work_md] + steps)
    new_btn.click(on_restart, None, [state, vid_in, path_in, resume_box, resume_dd] + steps)

if __name__ == "__main__":
    demo.queue().launch(share=True, debug=True, css=CSS, allowed_paths=[CACHE, DRIVE_JOBS])
