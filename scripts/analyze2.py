#!/usr/bin/env python3
"""Доанализ: 1) крупные здания (кандидаты МКД) в каждом селе; 2) реальный охват
addr:housenumber (диапазоны, дубли); 3) запрос OSM в широкой окрестности Алтайского."""
import json, os, re, requests, time

DIR = "/home/z/my-project/scripts/households"
NON_RES = {"garage", "garages", "shed", "barn", "roof", "carport", "greenhouse",
           "industrial", "warehouse", "commercial", "retail", "school", "kindergarten",
           "hospital", "kiosk", "service", "construction", "ruins", "wall", "hut",
           "public", "civic", "offices", "hotel", "train_station", "tower"}

files = ["verhneberezevka", "solnechnoe", "perevalnoe", "vinnoe", "prigorodnoe", "altaisky"]

print("== Крупные здания (>= 300 м2) — кандидаты многоквартирных/общественных ==")
for key in files:
    with open(os.path.join(DIR, f"{key}.geojson"), encoding="utf-8") as f:
        fc = json.load(f)
    big = [ft for ft in fc["features"]
           if ft["properties"]["area_m2"] >= 300 and ft["properties"]["building"] not in NON_RES]
    big.sort(key=lambda ft: -ft["properties"]["area_m2"])
    print(f"\n{fc['village']}: {len(big)} шт >=300 м2")
    for ft in big[:12]:
        p = ft["properties"]
        print(f"   id={p['osm_id']} tag={p['building']} area={p['area_m2']:.0f} м2 hn={p['housenumber']} levels={p['levels']}")

print("\n== addr:housenumber: диапазоны и дубли ==")
for key in files:
    with open(os.path.join(DIR, f"{key}.geojson"), encoding="utf-8") as f:
        fc = json.load(f)
    hns = [ft["properties"]["housenumber"] for ft in fc["features"] if ft["properties"]["housenumber"]]
    if not hns:
        print(f"{key}: нет номеров")
        continue
    def numof(s):
        m = re.match(r"\s*(\d+)", str(s))
        return int(m.group(1)) if m else None
    nums = [numof(h) for h in hns]
    nums_ok = [n for n in nums if n is not None]
    seen, dups = {}, []
    for h in hns:
        seen[h] = seen.get(h, 0) + 1
    dups = {h: c for h, c in seen.items() if c > 1}
    print(f"{key}: n={len(hns)}, номера от {min(nums_ok)} до {max(nums_ok)}, "
          f"уникальных {len(seen)}, дубликаты: {dict(list(dups.items())[:8])}")

print("\n== Широкая окрестность Алтайского (bbox 50.20-50.30, 82.31-82.41) ==")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
q = """[out:json][timeout:120];
(
  way["building"](50.20,82.31,50.30,82.41);
  node["place"](50.20,82.31,50.30,82.41);
);
out tags center;"""
data = None
for m in MIRRORS:
    try:
        r = requests.post(m, data={"data": q}, headers=UA, timeout=90)
        if r.status_code == 200:
            data = r.json()
            print(f"источник: {m.split('/')[2]}")
            break
        print(f"  [{m.split('/')[2]}] HTTP {r.status_code}")
    except Exception as e:
        print(f"  [{m.split('/')[2]}] {type(e).__name__}")
    time.sleep(3)
if data:
    blds = [el for el in data["elements"] if el.get("type") == "way"]
    places = [el for el in data["elements"] if el.get("type") == "node"]
    print(f"зданий всего в широкой рамке: {len(blds)}")
    for p in places:
        t = p.get("tags", {})
        print(f"  place: {t.get('name')} ({t.get('place')}), {p['lat']:.5f},{p['lon']:.5f}")
    # грубая сетка 1x1 км, счёт зданий
    grid = {}
    for b in blds:
        c = b.get("center", {})
        gx = int((c["lon"] - 82.31) / 0.0135)
        gy = int((c["lat"] - 50.20) / 0.009)
        grid[(gx, gy)] = grid.get((gx, gy), 0) + 1
    print("сетка ~1 км (строки юг->север):")
    for gy in sorted(range(0, 12), reverse=True):
        row = "".join(f"{grid.get((gx, gy), 0):4d}" for gx in range(0, 8))
        latr = 50.20 + gy * 0.009
        print(f"  lat~{latr:.3f}: {row}")
