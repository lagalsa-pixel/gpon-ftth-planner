#!/usr/bin/env python3
"""Полноразрешающие кропы вдоль северной магистрали Алтайского для верификации."""
from PIL import Image
import json, sys

sys.path.insert(0, "/home/z/my-project/scripts")
import mark_households as mh
import download_and_stitch as ds

Image.MAX_IMAGE_PIXELS = None

with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
    villages = {v["key"]: v for v in json.load(f)}
v = villages["altaisky"]
bbox = v["bbox_final"]
with open("/home/z/my-project/scripts/households/altaisky_numbered.geojson", encoding="utf-8") as f:
    numbered = json.load(f)
dx, dy = numbered["offset_px"]
ox, oy = mh.crop_origin(bbox)

def to_px(lon, lat):
    gx, gy = mh.to_global(lon, lat)
    return gx - ox + dx, gy - oy + dy

with open("/home/z/my-project/scripts/ftth_design/altaisky.json", encoding="utf-8") as f:
    design = json.load(f)

img = Image.open("/home/z/my-project/download/snp_vko/ftth/06_Алтайский_FTTH_z18.png")
W, H = img.size

# северные feeder-точки
pts = [p for c in design["cables"]["feeder"] for p in c["pts"]]
pts.sort(key=lambda p: -p[1])
# две зоны внимания: самая северная точка и точка ~50.2645
targets = [pts[0]]
for p in pts:
    if p[1] < 50.2645 and all(abs(p[1] - t[1]) > 0.0008 for t in targets):
        targets.append(p)
        break

for i, (lon, lat) in enumerate(targets):
    x, y = to_px(lon, lat)
    x, y = int(x), int(y)
    S = 900  # полукадр
    crop = img.crop((max(0, x - S), max(0, y - S), min(W, x + S), min(H, y + S)))
    crop = crop.resize((crop.width // 2, crop.height // 2), Image.LANCZOS)
    crop.convert("RGB").save(f"/home/z/my-project/scripts/qc_alt_zone{i+1}.jpg", "JPEG", quality=90)
    print(f"зона {i+1}: lat={lat:.5f} -> qc_alt_zone{i+1}.jpg {crop.size}")
