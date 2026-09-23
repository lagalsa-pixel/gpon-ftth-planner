#!/usr/bin/env python3
"""Финальный расчёт границ застройки 6 СНП методом кластеризации:
- здания в r=2.5 км от якоря села (OSM)
- single-linkage кластеризация с порогом 350 м
- семена = кластеры, пересекающие радиус 600 м от якоря
- для Пригородного: исключение зданий внутри полигонов Риддера
- bbox = перцентили 1..99 + буфер 300 м, минимум ±500 м от якоря
Результат: scripts/snp_bounds_final.json
"""
import requests, json, math, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# bboxes полигонов Риддера (из предыдущего запроса), для исключения городских зданий
RIDDER_POLY_BBOXES = [
    (50.33472, 50.34025, 83.51045, 83.51941),
    (50.32017, 50.32509, 83.50425, 83.51132),
    (50.32208, 50.32903, 83.49661, 83.50787),
    (50.32620, 50.33259, 83.48943, 83.49963),
    (50.32786, 50.33281, 83.52260, 83.52510),
    (50.33243, 50.34807, 83.51552, 83.53243),
    (50.32833, 50.33238, 83.52475, 83.53007),
    (50.33394, 50.33601, 83.49872, 83.50192),
    (50.33137, 50.33548, 83.49349, 83.50037),
    (50.32962, 50.33224, 83.49751, 83.50169),
    (50.33260, 50.33495, 83.50097, 83.50477),
    (50.33392, 50.33623, 83.50257, 83.50630),
    (50.32663, 50.32774, 83.51046, 83.51421),
    (50.32400, 50.32674, 83.52580, 83.53057),
    (50.31809, 50.33490, 83.52610, 83.55400),
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

def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*R*math.asin(math.sqrt(a))

def cluster_single_linkage(points, thresh=350.0):
    """points: list of (lat, lon). Возвращает list of списков индексов."""
    n = len(points)
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
    # Сетка для ускорения: ячейка 350м
    cell = {}
    mlat = sum(p[0] for p in points) / n
    dlat = 350.0 / 111200.0
    dlon = 350.0 / (111320.0 * math.cos(math.radians(mlat)))
    for idx, (la, lo) in enumerate(points):
        cell.setdefault((int(la // dlat), int(lo // dlon)), []).append(idx)
    for (ci, cj), idxs in cell.items():
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                other = cell.get((ci + di, cj + dj), [])
                for i in idxs:
                    for j in other:
                        if j <= i:
                            continue
                        if hav(points[i][0], points[i][1], points[j][0], points[j][1]) <= thresh:
                            union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())

with open("/home/z/my-project/scripts/snp_bounds.json", encoding="utf-8") as f:
    villages = json.load(f)

BUFFER_M = 300
final = []
for v in villages:
    print(f"\n=== {v['name']} (якорь {v['anchor'][0]:.5f},{v['anchor'][1]:.5f}) ===", flush=True)
    la, lo = v["anchor"]
    q = f"""[out:json][timeout:50];
way["building"](around:2500,{la},{lo});
out center;"""
    data = ov_query(q)
    if not data:
        print("  !! Overpass недоступен — fallback: ±1200 м от якоря", flush=True)
        final.append({**v, "bbox_final": None, "method": "fallback"})
        continue
    blds = [el["center"] for el in data.get("elements", [])
            if el.get("type") == "way" and "building" in el.get("tags", {}) and "center" in el]

    # Пригородное: выкидываем здания внутри полигонов Риддера
    if v["key"] == "prigorodnoe":
        before = len(blds)
        blds = [b for b in blds if not any(bb[0] <= b["lat"] <= bb[1] and bb[2] <= b["lon"] <= bb[3] for bb in RIDDER_POLY_BBOXES)]
        print(f"  исключено зданий Риддера: {before - len(blds)}", flush=True)

    pts = [(b["lat"], b["lon"]) for b in blds]
    print(f"  зданий всего: {len(pts)}", flush=True)
    clusters = cluster_single_linkage(pts, 350.0)
    clusters.sort(key=len, reverse=True)

    seed_clusters = []
    for cl in clusters:
        if any(hav(la, lo, pts[i][0], pts[i][1]) <= 600 for i in cl):
            seed_clusters.append(cl)
    kept_idx = [i for cl in seed_clusters for i in cl]
    print(f"  кластеров: {len(clusters)} (размеры топ-5: {[len(c) for c in clusters[:5]]}); "
          f"семян у якоря: {len(seed_clusters)}; зданий в них: {len(kept_idx)}", flush=True)

    if len(kept_idx) < 5:
        kept_idx = [i for i, p in enumerate(pts) if hav(la, lo, p[0], p[1]) <= 1200]
        print(f"  мало — fallback r=1200м: {len(kept_idx)}", flush=True)

    klats = sorted(pts[i][0] for i in kept_idx)
    klons = sorted(pts[i][1] for i in kept_idx)
    def pct(arr, p):
        idx = max(0, min(len(arr)-1, int(round((len(arr)-1)*p))))
        return arr[idx]

    lat_lo, lat_hi = pct(klats, 0.01), pct(klats, 0.99)
    lon_lo, lon_hi = pct(klons, 0.01), pct(klons, 0.99)

    mlat = (lat_lo + lat_hi) / 2
    m_lat = 111132.92 - 559.82*math.cos(2*math.radians(mlat)) + 1.175*math.cos(4*math.radians(mlat))
    m_lon = 111412.84*math.cos(math.radians(mlat)) - 93.5*math.cos(3*math.radians(mlat))

    lat_lo_b = lat_lo - BUFFER_M / m_lat; lat_hi_b = lat_hi + BUFFER_M / m_lat
    lon_lo_b = lon_lo - BUFFER_M / m_lon; lon_hi_b = lon_hi + BUFFER_M / m_lon

    # Минимальный кадр ±500 м от якоря
    lat_lo_b = min(lat_lo_b, la - 500/m_lat); lat_hi_b = max(lat_hi_b, la + 500/m_lat)
    lon_lo_b = min(lon_lo_b, lo - 500/m_lon); lon_hi_b = max(lon_hi_b, lo + 500/m_lon)

    w = (lon_hi_b - lon_lo_b) * m_lon
    h = (lat_hi_b - lat_lo_b) * m_lat
    print(f"  итоговый кадр: {w:.0f} x {h:.0f} м; lat [{lat_lo_b:.5f},{lat_hi_b:.5f}] lon [{lon_lo_b:.5f},{lon_hi_b:.5f}]", flush=True)

    final.append({**v, "method": "osm_cluster", "n_buildings_kept": len(kept_idx),
                  "n_clusters": len(clusters),
                  "bbox_final": {"lat_lo": lat_lo_b, "lat_hi": lat_hi_b,
                                 "lon_lo": lon_lo_b, "lon_hi": lon_hi_b},
                  "size_m_final": {"w": w, "h": h}})
    time.sleep(1)

with open("/home/z/my-project/scripts/snp_bounds_final.json", "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)
print("\nСохранено: scripts/snp_bounds_final.json", flush=True)
