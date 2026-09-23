#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OSM-загрузка v3: bbox = охват тайлов, 4 квадранта, параллельно на 3 зеркала.
Инкрементальное сохранение после каждого СНП. Запуск: python3 fetch_osm3.py [Имя]"""
import json, math, os, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

WORK = '/home/z/my-project/work'
OUT = f'{WORK}/osm_data.json'

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = {s['name']: s for s in json.load(f)}

EPS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

def overpass_once(ep, query, timeout=100):
    url = ep + "?" + urllib.parse.urlencode({"data": query})
    req = urllib.request.Request(url, headers={"User-Agent": "FTTH-plan-KZ/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def query_parallel(queries):
    """queries: list of (kind, bbox). Возвращает dict way_id -> way."""
    ways = {}
    tasks = []
    for i, (kind, bb) in enumerate(queries):
        s, w, n, e = bb
        if kind == 'building':
            q = f'[out:json][timeout:90];(way["building"]({s},{w},{n},{e}););out geom;'
        else:
            q = (f'[out:json][timeout:90];(way["highway"~"^(residential|unclassified|tertiary|secondary|'
                 f'primary|living_street|service)$"]({s},{w},{n},{e}););out geom;')
        tasks.append((q, EPS[i % 3]))

    with ThreadPoolExecutor(max_workers=min(3, len(tasks))) as ex:
        futs = {ex.submit(overpass_once, ep, q): q for q, ep in tasks}
        for fut in futs:
            try:
                d = fut.result()
                for el in d.get('elements', []):
                    if el.get('type') == 'way' and 'geometry' in el:
                        ways[el['id']] = {'id': el['id'], 'tags': el.get('tags', {}),
                                          'geom': [(p['lat'], p['lon']) for p in el['geometry']]}
            except Exception as ex_:
                print(f"    ! ошибка: {type(ex_).__name__} {ex_}", flush=True)
    return ways

def run_settlement(name):
    snp = SNPS[name]
    geo_path = f'{WORK}/geo/{name}.json'
    with open(geo_path, encoding='utf-8') as f:
        g = json.load(f)
    lat_c = (g['lat_max'] + g['lat_min']) / 2
    lon_c = (g['lon_min'] + g['lon_max']) / 2
    lat_half = (g['lat_max'] - g['lat_min']) / 2
    lon_half = (g['lon_max'] - g['lon_min']) / 2

    quadrants = [
        (lat_c - lat_half, lon_c - lon_half, lat_c, lon_c),
        (lat_c - lat_half, lon_c, lat_c, lon_c + lon_half),
        (lat_c, lon_c - lon_half, lat_c + lat_half, lon_c),
        (lat_c, lon_c, lat_c + lat_half, lon_c + lon_half),
    ]
    print(f"=== {name} (ожид. {snp['households']} ДХ) ===", flush=True)
    t0 = time.time()

    # волна 1: здания (4 квадранта на 3 зеркала)
    bld = query_parallel([('building', q) for q in quadrants])
    print(f"  здания: {len(bld)} ({time.time()-t0:.0f} c)", flush=True)
    # волна 2: дороги
    rds = query_parallel([('highway', q) for q in quadrants])
    print(f"  дороги: {len(rds)} ({time.time()-t0:.0f} c)", flush=True)

    # повторные попытки для недокачанных квадрантов — по количеству, оценке полноты
    return {'snp': snp, 'buildings': list(bld.values()), 'roads': list(rds.values())}

def main():
    targets = sys.argv[1:] or list(SNPS.keys())
    results = {}
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            results = json.load(f)
    for name in targets:
        if name in results and results[name].get('buildings'):
            print(f"=== {name}: уже есть ({len(results[name]['buildings'])} зд.)", flush=True)
            continue
        rec = run_settlement(name)
        results[name] = rec
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False)
        print(f"  СОХРАНЕНО: {len(rec['buildings'])} зданий, {len(rec['roads'])} дорог", flush=True)
    print("ГОТОВО", flush=True)

if __name__ == '__main__':
    main()
