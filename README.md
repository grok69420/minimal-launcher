# Keep One Person

Remove people from a video as if they had never been there. Two ways:
- **Keep one person** - everyone else is removed (optionally found from photos of the person).
- **Remove some people** - click the people to remove; everyone else stays.

The sound stays as it was. Runs in Google Colab (an A100 GPU with Colab Pro is recommended).

**Start:** open
[Keep_One_Person.ipynb in Colab](https://colab.research.google.com/github/grok69420/minimal-launcher/blob/keep-one-person/Keep_One_Person.ipynb)
and press the ▶ play button, then upload your video in the app. The notebook always downloads the latest version of the program
from this branch.

## Google Drive
- `Keep One Person/` - optional: put your video and photos here instead of uploading them in the app
- `Keep One Person/Finished/` - finished videos and check videos appear here
- `Keep One Person/Feedback/` - your corrections (the app learns from them)
- `Keep One Person/In progress (automatic)/` - work in progress; long videos are processed in
  parts of about 90 seconds, so an interrupted job can be continued from the app

## Fixing a result
When a video is finished the app asks **Is it right?** Press **No, fix something**, move the
slider to the problem, choose what is wrong (a person is still there, smudged, outline
visible, wrong person) and click on the spot. **Redo with these fixes** redoes only the
affected parts. Every correction is saved in `Keep One Person/Feedback/` and new videos start
with settings adjusted to the problems you reported most.

## Better (between Fast and Film quality)
Choose **Better** under *Speed* when the video has crowds. The film painter (SVOR, see below)
paints every 3rd frame and the frames between follow the camera.

Measured on a 42-second crowded section of a music video (about 10 people per picture, Colab
L4 GPU), counting the people a detector still sees in the finished video beyond the kept one:

| Level | Extra people seen | Pictures with an extra person | Time (L4) |
|---|---|---|---|
| Fast | 65 | 26.8% | 4.7 min |
| Better | 23 | 11.9% | 28.9 min |

So about two thirds fewer left-over or painted-in people, for about 6 times the time. The
times are from an L4; on an A100 this level has not been timed yet.

## Film quality
Choose **Film quality** under *Speed* for the best result. It takes much longer than the
15-minute automatic setting: measured on a Colab A100, one minute of a crowded music video
took 28 minutes (so a 4.6-minute video takes about 2 hours).
- **SVOR** (Xiaomi, winner of the CVPR 2026 video object removal challenge) paints the
  background. It also removes the shadows and reflections people leave, and copes with masks
  that miss a hand or a foot. On a crowded stage it gives an empty stage instead of the
  person-shaped smudges of the quick painter.
- SVOR also fades out people it was not asked to remove when they stand next to removed ones,
  so a band around the kept person is painted again by a painter that keeps everything
  outside its mask - no halos or outlines around the kept person.
- **Real background**: where the background behind a removed person can be seen in other
  frames of the shot, those real pixels are moved along with the camera and used.
- Every painted piece is checked for person-like figures the painter made up; such pieces
  are painted again (best of three), and the self-check always repairs left-over people.
- Small people in wide crowd shots are found with a second look at the frame in four
  enlarged tiles; the most accurate tracking model (SAM 2.1 large) follows the kept person;
  the kept person gets a soft, picture-guided edge (hair); the painted areas get the video's
  own grain.

## How it works
Scene cuts are detected; every chosen person is recognised again in each scene (face and
clothing); SAM 2 tracks people pixel-accurately. Removed areas are filled in two ways:
- **Steady camera** (tripod, interview, presentation): the empty background is assembled
  from the moments each spot was uncovered - sharp, no flicker, and fast. Spots that were
  never uncovered are painted by AI.
- **Moving camera**: AI-generated background (MiniMax-Remover at its own size, 832x480 - smaller
  sizes made a checkerboard pattern; ProPainter as the fallback). The faster levels paint every
  2nd, 3rd or 4th frame; the frames between are the painted frames moved along with the camera
  (measured on the background), then cross-faded - no smearing.

**Finding people:** the scan looks at every frame at 1280 pixels and keeps people who overlap
in crowds; on 7 sample frames of a crowded music video it found 184 people where the previous
version found 100.

**Speed (measured on a Colab A100, 4.6-minute music video with up to 30+ dancers):** 12.5
minutes of processing (scan 2.3 min, finding the person 1.3 min, removing and painting 8.9
min, three parts at a time). Add starting Colab, the setup and the upload: the app opens
while the AI models are still downloading, and the scan starts as soon as the upload is
finished. The background painting level is chosen automatically so the processing takes
about 12 minutes; choose *Sharpest background* under More options for every frame painted
with extra care (takes longer).

**Smaller GPUs:** when Colab has no A100 free it connects an L4 instead. The app works there
(the scan now uses smaller batches when GPU memory is short, and the film painter works on one
part at a time unless about 34 GB are free), but everything takes several times longer.

**Limits:** where a crowd covers the background in every frame of a shot, there is no real
background to recover - the painted area is invented and looks soft there. Steady shots and
shots with a few people come out much cleaner.

After each part a **self-check** looks for people who should be gone and fixes the part once
automatically; anything still found is pointed out on the finished screen. Everything else
keeps the original pixels, resolution and audio. The finished screen shows how long each
step took.

Engines: YOLO11, SAM 2.1, InsightFace, MiniMax-Remover (with the TAEHV tiny decoder),
SVOR on Wan2.1-VACE (film quality), ProPainter.

## Files
- `Keep_One_Person.ipynb` - one-button Colab notebook
- `app.py` - the step-by-step web app (Gradio)
- `remove_people.py` - the processing engine

## Licences of the components
- MiniMax-Remover model: CC BY-NC 4.0 - non-commercial use only.
- ProPainter: S-Lab License 1.0 - non-commercial use only.
- InsightFace pretrained face models: non-commercial research use only.
- Ultralytics YOLO11: AGPL-3.0.
- SAM 2: Apache 2.0.
- SVOR: code Apache 2.0 (removal weights: see huggingface.co/HigherHu/SVOR); it runs on
  Wan2.1-VACE-1.3B (Apache 2.0).
- TAEHV (tiny decoder): MIT.

Commercial use of videos made with this tool would need commercial licences for these
components.
