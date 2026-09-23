#!/usr/bin/env python3
"""Выгрузка геометрий зданий OSM (контуры) по итоговым кадрам 6 СНП ВКО.

Для каждого села: way["building"] в пределах bbox_final, фильтр центроида,
для Пригородного — исключение полигонов Риддера и радиус 1400 м от якоря.
Результат: scripts/households/<key>.geojson (полигоны + теги + площадь + центроид)
+ сводка по тегам building в консоль.
"""
import requests, json, math, time, os

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

OUTDIR = "/home/z/my-project/scripts/households"
os.makedirs(OUTDIR, exist_ok=True)


def ov_query(query, tries=4):
    for attempt in range(tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(mirror, data={"data": query}, headers=UA, timeout=90)
                if r.status_code == 200:
                    return r.json()
                print(f"    [{mirror.split('/')[2]}] HTTP {r.status_code}", flush=True)
            except Exception as e:
                print(f"    [{mirror.split('/')[2]}] {type(e).__name__}", flush=True)
        if attempt < tries - 1:
            print(f"    раунд {attempt+1} не удался, пауза 25с...", flush=True)
            time.sleep(25)
    return None


def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def poly_centroid_area(pts):
    """pts: [(lat,lon),...]. Возвращает (clat, clon, area_m2) — шнурковая формула
    в локальной равноугольной проекции вокруг центроида bbox."""
    la0 = sum(p[0] for p in pts) / len(pts)
    lo0 = sum(p[1] for p in pts) / len(pts)
    mlat = 111132.92 - 559.82 * math.cos(2 * math.radians(la0))
    mlon = 111412.84 * math.cos(math.radians(la0))
    xs = [(p[1] - lo0) * mlon for p in pts]
    ys = [(p[0] - la0) * mlat for p in pts]
    a2 = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = xs[i], ys[i]
        x2, y2 = xs[(i + 1) % n], ys[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a2) < 1e-9:
        return la0, lo0, 0.0
    area = abs(a2) / 2.0
    cx /= 3 * a2
    cy /= 3 * a2
    return la0 + cy / mlat, lo0 + cx / mlon, area


def main():
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    if only:
        villages = [v for v in villages if v["key"] == only]

    summary = []
    for v in villages:
        bbox = v["bbox_final"]
        key = v["key"]
        print(f"\n=== {v['name']} ===", flush=True)
        q = f"""[out:json][timeout:120];
way["building"]({bbox['lat_lo']},{bbox['lon_lo']},{bbox['lat_hi']},{bbox['lon_hi']});
out geom;"""
        data = ov_query(q)
        if not data:
            print("  !! Overpass недоступен, пропуск села", flush=True)
            summary.append(dict(key=key, ok=False))
            continue

        feats, hist, n_hn = [], {}, 0
        for el in data.get("elements", []):
            if el.get("type") != "way" or "geometry" not in el:
                continue
            tags = el.get("tags", {})
            bt = tags.get("building", "yes")
            geom = [(n["lat"], n["lon"]) for n in el["geometry"]]
            # замкнутость
            if len(geom) >= 3 and geom[0] != geom[-1]:
                geom = geom + [geom[0]]
            if len(geom) < 4:
                continue
            clat, clon, area = poly_centroid_area(geom)
            # центроид должен лежать в кадре
            if not (bbox["lat_lo"] <= clat <= bbox["lat_hi"] and bbox["lon_lo"] <= clon <= bbox["lon_hi"]):
                continue
            # Пригородное: исключить Риддер и радиус > 1400 м
            if key == "prigorodnoe":
                if any(bb[0] <= clat <= bb[1] and bb[2] <= clon <= bb[3] for bb in RIDDER_POLY_BBOXES):
                    continue
                la, lo = v["anchor"]
                if hav(la, lo, clat, clon) > 1400:
                    continue
            hist[bt] = hist.get(bt, 0) + 1
            hn = tags.get("addr:housenumber")
            if hn:
                n_hn += 1
            feats.append({
                "type": "Feature",
                "properties": {
                    "osm_id": el["id"],
                    "building": bt,
                    "housenumber": hn,
                    "street": tags.get("addr:street"),
                    "levels": tags.get("building:levels"),
                    "area_m2": round(area, 1),
                    "clat": clat, "clon": clon,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[p[1], p[0]] for p in geom]],
                },
            })

        out = {"type": "FeatureCollection", "village": v["name"], "key": key, "features": feats}
        path = os.path.join(OUTDIR, f"{key}.geojson")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)

        top = sorted(hist.items(), key=lambda kv: -kv[1])
        print(f"  зданий в кадре: {len(feats)}; с addr:housenumber: {n_hn}", flush=True)
        print(f"  теги building: {top}", flush=True)
        summary.append(dict(key=key, ok=True, n=len(feats), hist=hist, n_hn=n_hn,
                            official=v["households"]))
        time.sleep(12)

    with open(os.path.join(OUTDIR, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("\nСохранено: scripts/households/*.geojson + _summary.json", flush=True)


if __name__ == "__main__":
    main()
