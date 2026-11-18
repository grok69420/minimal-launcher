#!/usr/bin/env python3
"""Hourly updater for the North Indian Ocean cyclone tracker.

Fetches the latest IMD (RSMC New Delhi) tropical cyclone advisory PDF and JTWC
North Indian Ocean warnings, parses positions and forecasts, builds an
equal-weight consensus track, finds landfall and distances to reference places,
and writes docs/data/latest.json, docs/data/history.json and docs/data/status.json.

If a source cannot be fetched or parsed, its last good data is kept and the
error is recorded in status.json. The job never fails because a source is down.

Offline test:  python scripts/update.py --imd-text FILE --jtwc-text FILE --now 2026-11-18T09:00Z
"""
import argparse, io, json, math, os, re, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
UTC = timezone.utc

IMD_PAGE = "https://mausam.imd.gov.in/imd_latest/contents/cyclone.php"
IMD_BASE = "https://mausam.imd.gov.in/"
JTWC_RSS = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
JTWC_TXT = "https://www.metoc.navy.mil/jtwc/products/{sid}web.txt"
UA = {"User-Agent": "india-cyclone-tracker/1.0 (+GitHub Actions; hourly)"}

# IMD classification by maximum sustained wind (km/h, 3-minute average)
IMD_CLASSES = [(222, "Super Cyclonic Storm"), (167, "Extremely Severe Cyclonic Storm"),
               (118, "Very Severe Cyclonic Storm"), (89, "Severe Cyclonic Storm"),
               (62, "Cyclonic Storm"), (50, "Deep Depression"), (31, "Depression")]


def imd_class(kmh):
    for lo, name in IMD_CLASSES:
        if kmh >= lo:
            return name
    return "Low pressure area"


def iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


# ---------------------------------------------------------------- IMD
IMD_ROW = re.compile(
    r"(\d{2})\.(\d{2})\.(\d{2,4})\s*/\s*(\d{4})\s+"          # 18.11.26/0600
    r"(\d{1,2}\.\d{1,2})\s*/\s*(\d{2,3}\.\d{1,2})\s+"         # 13.1/85.4
    r"(\d{2,3})\s*[-–]\s*(\d{2,3})"                          # 90-100
    r"(?:\s*gusting\s*to\s*(\d{2,3}))?", re.I)
IMD_NAME = re.compile(r"(?:Cyclonic Storm|Cyclone)\s*[\"“”']\s*([A-Z][A-Za-z]+)\s*[\"“”']", re.I)


def parse_imd(text, is_ist=False):
    """Return dict with forecast rows from an IMD advisory/bulletin text."""
    flat = re.sub(r"\s+", " ", text)
    rows, seen = [], set()
    for m in IMD_ROW.finditer(flat):
        d, mo, y, hm, la, lo, w1, w2, g = m.groups()
        y = int(y) + (2000 if len(y) == 2 else 0)
        t = datetime(y, int(mo), int(d), int(hm[:2]), int(hm[2:]), tzinfo=UTC)
        if is_ist:
            t -= timedelta(hours=5, minutes=30)
        lat, lon, lo_w, hi_w = float(la), float(lo), int(w1), int(w2)
        if not (0 < lat < 35 and 40 < lon < 105) or lo_w > hi_w:
            continue
        key = iso(t)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"time": key, "lat": lat, "lon": lon, "kmh": [lo_w, hi_w],
                     "gust": int(g) if g else None, "cls": imd_class(hi_w)})
    rows.sort(key=lambda r: r["time"])
    nm = IMD_NAME.search(flat)
    return {"name": nm.group(1).capitalize() if nm else None, "track": rows}


def fetch_imd(session):
    html = session.get(IMD_PAGE, headers=UA, timeout=60).text
    links = set(re.findall(r"(backend/assets/cyclone_pdf/[^\"'<> ]+?\.pdf)", html, re.I))
    if not links:
        return None, None, "no advisory PDF linked on the IMD cyclone page"

    def rank(u):  # prefer RSMC advisories (UTC tables); newest by number in name
        n = re.findall(r"(?:no[_.\s]*|No[_.\s]*)(\d+)", u, re.I)
        return ("advisory" in u.lower(), int(n[0]) if n else 0, u)
    url = IMD_BASE + sorted(links, key=rank)[-1].replace(" ", "%20")
    import pdfplumber
    pdf = session.get(url, headers=UA, timeout=90).content
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages)
    is_ist = "advisory" not in url.lower() and "(IST)" in text
    return url, parse_imd(text, is_ist), None


# ---------------------------------------------------------------- JTWC
JT_POS = re.compile(r"(\d{2})(\d{2})(\d{2})Z\s*---\s*(?:NEAR\s+)?(\d{1,2}\.\d)([NS])\s+(\d{2,3}\.\d)([EW])")
JT_WIND = re.compile(r"MAX SUSTAINED WINDS\s*-\s*(\d{2,3})\s*KT")
JT_SUBJ = re.compile(r"TROPICAL CYCLONE\s+(\d{2}[AB])\s*\(([A-Z0-9\- ]+)\)\s*WARNING\s+NR\s+(\d+)")
JT_HEAD = re.compile(r"WTIO\d\d\s+PGTW\s+(\d{2})(\d{2})(\d{2})")


def _jt_time(day, hh, mm, now):
    """JTWC gives DDHHMMZ only; take the month that puts it nearest to now."""
    best = None
    for dm in (-1, 0, 1):
        y, m = now.year, now.month + dm
        if m == 0: y, m = y - 1, 12
        if m == 13: y, m = y + 1, 1
        try:
            t = datetime(y, m, day, hh, mm, tzinfo=UTC)
        except ValueError:
            continue
        if best is None or abs((t - now).total_seconds()) < abs((best - now).total_seconds()):
            best = t
    return best


def parse_jtwc(text, now):
    body = text.split("REMARKS:")[0]
    subj = JT_SUBJ.search(text)
    head = JT_HEAD.search(text)
    pos = list(JT_POS.finditer(body))
    if not pos:
        return None
    pts = []
    for i, m in enumerate(pos):
        dd, hh, mi, la, ns, lo, ew = m.groups()
        seg = body[m.end(): pos[i + 1].start() if i + 1 < len(pos) else len(body)]
        w = JT_WIND.search(seg)
        lat = float(la) * (1 if ns == "N" else -1)
        lon = float(lo) * (1 if ew == "E" else -1)
        pts.append({"time": iso(_jt_time(int(dd), int(hh), int(mi), now)), "lat": lat, "lon": lon,
                    "kt": int(w.group(1)) if w else None})
    issued = iso(_jt_time(int(head.group(1)), int(head.group(2)), int(head.group(3)), now)) if head else None
    return {"id": subj.group(1) if subj else None,
            "name": subj.group(2).strip().capitalize() if subj else None,
            "warning": int(subj.group(3)) if subj else None, "issued": issued,
            "fix": pts[0], "track": pts}


def fetch_jtwc(session, now):
    ids = set()
    try:
        rss = session.get(JTWC_RSS, headers=UA, timeout=60).text
        ids |= set(re.findall(r"(io\d{4})web\.txt", rss, re.I))
    except Exception:
        pass
    if not ids:  # fallback: probe this year's storm numbers
        yy = now.strftime("%y")
        for n in range(1, 13):
            sid = f"io{n:02d}{yy}"
            try:
                r = session.get(JTWC_TXT.format(sid=sid), headers=UA, timeout=30)
                if r.ok and "WTIO" in r.text:
                    ids.add(sid)
            except Exception:
                continue
    out = []
    for sid in sorted(i.lower() for i in ids):
        url = JTWC_TXT.format(sid=sid)
        r = session.get(url, headers=UA, timeout=60)
        if r.ok:
            w = parse_jtwc(r.text, now)
            if w:
                w["url"] = url
                out.append(w)
    return out


# ---------------------------------------------------------------- geometry
def hav(a, b):
    R, r = 6371.0, math.pi / 180
    dp, dl = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    x = math.sin(dp / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def interp(track, t):
    ts = [parse_iso(p["time"]) for p in track]
    if not track or t < ts[0] or t > ts[-1]:
        return None
    for i in range(len(track) - 1):
        if ts[i] <= t <= ts[i + 1]:
            span = (ts[i + 1] - ts[i]).total_seconds()
            f = (t - ts[i]).total_seconds() / span if span else 0
            a, b = track[i], track[i + 1]
            return (a["lat"] + f * (b["lat"] - a["lat"]), a["lon"] + f * (b["lon"] - a["lon"]))
    return (track[-1]["lat"], track[-1]["lon"])


def consensus(imd_tr, jt_tr):
    """Equal-weight average on a 6-hourly grid where both tracks overlap."""
    if not imd_tr or not jt_tr:
        one = imd_tr or jt_tr
        return [{"time": p["time"], "lat": p["lat"], "lon": p["lon"], "sep_km": None, "single": True} for p in one]
    t0 = max(parse_iso(imd_tr[0]["time"]), parse_iso(jt_tr[0]["time"]))
    t1 = min(parse_iso(imd_tr[-1]["time"]), parse_iso(jt_tr[-1]["time"]))
    first = t0.replace(minute=0, second=0) - timedelta(hours=t0.hour % 6) + timedelta(hours=6)
    grid = [t0]
    g = first
    while g <= t1:
        grid.append(g)
        g += timedelta(hours=6)
    out = []
    for g in grid:
        a, b = interp(imd_tr, g), interp(jt_tr, g)
        if a and b:
            out.append({"time": iso(g), "lat": round((a[0] + b[0]) / 2, 2), "lon": round((a[1] + b[1]) / 2, 2),
                        "imd": [round(a[0], 2), round(a[1], 2)], "jtwc": [round(b[0], 2), round(b[1], 2)],
                        "sep_km": round(hav(a, b))})
    return out


_LAND = None


def land():
    global _LAND
    if _LAND is None:
        from shapely.geometry import shape
        _LAND = shape(json.load(open(os.path.join(ROOT, "scripts", "land_region.geojson"))))
    return _LAND


def landfall(track):
    from shapely.geometry import LineString, Point
    L = land()
    for a, b in zip(track, track[1:]):
        pa = Point(a["lon"], a["lat"])
        if L.contains(pa):
            continue
        seg = LineString([(a["lon"], a["lat"]), (b["lon"], b["lat"])])
        hit = seg.intersection(L.boundary)
        if hit.is_empty:
            continue
        pts = [hit] if hit.geom_type == "Point" else [g for g in getattr(hit, "geoms", []) if g.geom_type == "Point"]
        if not pts:
            continue
        p = min(pts, key=pa.distance)
        f = pa.distance(p) / seg.length
        ta, tb = parse_iso(a["time"]), parse_iso(b["time"])
        return {"lat": round(p.y, 2), "lon": round(p.x, 2), "time": iso(ta + (tb - ta) * f)}
    return None


def closest(track, place):
    best = None
    for a, b in zip(track, track[1:]):
        ta, tb = parse_iso(a["time"]), parse_iso(b["time"])
        for k in range(61):
            f = k / 60
            q = (a["lat"] + f * (b["lat"] - a["lat"]), a["lon"] + f * (b["lon"] - a["lon"]))
            d = hav(q, place)
            if best is None or d < best[0]:
                best = (d, ta + (tb - ta) * f)
    return {"km": round(best[0]), "time": iso(best[1])} if best else None


# ---------------------------------------------------------------- main
def load(name, default):
    try:
        return json.load(open(os.path.join(DATA, name)))
    except Exception:
        return default


def save(name, obj):
    with open(os.path.join(DATA, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def in_region(lat, lon):  # North Indian Ocean (Bay of Bengal + Arabian Sea)
    return 0 <= lat <= 30 and 45 <= lon <= 100


def build(imd, imd_url, jtwc_list, prev, history, now):
    places = json.load(open(os.path.join(ROOT, "scripts", "places.json")))
    storms = []
    jt_left = [w for w in jtwc_list if in_region(w["fix"]["lat"], w["fix"]["lon"])]
    imd_tr = imd["track"] if imd and imd["track"] else []
    # match IMD system to nearest JTWC system (within 600 km of IMD's first point)
    match = None
    if imd_tr:
        cands = [(hav((imd_tr[0]["lat"], imd_tr[0]["lon"]), (w["fix"]["lat"], w["fix"]["lon"])), w) for w in jt_left]
        cands = [c for c in cands if c[0] < 600]
        if cands:
            match = min(cands, key=lambda c: c[0])[1]
            jt_left.remove(match)
    systems = []
    if imd_tr:
        systems.append((imd, match))
    systems += [(None, w) for w in jt_left]
    for im, jt in systems:
        it = im["track"] if im else []
        jtr = jt["track"] if jt else []
        cons = consensus(it, jtr)
        sid = (jt and jt["id"]) or (im and im["name"]) or "storm"
        name = (im and im["name"]) or (jt and jt["name"]) or sid
        # history of observed fixes
        h = history.setdefault(sid, [])
        for src, fix in (("imd", it[0] if it else None), ("jtwc", jt["fix"] if jt else None)):
            if fix and not any(x["time"] == fix["time"] and x["src"] == src for x in h):
                h.append({"time": fix["time"], "lat": fix["lat"], "lon": fix["lon"], "src": src})
        h.sort(key=lambda x: (x["time"], x["src"]))
        track_for_dist = cons if len(cons) > 1 else (it or jtr)
        near = {n: closest(track_for_dist, places["places"][n]) for n in places["places"]} if len(track_for_dist) > 1 else {}
        storms.append({
            "id": sid, "name": name,
            "imd": {"url": imd_url, "track": it} if it else None,
            "jtwc": {k: jt[k] for k in ("id", "warning", "issued", "fix", "track", "url")} if jt else None,
            "consensus": cons,
            "landfall": {"imd": landfall(it) if len(it) > 1 else None,
                         "jtwc": landfall(jtr) if len(jtr) > 1 else None,
                         "consensus": landfall(cons) if len(cons) > 1 else None},
            "near": near, "past": h})
    return {"storms": storms, "places": places}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imd-text"); ap.add_argument("--jtwc-text", action="append")
    ap.add_argument("--now")
    a = ap.parse_args()
    now = datetime.strptime(a.now, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) if a.now else datetime.now(UTC)
    os.makedirs(DATA, exist_ok=True)
    prev, history = load("latest.json", None), load("history.json", {})
    status = {"checked": iso(now), "imd": {}, "jtwc": {}}
    imd = imd_url = None
    jt = []
    if a.imd_text or a.jtwc_text:  # offline mode
        if a.imd_text:
            imd, imd_url = parse_imd(open(a.imd_text).read()), "fixture:" + os.path.basename(a.imd_text)
        for f in a.jtwc_text or []:
            w = parse_jtwc(open(f).read(), now)
            if w:
                w["url"] = "fixture:" + os.path.basename(f); jt.append(w)
        status["imd"]["ok"] = bool(imd and imd["track"]); status["jtwc"]["ok"] = bool(jt)
    else:
        import requests
        s = requests.Session()
        try:
            imd_url, imd, err = fetch_imd(s)
            status["imd"] = {"ok": bool(imd and imd["track"]), "url": imd_url, "error": err}
        except Exception as e:
            status["imd"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
        try:
            jt = fetch_jtwc(s, now)
            status["jtwc"] = {"ok": True, "storms": [w["id"] for w in jt]}
        except Exception as e:
            status["jtwc"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
        # keep last good data for a source that failed
        if prev and prev.get("storms"):
            if not status["imd"]["ok"] and status["imd"].get("error"):
                old = next((x for x in prev["storms"] if x.get("imd")), None)
                if old:
                    imd, imd_url = {"name": old["name"], "track": old["imd"]["track"]}, old["imd"]["url"]
                    status["imd"]["using_previous"] = True
            if not status["jtwc"]["ok"]:
                jt = [dict(x["jtwc"], name=x["name"]) for x in prev["storms"] if x.get("jtwc")]
                status["jtwc"]["using_previous"] = True
    # drop forecasts whose last point is more than 36 h old (system over)
    def fresh(tr):
        return tr and parse_iso(tr[-1]["time"]) > now - timedelta(hours=36)
    if imd and not fresh(imd["track"]):
        imd = None
    jt = [w for w in jt if fresh(w["track"])]
    latest = build(imd, imd_url, jt, prev, history, now)
    save("latest.json", latest); save("history.json", history); save("status.json", status)
    print(json.dumps(status))
    print("storms:", [(s["id"], s["name"], len(s["consensus"])) for s in latest["storms"]])


if __name__ == "__main__":
    main()
