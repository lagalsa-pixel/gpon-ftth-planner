#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Надёжная загрузка OSM: квадрантные запросы, инкрементальное сохранение, фон."""
import json, time, math, urllib.request, urllib.parse, os, sys

WORK = '/home/z/my-project/work'
OUT = f'{WORK}/osm_data.json'
LOCK = f'{WORK}/osm_done.flag'

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

def overpass(query, tries=4, timeout=120):
    for attempt in range(tries):
        ep = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            url = ep + "?" + urllib.parse.urlencode({"data": query})
            req = urllib.request.Request(url, headers={"User-Agent": "FTTH-design-KZ/1.0 (network planning)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            print(f"  ! {ep.split('/')[2]} поп.{attempt+1}: {type(e).__name__} {e}", flush=True)
            time.sleep(5 + attempt * 5)
    return None

def bbox_around(lat, lon, half_m):
    dlat = half_m / 111320.0
    dlon = half_m / (111320.0 * max(0.1, math.cos(math.radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)

def query_chunk(s, w, n, e, kind):
    if kind == 'building':
        q = f'[out:json][timeout:110];(way["building"]({s},{w},{n},{e}););out geom;'
    else:
        q = (f'[out:json][timeout:110];(way["highway"~"^(residential|unclassified|tertiary|secondary|primary|'
             f'living_street|service|track)$"]({s},{w},{n},{e}););out geom;')
    return overpass(q)

# загрузка уже сделанного
results = {}
if os.path.exists(OUT):
    with open(OUT, encoding='utf-8') as f:
        results = json.load(f)

for snp in SNPS:
    name = snp['name']
    if name in results and results[name].get('roads'):
        print(f"=== {name}: уже загружено, пропуск", flush=True)
        continue
    print(f"\n=== {name} (ожид. {snp['households']} ДХ) ===", flush=True)
    t0 = time.time()

    # 4 квадранта по ±2.2 км
    R = 2200
    bb = bbox_around(snp['lat'], snp['lon'], R)
    clat, clon = snp['lat'], snp['lon']
    quadrants = [
        (clat - R/111320, clon - R/(111320*math.cos(math.radians(clat))), clat, clon),
        (clat - R/111320, clon, clat, clon + R/(111320*math.cos(math.radians(clat)))),
        (clat, clon - R/(111320*math.cos(math.radians(clat))), clat + R/111320, clon),
        (clat, clon, clat + R/111320, clon + R/(111320*math.cos(math.radians(clat)))),
    ]

    bld, rds = {}, {}
    for i, q in enumerate(quadrants):
        s, w, n, e = q
        d = query_chunk(s, w, n, e, 'building')
        if d:
            for el in d['elements']:
                if el.get('type') == 'way' and 'geometry' in el:
                    bld[el['id']] = {'id': el['id'], 'tags': el.get('tags', {}),
                                     'geom': [(p['lat'], p['lon']) for p in el['geometry']]}
        print(f"  квадрант {i+1}/4: зданий {len(bld)}", flush=True)
        time.sleep(1.5)

    for i, q in enumerate(quadrants):
        s, w, n, e = q
        d = query_chunk(s, w, n, e, 'highway')
        if d:
            for el in d['elements']:
                if el.get('type') == 'way' and 'geometry' in el:
                    rds[el['id']] = {'id': el['id'], 'tags': el.get('tags', {}),
                                     'geom': [(p['lat'], p['lon']) for p in el['geometry']]}
        print(f"  квадрант {i+1}/4: дорог {len(rds)}", flush=True)
        time.sleep(1.5)

    results[name] = {
        'snp': snp,
        'buildings': list(bld.values()),
        'roads': list(rds.values()),
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"  СОХРАНЕНО: {len(bld)} зданий, {len(rds)} дорог ({time.time()-t0:.0f} c)", flush=True)

open(LOCK, 'w').write('done')
print("\nВСЁ ГОТОВО", flush=True)
