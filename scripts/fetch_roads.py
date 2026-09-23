#!/usr/bin/env python3
"""Выгрузка улично-дорожной сети OSM по кадрам 6 СНП ВКО (для проектирования FTTH).

Для каждого села: way["highway"] в пределах bbox_final + рекурсия узлов (out body),
чтобы граф имел общие узлы на пересечениях улиц.
Результат: scripts/osm_roads/<key>.json — сырой ответ Overpass (ways + nodes).

Использование: python3 fetch_roads.py [key|all]
"""
import requests, json, time, os, sys

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]

OUTDIR = "/home/z/my-project/scripts/osm_roads"
os.makedirs(OUTDIR, exist_ok=True)


def ov_query(query, tries=4):
    for attempt in range(tries):
        for mirror in MIRRORS:
            try:
                r = requests.post(mirror, data={"data": query}, headers=UA, timeout=120)
                if r.status_code == 200:
                    return r.json()
                print(f"    [{mirror.split('/')[2]}] HTTP {r.status_code}", flush=True)
            except Exception as e:
                print(f"    [{mirror.split('/')[2]}] {type(e).__name__}", flush=True)
        if attempt < tries - 1:
            print(f"    раунд {attempt+1} не удался, пауза 25с...", flush=True)
            time.sleep(25)
    return None


def main():
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg not in ("all",):
        villages = [v for v in villages if v["key"] == arg]

    for v in villages:
        bbox = v["bbox_final"]
        key = v["key"]
        print(f"\n=== {v['name']} ===", flush=True)
        q = f"""[out:json][timeout:180];
way["highway"]({bbox['lat_lo']},{bbox['lon_lo']},{bbox['lat_hi']},{bbox['lon_hi']});
(._;>;);
out body;"""
        data = ov_query(q)
        if not data:
            print("  !! Overpass недоступен, пропуск села", flush=True)
            continue

        n_ways = n_nodes = 0
        hist = {}
        for el in data.get("elements", []):
            if el.get("type") == "way" and "nodes" in el:
                n_ways += 1
                hw = el.get("tags", {}).get("highway", "?")
                hist[hw] = hist.get(hw, 0) + 1
            elif el.get("type") == "node":
                n_nodes += 1
        top = sorted(hist.items(), key=lambda kv: -kv[1])
        print(f"  дорог: {n_ways}, узлов: {n_nodes}; типы: {top[:10]}", flush=True)

        path = os.path.join(OUTDIR, f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"  сохранено: {path}", flush=True)
        time.sleep(12)

    print("\nГотово.", flush=True)


if __name__ == "__main__":
    main()
