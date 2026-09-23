#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OSM-загрузка v4: зеркало maps.mail.ru, полный bbox тайлов, инкрементальное сохранение."""
import json, os, sys, time, urllib.request, urllib.parse

WORK = '/home/z/my-project/work'
OUT = f'{WORK}/osm_data.json'

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = {s['name']: s for s in json.load(f)}

EPS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

def overpass(query, timeout=120, tries=3):
    for a in range(tries):
        for ep in EPS:
            try:
                url = ep + "?" + urllib.parse.urlencode({"data": query})
                req = urllib.request.Request(url, headers={"User-Agent": "FTTH-plan-KZ/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.load(r)
            except Exception as e:
                print(f"    ! {ep.split('/')[2]}: {type(e).__name__}", flush=True)
    return None

def run_settlement(name):
    snp = SNPS[name]
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        g = json.load(f)
    s, w = g['lat_min'], g['lon_min']
    n, e = g['lat_max'], g['lon_max']

    print(f"=== {name} (ожид. {snp['households']} ДХ) ===", flush=True)
    t0 = time.time()
    q_b = f'[out:json][timeout:110];(way["building"]({s},{w},{n},{e}););out geom;'
    d = overpass(q_b)
    bld = [el for el in (d or {}).get('elements', []) if el.get('type') == 'way' and 'geometry' in el]
    print(f"  здания: {len(bld)} ({time.time()-t0:.0f} c)", flush=True)

    q_r = (f'[out:json][timeout:110];(way["highway"~"^(residential|unclassified|tertiary|secondary|'
           f'primary|living_street|service|track|pedestrian)$"]({s},{w},{n},{e}););out geom;')
    d = overpass(q_r)
    rds = [el for el in (d or {}).get('elements', []) if el.get('type') == 'way' and 'geometry' in el]
    print(f"  дороги: {len(rds)} ({time.time()-t0:.0f} c)", flush=True)

    return {
        'snp': snp,
        'buildings': [{'id': el['id'], 'tags': el.get('tags', {}),
                       'geom': [(p['lat'], p['lon']) for p in el['geometry']]} for el in bld],
        'roads': [{'id': el['id'], 'tags': el.get('tags', {}),
                   'geom': [(p['lat'], p['lon']) for p in el['geometry']]} for el in rds],
    }

def main():
    targets = sys.argv[1:] or list(SNPS.keys())
    results = {}
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            results = json.load(f)
    for name in targets:
        # перезагружаем всё заново чистым качественным зеркалом
        rec = run_settlement(name)
        if len(rec['buildings']) < 10:
            print("  ! пусто, пропуск сохранения", flush=True)
            continue
        results[name] = rec
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False)
        print(f"  СОХРАНЕНО: {len(rec['buildings'])} зданий, {len(rec['roads'])} дорог", flush=True)
    print("ГОТОВО", flush=True)

if __name__ == '__main__':
    main()
