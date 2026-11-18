"""Run: python tests/test_parse.py  (no network needed)"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import update as u
F = os.path.join(os.path.dirname(__file__), "fixtures")
imd = u.parse_imd(open(os.path.join(F, "imd_advisory_15.txt")).read())
assert imd["name"] == "Akvan", imd["name"]
assert len(imd["track"]) == 9
assert imd["track"][0] == {"time": "2026-11-18T06:00Z", "lat": 13.1, "lon": 85.4, "kmh": [90, 100], "gust": 110, "cls": "Severe Cyclonic Storm"}
assert imd["track"][6]["cls"] == "Cyclonic Storm"
# rows split across lines, as pdf text extraction can do
wrapped = "18.11.26/\n0600 13.1/\n85.4 90-\n100 gusting\nto 110"
assert u.parse_imd(wrapped)["track"][0]["kmh"] == [90, 100]
# IST bulletin rows shift to UTC
ist = u.parse_imd("18.11.26/1130 13.1/85.4 90-100 gusting to 110", is_ist=True)
assert ist["track"][0]["time"] == "2026-11-18T06:00Z"
now = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)
jt = u.parse_jtwc(open(os.path.join(F, "jtwc_io0526_nr006.txt")).read(), now)
assert (jt["id"], jt["name"], jt["warning"]) == ("05B", "Akvan", 6)
assert jt["fix"] == {"time": "2026-11-18T00:00Z", "lat": 13.0, "lon": 86.9, "kt": 45}
assert [p["time"] for p in jt["track"]][-1] == "2026-11-20T12:00Z" and len(jt["track"]) == 6
assert jt["track"][-1]["kt"] == 30
# month rollover: a 31st-of-month fix read on the 1st of the next month
assert u._jt_time(31, 18, 0, datetime(2026, 11, 1, 2, tzinfo=timezone.utc)).month == 10
cons = u.consensus(imd["track"], jt["track"])
assert cons[0]["time"] == "2026-11-18T06:00Z" and cons[-1]["time"] == "2026-11-20T12:00Z"
lf = u.landfall(cons)
assert 18.0 < lf["lat"] < 18.8 and 83.8 < lf["lon"] < 84.5, lf
print("all parser tests passed")
