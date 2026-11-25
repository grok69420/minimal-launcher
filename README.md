# Startup Law Library — content

The library the Android app downloads when it is online.

- `content.json` — base library (all collections).
- `patches/*.json` — daily additions and corrections, applied in file-name order. Each upsert replaces the whole document with that id.
- `tools/build_content.py` — merges, validates (ids, required fields, module references, quiz answers, https links, no shrinking) and stamps a rising `rev`.
- The workflow signs the result with the app's release key and publishes `content.json` + `content.json.sig` to the `startup-law-content` release. The app accepts it only if the signature matches its own signing key and the revision is newer than what it already has.
