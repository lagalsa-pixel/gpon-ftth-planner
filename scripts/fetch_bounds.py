#!/usr/bin/env python3
"""Получение границ застройки 6 СНП из OSM (Overpass API):
- place-узлы (r=5 км) для привязки и отсечения соседних поселений
- центры зданий (r=2.5 км) для расчёта bbox застройки
Результат: /home/z/my-project/scripts/snp_bounds.json
"""
import requests, json, math, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

VILLAGES = [
    dict(key="verhneberezevka", name="с. Верхнеберезовка", district="Глубоковский район", okrug="Верхнеберезовский с.о.",
         osm_names=["Верхнеберезовка", "Верхняя Березовка"], lat=50.28420545, lon=82.209512, households=940, kato=634045100),
    dict(key="solnechnoe", name="с. Солнечное", district="Глубоковский район", okrug="Бобровский с.о.",
         osm_names=["Солнечное"], lat=50.0517755, lon=82.71438134, households=366, kato=634039300),
    dict(key="perevalnoe", name="с. Перевальное", district="Глубоковский район", okrug="Красноярский с.о.",
         osm_names=["Перевальное", "Перевальное (Красноярский с/о)"], lat=50.24139084, lon=82.28314297, households=339, kato=634053300),
    dict(key="vinnoe", name="с. Винное", district="Глубоковский район", okrug="Тарханский с.о.",
         osm_names=["Винное"], lat=50.05844487, lon=82.82687999, households=490, kato=634067300),
    dict(key="prigorodnoe", name="с. Пригородное", district="г. Риддер", okrug="—",
         osm_names=["Пригородное", "Пригородный"], lat=50.321981, lon=83.52094976, households=365, kato=632400680),
    dict(key="altaisky", name="с. Алтайский", district="Глубоковский район", okrug="Алтайский с.о.",
         osm_names=["Алтайский", "Алтайское"], lat=50.24399825, lon=82.36103064, households=716, kato=634033100),
]

def ov_query(query, tries=3):
    for attempt in range(tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(mirror, data={"data": query}, headers=UA, timeout=55)
                if r.status_code == 200:
                    return r.json()
                print(f"    [{mirror.split('/')[2]}] HTTP {r.status_code}", flush=True)
            except requests.exceptions.Timeout:
                print(f"    [{mirror.split('/')[2]}] timeout", flush=True)
            except Exception as e:
                print(f"    [{mirror.split('/')[2]}] {type(e).__name__}", flush=True)
        time.sleep(3)
    return None

def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def meters_per_deg_lat(lat):
    return 111132.92 - 559.82*math.cos(2*math.radians(lat)) + 1.175*math.cos(4*math.radians(lat))

def meters_per_deg_lon(lat):
    return 111412.84*math.cos(math.radians(lat)) - 93.5*math.cos(3*math.radians(lat))

BUFFER_M = 300  # запас вокруг застройки

results = []
for v in VILLAGES:
    print(f"\n=== {v['name']} ===", flush=True)
    la, lo = v["lat"], v["lon"]
    q = f"""[out:json][timeout:50];
(
  node["place"](around:5000,{la},{lo});
  way["building"](around:2500,{la},{lo});
);
out center;"""
    data = ov_query(q)
    if data is None:
        print("  !! Overpass недоступен, будет fallback на радиус 1200 м", flush=True)
        results.append({**v, "source": "fallback", "bbox": None})
        continue

    places = [el for el in data.get("elements", []) if el.get("type") == "node" and "place" in el.get("tags", {})]
    buildings = [el for el in data.get("elements", [])
                 if el.get("type") == "way" and "building" in el.get("tags", {})
                 and "center" in el]

    # Ищем целевой place-узел по имени
    target = None
    for p in places:
        nm = p["tags"].get("name", "") or p["tags"].get("name:ru", "") or p["tags"].get("name:kk", "")
        for cand in v["osm_names"]:
            if nm.strip().lower() == cand.strip().lower():
                target = p
                break
        if target:
            break
    if target is None:  # ближайший place-узел не дальше 1500 м
        cands = [(hav(la, lo, p["lat"], p["lon"]), p) for p in places]
        cands = [c for c in cands if c[0] < 1500]
        if cands:
            target = min(cands, key=lambda c: c[0])[1]

    anchor = (target["lat"], target["lon"]) if target else (la, lo)
    print(f"  place-узлов (r=5км): {len(places)}, зданий (r=2.5км): {len(buildings)}", flush=True)
    print(f"  place-узлы: " + "; ".join(f"{p['tags'].get('name','?')}({p['tags'].get('place','?')},{p['lat']:.3f},{p['lon']:.3f})" for p in places[:10]), flush=True)
    if target:
        print(f"  целевой узел: {target['tags'].get('name')} @ {anchor[0]:.5f},{anchor[1]:.5f} (тип: {target['tags'].get('place')})", flush=True)
    else:
        print("  целевой узел НЕ найден, якорь = координаты из Excel", flush=True)

    # Соседние поселения (place-узлы в 5 км, кроме цели) для отсечения чужих зданий
    others = [p for p in places if p is not target]
    other_anchor_like = []
    for p in others:
        pl = p["tags"].get("place", "")
        if pl in ("village", "town", "city", "hamlet", "allotments", "isolated_dwelling", "suburb", "quarter"):
            nm = p["tags"].get("name", "?")
            d_to_anchor = hav(anchor[0], anchor[1], p["lat"], p["lon"])
            other_anchor_like.append((p["lat"], p["lon"], nm, pl, d_to_anchor))

    def building_belongs(b):
        """Здание относится к целевому селу, если оно ближе к якорю, чем к центру любого другого поселения (с запасом 1.2 для мелких хуторов)."""
        d_anchor = hav(anchor[0], anchor[1], b["center"]["lat"], b["center"]["lon"])
        for (pla, plo, nm, pl, _) in other_anchor_like:
            d_other = hav(pla, plo, b["center"]["lat"], b["center"]["lon"])
            if d_other < d_anchor / 1.2:
                return False
        return True

    kept = [b for b in buildings if building_belongs(b)]
    print(f"  зданий после отсечения соседних поселений: {len(kept)}", flush=True)
    if len(kept) < 5:
        kept = [b for b in buildings if hav(anchor[0], anchor[1], b["center"]["lat"], b["center"]["lon"]) < 1200]
        print(f"  мало зданий, сужение до r=1200м от якоря: {len(kept)}", flush=True)

    lats = sorted(b["center"]["lat"] for b in kept)
    lons = sorted(b["center"]["lon"] for b in kept)

    def pct(arr, p):
        if len(arr) == 0:
            return None
        idx = max(0, min(len(arr) - 1, int(round((len(arr) - 1) * p))))
        return arr[idx]

    # Робастные перцентили (1..99) против выбросов-одиночных ферм
    lat_lo, lat_hi = pct(lats, 0.01), pct(lats, 0.99)
    lon_lo, lon_hi = pct(lons, 0.01), pct(lons, 0.99)

    mlat = (lat_lo + lat_hi) / 2
    lat_lo_b = lat_lo - BUFFER_M / meters_per_deg_lat(mlat)
    lat_hi_b = lat_hi + BUFFER_M / meters_per_deg_lat(mlat)
    lon_lo_b = lon_lo - BUFFER_M / meters_per_deg_lon(mlat)
    lon_hi_b = lon_hi + BUFFER_M / meters_per_deg_lon(mlat)

    w_m = (lon_hi_b - lon_lo_b) * meters_per_deg_lon(mlat)
    h_m = (lat_hi_b - lat_lo_b) * meters_per_deg_lat(mlat)
    print(f"  bbox застройки+300м: lat [{lat_lo_b:.5f}, {lat_hi_b:.5f}], lon [{lon_lo_b:.5f}, {lon_hi_b:.5f}]", flush=True)
    print(f"  размер кадра: {w_m:.0f} x {h_m:.0f} м, зданий в границах: {len(kept)}", flush=True)

    results.append({
        **v, "source": "osm_buildings",
        "anchor": anchor,
        "n_buildings": len(kept),
        "bbox": {"lat_lo": lat_lo_b, "lat_hi": lat_hi_b, "lon_lo": lon_lo_b, "lon_hi": lon_hi_b},
        "size_m": {"w": w_m, "h": h_m},
    })
    time.sleep(1)

with open("/home/z/my-project/scripts/snp_bounds.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nСохранено: scripts/snp_bounds.json", flush=True)
