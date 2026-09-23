#!/usr/bin/env python3
"""Кроп северной части Алтайского для проверки трассировки магистрали."""
from PIL import Image
import json, math, sys

sys.path.insert(0, "/home/z/my-project/scripts")
import mark_households as mh

Image.MAX_IMAGE_PIXELS = None

# координаты интересующих feeder-сегментов (север)
with open("/home/z/my-project/scripts/ftth_design/altaisky.json", encoding="utf-8") as f:
    design = json.load(f)

# найдём самые северные feeder-сегменты
feeder = design["cables"]["feeder"]
feeder.sort(key=lambda c: -max(p[1] for p in c["pts"]))
print("Самые северные сегменты магистрали (lat):")
for c in feeder[:10]:
    print(f"  fibers={c['fibers']} load={c['load']} lat={max(p[1] for p in c['pts']):.5f}")

# кроп верхней трети изображения
img = Image.open("/home/z/my-project/download/snp_vko/ftth/06_Алтайский_FTTH_z18.png")
W, H = img.size
crop = img.crop((0, 0, W, H // 3))
crop.thumbnail((1800, 1800), Image.LANCZOS)
crop.convert("RGB").save("/home/z/my-project/scripts/qc_alt_north.jpg", "JPEG", quality=88)
print(f"кроп сохранён: scripts/qc_alt_north.jpg ({crop.size})")

# заодно: типы дорог на севере (lat > 50.255)
with open("/home/z/my-project/scripts/osm_roads/altaisky.json", encoding="utf-8") as f:
    roads = json.load(f)
nodes = {el["id"]: (el["lat"], el["lon"]) for el in roads["elements"] if el.get("type") == "node"}
from collections import Counter
cnt = Counter()
for el in roads["elements"]:
    if el.get("type") != "way":
        continue
    lats = [nodes[n][0] for n in el.get("nodes", []) if n in nodes]
    if lats and max(lats) > 50.255:
        cnt[el.get("tags", {}).get("highway", "?")] += 1
print("Типы дорог в северной полосе (lat>50.255):", dict(cnt))
