"""One-off: build docs/data/land.json (SVG paths) and scripts/land_region.geojson (for landfall checks).
Needs world-atlas topojson converted to GeoJSON (see README). Not run by the hourly job."""
import json, math, sys
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid
land_src, border_src = sys.argv[1], sys.argv[2]
BB = (66.0, 4.0, 96.0, 26.5)
LAT0 = 17.0
clip = box(*BB)
land = unary_union([make_valid(shape(f["geometry"])).intersection(clip)
                    for f in json.load(open(land_src))["features"]])
from shapely.geometry import MultiPolygon
def polys_of(g):
    if g.geom_type == "Polygon": return [g]
    return [p for x in getattr(g, "geoms", []) for p in polys_of(x)]
land = MultiPolygon(polys_of(land))
json.dump(mapping(land.simplify(0.005, preserve_topology=True)), open("scripts/land_region.geojson", "w"))
k = math.cos(math.radians(LAT0)); W = 2000
sx = W / ((BB[2] - BB[0]) * k); H = round((BB[3] - BB[1]) * sx)
P = lambda lon, lat: (round((lon - BB[0]) * k * sx, 1), round((BB[3] - lat) * sx, 1))
simp = land.simplify(0.008, preserve_topology=True)
polys = [simp] if simp.geom_type == "Polygon" else list(simp.geoms)
ring = lambda r: "M" + "L".join(f"{x},{y}" for x, y in (P(*c) for c in r.coords)) + "Z"
d = "".join(ring(p.exterior) + "".join(ring(i) for i in p.interiors) for p in polys if p.area > 0.0003)
b = shape(json.load(open(border_src))).intersection(clip)
lines = [b] if b.geom_type == "LineString" else [g for g in getattr(b, "geoms", []) if g.geom_type == "LineString"]
bp = "".join("M" + "L".join(f"{x},{y}" for x, y in (P(*c) for c in l.coords)) for l in lines)
json.dump({"bbox": BB, "lat0": LAT0, "W": W, "H": H, "land": d, "borders": bp}, open("docs/data/land.json", "w"))
print("land.json", len(d) + len(bp), "chars")
