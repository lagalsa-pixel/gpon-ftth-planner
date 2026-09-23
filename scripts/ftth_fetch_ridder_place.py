#!/usr/bin/env python3
"""Получение полигона городской застройки Риддера (place=city) для исключения из с. Пригородное."""
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
  way["place"~"city|town"]["name"~"Риддер|Ridder"](50.28,83.42,50.42,83.64);
  relation["place"~"city|town"]["name"~"Риддер|Ridder"](50.28,83.42,50.42,83.64);
  way["landuse"="residential"]["name"~"Риддер|Ridder"](50.28,83.42,50.42,83.64);
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
            geom = el.get('geometry') or []
            print(f"  {el['type']}/{el.get('id')}: place={t.get('place')}, landuse={t.get('landuse')}, name={t.get('name')}, точек {len(geom)}")
        if els:
            with open(os.path.join(OUT, 'ridder_place.json'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print('сохранено ridder_place.json')
            break
    except Exception as e:
        print(f'ОШИБКА: {type(e).__name__}: {str(e)[:120]}')
    time.sleep(random.uniform(15, 25))
