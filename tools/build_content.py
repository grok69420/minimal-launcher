#!/usr/bin/env python3
"""Builds the library the app downloads: base content.json + patches/*.json (applied in file-name
order), validated strictly, stamped with a rising revision. Exits non-zero on any problem, so a
bad edit is never signed or published.

Collections: modules, lessons, cases, gaps, stories, traps, quiz, updates, glossary, palettes
(palettes = brand mood boards; each swatch must say whether its value is published or approximated).

Patch format (written by the daily update task). Upserts are shallow-merged into the existing
document with that id, so app-only fields such as a lesson's "plain" summary survive.
{
  "date": "2026-11-26",
  "upserts": [ {"c": "updates", "id": "u-2026-11-26-x", "data": { ...full document... }} ],
  "meta": {"lastChecked": "2026-11-26"}            # optional
}
"""
import glob, json, os, re, sys, time

COLLS = ["modules", "lessons", "cases", "gaps", "stories", "traps", "quiz", "updates", "glossary", "palettes"]
REQ = {
    "modules": ["title", "vol", "order"], "lessons": ["module", "title", "summary", "body"],
    "cases": ["name", "court", "module", "held"], "gaps": ["title", "module", "status", "gap", "closed"],
    "stories": ["name", "kind", "outcome", "what", "lesson"], "traps": ["clause", "risk", "ask"],
    "quiz": ["module", "q", "opts", "a", "why"], "updates": ["date", "kind", "module", "title", "summary"],
    "glossary": ["term", "plain", "aliases"],
    "palettes": ["brand", "title", "swatches", "basis"],
}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
errors = []

def err(msg): errors.append(msg)

def links(v):
    if v is None: return []
    return v if isinstance(v, list) else [v]

def main(base_path, patch_dir, out_path):
    lib = json.load(open(base_path, encoding="utf-8"))
    for c in COLLS: lib.setdefault(c, [])
    for p in sorted(glob.glob(os.path.join(patch_dir, "*.json"))):
        try:
            patch = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            err(f"{p}: not valid JSON ({e})"); continue
        for u in patch.get("upserts", []):
            c, i, d = u.get("c"), u.get("id"), u.get("data")
            if c not in COLLS or not isinstance(i, str) or not i or not isinstance(d, dict):
                err(f"{p}: bad upsert {str(u)[:120]}"); continue
            d = dict(d); d["id"] = i
            items = lib[c]
            for k, old in enumerate(items):
                # Shallow merge: fields the patch leaves out (e.g. the app-only "plain" summary) are kept.
                if old.get("id") == i: items[k] = {**old, **d}; break
            else: items.append(d)
        if isinstance(patch.get("meta"), dict):
            lib.setdefault("meta", {}).update(patch["meta"])

    mods = {m.get("id") for m in lib["modules"]}
    for c in COLLS:
        seen = set()
        for d in lib[c]:
            i = d.get("id")
            if not i or i in seen: err(f"{c}: missing or duplicate id {i}")
            seen.add(i)
            for f in REQ[c]:
                if d.get(f) in (None, "", []): err(f"{c}/{i}: missing {f}")
            if c != "modules" and "module" in d and d["module"] not in mods: err(f"{c}/{i}: unknown module {d['module']}")
            for l in links(d.get("src")) + links(d.get("sources")):
                if not isinstance(l, dict) or not str(l.get("u", "")).startswith("https://"): err(f"{c}/{i}: link must be https: {l}")
        if c == "quiz":
            for d in lib[c]:
                if not isinstance(d.get("opts"), list) or not isinstance(d.get("a"), int) or not 0 <= d["a"] < len(d["opts"]):
                    err(f"quiz/{d.get('id')}: answer index out of range")
        if c == "palettes":
            for d in lib[c]:
                for sw in d.get("swatches") or []:
                    if not isinstance(sw, dict) or not HEX.match(str(sw.get("hex", ""))) or not sw.get("name") or not sw.get("basis"):
                        err(f"palettes/{d.get('id')}: every swatch needs a name, a #RRGGBB hex and a basis: {sw}")
        if c == "updates":
            for d in lib[c]:
                if not DATE.match(str(d.get("date", ""))): err(f"updates/{d.get('id')}: date must be YYYY-MM-DD")
    if not DATE.match(str(lib.get("meta", {}).get("lastChecked", ""))): err("meta.lastChecked must be YYYY-MM-DD")
    for c, n in {"modules": 8, "lessons": 30, "cases": 15, "quiz": 20, "glossary": 100}.items():
        if len(lib[c]) < n: err(f"{c}: only {len(lib[c])} items; refusing to publish a shrunken library")

    # Source-quality checks (audit 25 Nov 2026). Warnings by default; set STRICT=1 to block publishing on them.
    warns = []
    for c in ("cases", "gaps", "lessons"):
        for d in lib[c]:
            ls = links(d.get("src")) + links(d.get("sources"))
            if not ls: warns.append(f"{c}/{d.get('id')}: no source link")
            for l in ls:
                if isinstance(l, dict) and "indiankanoon.org/search" in str(l.get("u", "")):
                    warns.append(f"{c}/{d.get('id')}: links to an Indian Kanoon search page, not the judgment")
            if c == "cases" and not str(d.get("citation", "")).strip():
                warns.append(f"cases/{d.get('id')}: no citation")
            if "verified" in d and not DATE.match(str(d["verified"])):
                err(f"{c}/{d.get('id')}: verified must be YYYY-MM-DD")
    # Freshness report (informational, never blocks): when each case/loophole/lesson was last checked.
    today = time.strftime("%Y-%m-%d")
    def age(v):
        y, m, dd = map(int, v.split("-")); ty, tm, td = map(int, today.split("-"))
        return (ty - y) * 365 + (tm - m) * 30 + (td - dd)
    unchecked, stale, pend = 0, [], []
    for c in ("cases", "gaps", "lessons"):
        for d in lib[c]:
            v = d.get("verified")
            if not v or not DATE.match(str(v)): unchecked += 1; continue
            if age(v) > 183: stale.append(f"{c}/{d.get('id')} ({v})")
            st = str(d.get("status", "")).lower()
            if any(k in st for k in ("pending", "ongoing", "under appeal")) and age(v) > 92: pend.append(f"{c}/{d.get('id')} ({v})")
    total = sum(len(lib[c]) for c in ("cases", "gaps", "lessons"))
    print(f"Freshness: {total - unchecked}/{total} cases+loopholes+lessons have a verified date; {len(stale)} older than 6 months; {len(pend)} pending items not re-checked in 3 months")
    for s in stale + pend: print("  ! re-check", s)

    if warns:
        print(f"Source warnings ({len(warns)}):"); [print("  ~", w) for w in warns]
        if os.environ.get("STRICT") == "1": errors.extend(warns)

    if errors:
        print("Library did not validate:"); [print("  -", e) for e in errors]; sys.exit(1)

    out = {"schema": 1, "rev": int(os.environ.get("REV") or time.time()), "meta": lib.get("meta", {})}
    for c in COLLS: out[c] = lib[c]
    data = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if len(data.encode()) > 4 * 1024 * 1024: print("Library too large"); sys.exit(1)
    open(out_path, "w", encoding="utf-8").write(data)
    print("OK rev", out["rev"], {c: len(out[c]) for c in COLLS}, "lastChecked", out["meta"].get("lastChecked"))

if __name__ == "__main__":
    main(*sys.argv[1:4])
