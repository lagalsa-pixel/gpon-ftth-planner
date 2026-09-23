#!/usr/bin/env python3
"""Быстрая догрузка дорог: параллельный запрос ко всем зеркалам Overpass,
первый успешный ответ выигрывает. Формат выхода совместим с fetch_roads.py.

Использование: python3 fetch_roads_parallel.py <key1> [key2 ...]
"""
import requests, json, time, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MIRRORS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
OUTDIR = "/home/z/my-project/scripts/osm_roads"


def fetch_parallel(query, timeout=90):
    def get(mirror):
        try:
            r = requests.post(mirror, data={"data": query}, headers=UA, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if j.get("elements"):
                    return mirror, j
        except Exception as e:
            return mirror, None
        return mirror, None

    with ThreadPoolExecutor(len(MIRRORS)) as ex:
        futs = {ex.submit(get, m): m for m in MIRRORS}
        for f in as_completed(futs):
            mirror, res = f.result()
            if res:
                print(f"    успех: {mirror.split('/')[2]} ({len(res['elements'])} эл.)", flush=True)
                return res
    return None


def main():
    keys = sys.argv[1:]
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = {v["key"]: v for v in json.load(f)}

    for key in keys:
        v = villages[key]
        bbox = v["bbox_final"]
        print(f"\n=== {v['name']} ===", flush=True)
        q = f"""[out:json][timeout:120];
way["highway"]({bbox['lat_lo']},{bbox['lon_lo']},{bbox['lat_hi']},{bbox['lon_hi']});
(._;>;);
out body;"""
        for attempt in range(3):
            data = fetch_parallel(q)
            if data:
                n_ways = sum(1 for el in data["elements"] if el.get("type") == "way" and "nodes" in el)
                n_nodes = sum(1 for el in data["elements"] if el.get("type") == "node")
                print(f"  дорог: {n_ways}, узлов: {n_nodes}", flush=True)
                with open(os.path.join(OUTDIR, f"{key}.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                print(f"  сохранено: {key}.json", flush=True)
                break
            print(f"  попытка {attempt+1} не удалась, пауза 20с...", flush=True)
            time.sleep(20)

    print("\nГотово.", flush=True)


if __name__ == "__main__":
    main()
