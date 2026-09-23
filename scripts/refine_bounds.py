#!/usr/bin/env python3
"""Уточнение границ: landuse=residential полигоны для Пригородного и всех сёл.
Плюс гистограммы распределения зданий для проверки вытянутых сёл."""
import requests, json, math, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

def ov_query(query, tries=2):
    for attempt in range(tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(mirror, data={"data": query}, headers=UA, timeout=50)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass
        time.sleep(2)
    return None

# --- 1. Пригородное: landuse=residential полигоны r=2км от якоря села
print("=== Пригородное: полигоны landuse рядом с якорем (50.32097, 83.51958) ===", flush=True)
q = """[out:json][timeout:50];
way["landuse"~"residential|village_grounds"](around:2000,50.32097,83.51958);
out geom;"""
data = ov_query(q)
if data:
    for el in data.get("elements", []):
        geom = el.get("geometry", [])
        lats = [g["lat"] for g in geom]; lons = [g["lon"] for g in geom]
        cx, cy = sum(lons)/len(lons), sum(lats)/len(lats)
        contains = (min(lats) <= 50.32097 <= max(lats)) and (min(lons) <= 83.51958 <= max(lons))
        area_ha = None
        tags = el.get("tags", {})
        print(f"  way id={el['id']}: имя={tags.get('name','—')}, landuse={tags.get('landuse')}, "
              f"bbox lat[{min(lats):.5f},{max(lats):.5f}] lon[{min(lons):.5f},{max(lons):.5f}], "
              f"центр=({cy:.5f},{cx:.5f}), якорь внутри={contains}", flush=True)
else:
    print("  Overpass недоступен", flush=True)

# --- 2. Гистограммы зданий для вытянутых сёл
print("\n=== Распределение зданий по осям (проверка на выбросы) ===", flush=True)
with open("/home/z/my-project/scripts/snp_bounds.json", encoding="utf-8") as f:
    bounds = json.load(f)

for v, r in [(x, 2500) for x in ["Перевальное", "Алтайский", "Пригородное"]]:
    rec = next(b for b in bounds if v.split()[-1].lower() in b["name"].lower() or v in b["name"])
    q = f"""[out:json][timeout:50];
way["building"](around:{r},{rec['lat']},{rec['lon']});
out center;"""
    data = ov_query(q)
    if not data:
        print(f"  {v}: Overpass недоступен", flush=True)
        continue
    blds = [el["center"] for el in data.get("elements", []) if el.get("type") == "way" and "center" in el]
    lons = sorted(b["lon"] for b in blds); lats = sorted(b["lat"] for b in blds)
    def hist(arr, n=10):
        lo, hi = arr[0], arr[-1]
        if hi == lo:
            return "degenerate"
        buckets = [0]*n
        for x in arr:
            buckets[min(n-1, int((x-lo)/(hi-lo)*n))] += 1
        return buckets
    print(f"  {v} (n={len(blds)}):")
    print(f"    lon {lons[0]:.4f}..{lons[-1]:.4f}: {hist(lons)}")
    print(f"    lat {lats[0]:.4f}..{lats[-1]:.4f}: {hist(lats)}")
    time.sleep(1)
