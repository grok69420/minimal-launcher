# Keep One Person

Remove everyone from a video except the person you choose. Runs in Google Colab (free GPU).

**Start:** open
[Keep_One_Person.ipynb in Colab](https://colab.research.google.com/github/grok69420/minimal-launcher/blob/keep-one-person/Keep_One_Person.ipynb)
and press the ▶ play button. The notebook always downloads the latest version of the
program from this branch.

## How it works
1. Choose a video (upload, or a path on Google Drive for big files).
2. Click the person to keep.
3. For videos with several scenes, check that the right person is marked in each scene.
4. The video is processed in parts of about 90 seconds; each finished part is saved to
   Google Drive (folder `KeepOnePerson`), so an interrupted job can be continued.

Photos: put the video and some photos of the person in Google Drive, folder
`KeepOnePerson_input` - the app finds the person by face in every scene by itself.

Engines: YOLO11 (person detection), SAM 2.1 (tracking and segmentation),
InsightFace (recognising the person), MiniMax-Remover (realistic, AI-generated
background - default) and ProPainter (fast fill, also used automatically if the
realistic fill cannot run).

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
