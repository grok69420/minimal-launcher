# Keep One Person

Remove people from a video as if they had never been there. Two ways:
- **Keep one person** - everyone else is removed (optionally found from photos of the person).
- **Remove some people** - click the people to remove; everyone else stays.

The sound stays as it was. Runs in Google Colab (an A100 GPU with Colab Pro is recommended).

**Start:** open
[Keep_One_Person.ipynb in Colab](https://colab.research.google.com/github/grok69420/minimal-launcher/blob/keep-one-person/Keep_One_Person.ipynb)
and press the ▶ play button. The notebook always downloads the latest version of the program
from this branch.

## Google Drive
- `Keep One Person/` - put your video (and photos of the person to keep) here
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

## How it works
Scene cuts are detected; every chosen person is recognised again in each scene (face and
clothing); SAM 2 tracks people pixel-accurately. Removed areas are filled in two ways:
- **Steady camera** (tripod, interview, presentation): the empty background is assembled
  from the moments each spot was uncovered - sharp, no flicker, and fast. Spots that were
  never uncovered are painted by AI.
- **Moving camera**: AI-generated background (MiniMax-Remover, zoomed in on small areas for
  sharpness; ProPainter as the fast or fallback fill).

After each part a **self-check** looks for people who should be gone and fixes the part once
automatically; anything still found is pointed out on the finished screen. Everything else
keeps the original pixels, resolution and audio. The finished screen shows how long each
step took.

Engines: YOLO11, SAM 2.1, InsightFace, MiniMax-Remover, ProPainter.

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

Commercial use of videos made with this tool would need commercial licences for these
components.
