# Startup Law Library — content

The library the Android app downloads when it is online.

- `content.json` — base library (all collections).
- `patches/*.json` — daily additions and corrections, applied in file-name order. Each upsert replaces the whole document with that id.
- `tools/build_content.py` — merges, validates (ids, required fields, module references, quiz answers, https links, no shrinking) and stamps a rising `rev`.
- The workflow signs the result with the app's release key and publishes `content.json` + `content.json.sig` to the `startup-law-content` release. The app accepts it only if the signature matches its own signing key and the revision is newer than what it already has.

## Source rules (enforced in CI since 25 Nov 2026, `STRICT=1`)
Every case, loophole and lesson needs at least one https source. Cases need a `citation`. Link to the judgment itself (`indiankanoon.org/doc/<id>/`, sci.gov.in, a High Court site or an official PDF), never to an Indian Kanoon search page. Statutes: link India Code, RBI, DPIIT, PIB or the Income Tax Department. A patch that breaks these rules fails the build and is not published. Run `STRICT=1 python3 tools/build_content.py content.json patches /tmp/out.json` before pushing.
