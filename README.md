# India cyclone tracker

A free, self-updating tracker for cyclones in the North Indian Ocean (Bay of Bengal and Arabian Sea).
Every hour a GitHub Actions job downloads the latest **IMD (RSMC New Delhi)** advisory and the **JTWC**
North Indian Ocean warnings, builds an equal-weight consensus track, finds the landfall point and
distances to coastal places, and publishes the map to GitHub Pages.

It costs nothing to run on a public GitHub repository, and it uses no Claude credits.

## Setup (about 10 minutes, once)

1. On GitHub, create a new **public** repository, for example `india-cyclone-tracker`. Leave it empty.
2. Upload everything in this folder: **Add file → Upload files**, then drag in the whole folder contents.
   Check that `.github/workflows/update.yml` arrived. Some computers hide folders starting with a dot.
   If it is missing, use **Add file → Create new file**, type `.github/workflows/update.yml` as the name and paste the file's contents.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. **Settings → Actions → General → Workflow permissions: Read and write permissions → Save.**
5. **Actions** tab → **Update cyclone data** → **Run workflow**. The first run takes about 1–2 minutes.
6. Your tracker is at `https://<your-username>.github.io/<repo-name>/`.

After that it runs on its own every hour at about :17 past the hour (UTC). GitHub sometimes starts scheduled runs a few minutes late.

## What is in here

| Path | What it does |
|---|---|
| `scripts/update.py` | Fetches IMD + JTWC, parses them, computes consensus, landfall and distances, and writes `docs/data/*.json` |
| `scripts/places.json` | Reference places and your **watch list** (shown first in the distance table). Edit freely |
| `scripts/land_region.geojson` | Coastline used for landfall detection |
| `scripts/build_static.py` | One-off builder for the map coastline files. Not needed for normal use |
| `docs/index.html` | The tracker page. It reloads the data every 15 minutes |
| `docs/data/latest.json` | Current storms (seeded with Cyclone Akvan, 18 Nov 2026) |
| `docs/data/history.json` | Observed positions collected run by run, drawn as the past track |
| `.github/workflows/update.yml` | Hourly schedule, commit of changed data, Pages deploy |
| `tests/` | Offline parser tests with sample bulletins |

## How the consensus works

* IMD and JTWC tracks are interpolated to a common 6-hour clock and averaged with equal weight.
* Only the track is averaged. IMD winds are 3-minute averages and JTWC winds are 1-minute averages, so they are shown side by side, not averaged.
* The grey band is half the IMD–JTWC separation. It shows agency disagreement and is not a probability cone.
* If only one agency has a forecast, that track is shown without a consensus.

## When something breaks

* The **Data status** box on the page shows whether each source updated, kept its previous data, or failed, with the error text.
* A source that fails keeps its last good data, so the page never goes blank because one site is down.
* The most likely break is IMD changing the layout of its advisory PDF, or a site blocking automated downloads.
  Copy the error from Data status (or from the failed run in the Actions tab) and ask for a parser fix.

## Run it yourself

```
pip install -r requirements.txt
python tests/test_parse.py                 # offline tests
python scripts/update.py                   # live fetch, writes docs/data/
python -m http.server -d docs 8000         # open http://localhost:8000
```

## Limits

* This is an unofficial aggregation of public bulletins. For warnings and decisions use IMD and state disaster management (e.g. APSDMA) bulletins.
* Place coordinates are approximate. Distance bands (near core / strong winds / rain bands) are a rule of thumb, not official wind radii.
* GitHub pauses scheduled workflows after 60 days without commits. The workflow makes a small heartbeat commit each month to prevent this.

Coastline data: Natural Earth (public domain), via world-atlas 2.0.2.
