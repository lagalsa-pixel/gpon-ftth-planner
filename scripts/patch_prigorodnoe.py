#!/usr/bin/env python3
"""Патч границ Пригородного: только здания в радиусе 1400 м от якоря села
(с исключением полигонов Риддера), буфер 300 м. Обновляет snp_bounds_final.json."""
import requests, json, math, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
RIDDER_POLY_BBOXES = [
    (50.33472, 50.34025, 83.51045, 83.51941), (50.32017, 50.32509, 83.50425, 83.51132),
    (50.32208, 50.32903, 83.49661, 83.50787), (50.32620, 50.33259, 83.48943, 83.49963),
    (50.32786, 50.33281, 83.52260, 83.52510), (50.33243, 50.34807, 83.51552, 83.53243),
    (50.32833, 50.33238, 83.52475, 83.53007), (50.33394, 50.33601, 83.49872, 83.50192),
    (50.33137, 50.33548, 83.49349, 83.50037), (50.32962, 50.33224, 83.49751, 83.50169),
    (50.33260, 50.33495, 83.50097, 83.50477), (50.33392, 50.33623, 83.50257, 83.50630),
    (50.32663, 50.32774, 83.51046, 83.51421), (50.32400, 50.32674, 83.52580, 83.53057),
    (50.31809, 50.33490, 83.52610, 83.55400),
]

def ov_query(query, tries=3):
    for attempt in range(tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(mirror, data={"data": query}, headers=UA, timeout=60)
                if r.status_code == 200:
                    return r.json()
                print(f"  [{mirror.split('/')[2]}] HTTP {r.status_code}", flush=True)
            except Exception as e:
                print(f"  [{mirror.split('/')[2]}] {type(e).__name__}", flush=True)
        if attempt < tries - 1:
            print("  пауза 20с...", flush=True)
            time.sleep(20)
    return None

def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*R*math.asin(math.sqrt(a))

with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
    villages = json.load(f)

rec = next(v for v in villages if v["key"] == "prigorodnoe")
la, lo = rec["anchor"]
q = f"""[out:json][timeout:50];
way["building"](around:1400,{la},{lo});
out center;"""
print("Пауза 45с перед запросом (разгрузка зеркал)...", flush=True)
time.sleep(45)
data = ov_query(q)
if not data:
    print("!! Overpass недоступен — fallback по рамке Google Earth (центр ±1300 м)", flush=True)
    la0, lo0 = rec["lat"], rec["lon"]  # координаты из GE-ссылки: 50.321981, 83.52094976
    m_lat0 = 111132.92 - 559.82*math.cos(2*math.radians(la0))
    m_lon0 = 111412.84*math.cos(math.radians(la0))
    lat_lo_b, lat_hi_b = la0 - 1300/m_lat0, la0 + 1300/m_lat0
    lon_lo_b, lon_hi_b = lo0 - 1300/m_lon0, lo0 + 1300/m_lon0
    w = (lon_hi_b - lon_lo_b) * m_lon0; h = (lat_hi_b - lat_lo_b) * m_lat0
    rec["bbox_final"] = {"lat_lo": lat_lo_b, "lat_hi": lat_hi_b, "lon_lo": lon_lo_b, "lon_hi": lon_hi_b}
    rec["size_m_final"] = {"w": w, "h": h}
    rec["method"] = "ge_fallback_center_1300m"
    rec["n_buildings_kept"] = None
    with open("/home/z/my-project/scripts/snp_bounds_final.json", "w", encoding="utf-8") as f:
        json.dump(villages, f, ensure_ascii=False, indent=2)
    print(f"Кадр Пригородного (fallback): {w:.0f} x {h:.0f} м")
    raise SystemExit(0)
blds = [el["center"] for el in data.get("elements", [])
        if el.get("type") == "way" and "building" in el.get("tags", {}) and "center" in el]
blds = [b for b in blds if not any(bb[0] <= b["lat"] <= bb[1] and bb[2] <= b["lon"] <= bb[3] for bb in RIDDER_POLY_BBOXES)]
blds = [b for b in blds if hav(la, lo, b["lat"], b["lon"]) <= 1400]
print(f"Зданий Пригородного в r=1400м (без Риддера): {len(blds)}")

lats = sorted(b["lat"] for b in blds); lons = sorted(b["lon"] for b in blds)
def pct(arr, p):
    idx = max(0, min(len(arr)-1, int(round((len(arr)-1)*p))))
    return arr[idx]
lat_lo, lat_hi = pct(lats, 0.01), pct(lats, 0.99)
lon_lo, lon_hi = pct(lons, 0.01), pct(lons, 0.99)

mlat = (lat_lo + lat_hi) / 2
m_lat = 111132.92 - 559.82*math.cos(2*math.radians(mlat)) + 1.175*math.cos(4*math.radians(mlat))
m_lon = 111412.84*math.cos(math.radians(mlat)) - 93.5*math.cos(3*math.radians(mlat))

BUFFER_M = 300
lat_lo_b = lat_lo - BUFFER_M/m_lat; lat_hi_b = lat_hi + BUFFER_M/m_lat
lon_lo_b = lon_lo - BUFFER_M/m_lon; lon_hi_b = lon_hi + BUFFER_M/m_lon
lat_lo_b = min(lat_lo_b, la - 500/m_lat); lat_hi_b = max(lat_hi_b, la + 500/m_lat)
lon_lo_b = min(lon_lo_b, lo - 500/m_lon); lon_hi_b = max(lon_hi_b, lo + 500/m_lon)

w = (lon_hi_b - lon_lo_b) * m_lon; h = (lat_hi_b - lat_lo_b) * m_lat
print(f"Новый кадр Пригородного: {w:.0f} x {h:.0f} м; lat [{lat_lo_b:.5f},{lat_hi_b:.5f}] lon [{lon_lo_b:.5f},{lon_hi_b:.5f}]")

rec["bbox_final"] = {"lat_lo": lat_lo_b, "lat_hi": lat_hi_b, "lon_lo": lon_lo_b, "lon_hi": lon_hi_b}
rec["size_m_final"] = {"w": w, "h": h}
rec["method"] = "osm_cluster_capped1400"
rec["n_buildings_kept"] = len(blds)

with open("/home/z/my-project/scripts/snp_bounds_final.json", "w", encoding="utf-8") as f:
    json.dump(villages, f, ensure_ascii=False, indent=2)
print("Обновлено: scripts/snp_bounds_final.json")
