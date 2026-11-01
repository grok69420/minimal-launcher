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
- `Keep One Person/In progress (automatic)/` - work in progress; long videos are processed in
  parts of about 90 seconds, so an interrupted job can be continued from the app

## How it works
Scene cuts are detected; every chosen person is recognised again in each scene (face and
clothing); SAM 2 tracks people pixel-accurately; the removed areas are filled with
AI-generated background (MiniMax-Remover, zoomed in on small areas for sharpness; ProPainter
as the fast or fallback fill); everything else keeps the original pixels, resolution and audio.

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
