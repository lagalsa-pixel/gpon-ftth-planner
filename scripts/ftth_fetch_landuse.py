#!/usr/bin/env python3
"""Поиск полигона с. Пригородное (landuse/residential, place) рядом с якорем."""
import json, os, random, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'osm_ftth')

MIRRORS = [
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.osm.jp/api/interpreter',
]
HEADERS = {'User-Agent': 'ftth-network-design-research/1.0'}

Q = '''[out:json][timeout:180];
(
  node["place"](50.27,83.44,50.40,83.62);
  way["landuse"~"residential|village|allotments"](50.27,83.44,50.40,83.62);
);
out geom;'''

for attempt in range(12):
    url = MIRRORS[attempt % len(MIRRORS)]
    try:
        print(f'попытка {attempt+1}: {url}', flush=True)
        r = requests.post(url, data={'data': Q}, headers=HEADERS, timeout=240)
        if r.status_code == 429:
            time.sleep(40); continue
        if r.status_code == 504:
            time.sleep(15); continue
        r.raise_for_status()
        data = r.json()
        els = data.get('elements', [])
        print(f'OK: {len(els)} элементов')
        for el in els:
            t = el.get('tags', {})
            if el['type'] == 'node':
                print(f"  node/{el.get('id')}: place={t.get('place')}, name={t.get('name')} @ ({el['lat']:.5f},{el['lon']:.5f})")
            else:
                geom = el.get('geometry') or []
                if len(geom) >= 3:
                    lats = [p['lat'] for p in geom]; lons = [p['lon'] for p in geom]
                    print(f"  way/{el.get('id')}: landuse={t.get('landuse')}, name={t.get('name')}, точек {len(geom)}, "
                          f"bbox ({min(lats):.5f},{min(lons):.5f},{max(lats):.5f},{max(lons):.5f})")
        if els:
            with open(os.path.join(OUT, 'prigorodnoe_landuse.json'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print('сохранено prigorodnoe_landuse.json')
            break
    except Exception as e:
        print(f'ОШИБКА: {type(e).__name__}: {str(e)[:120]}')
    time.sleep(random.uniform(15, 25))
