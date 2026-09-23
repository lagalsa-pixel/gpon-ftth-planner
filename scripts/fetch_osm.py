#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка OSM данных (здания + дороги) по всем 6 СНП через Overpass API.
Широкий bbox ±3 км для оценки протяжённости застройки."""
import json, time, urllib.request, urllib.parse

with open('/home/z/my-project/work/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

def overpass(query, tries=3):
    for ep in ENDPOINTS:
        for attempt in range(tries):
            try:
                url = ep + "?" + urllib.parse.urlencode({"data": query})
                req = urllib.request.Request(url, headers={"User-Agent": "FTTH-design-KZ/1.0"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            except Exception as e:
                print(f"  ! {ep.split('/')[2]} попытка {attempt+1}: {e}")
                time.sleep(3)
    return None

def bbox_around(lat, lon, half_m_lat=3000):
    dlat = half_m_lat / 111320.0
    dlon = half_m_lat / (111320.0 * max(0.1, __import__('math').cos(__import__('math').radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)

results = {}
for snp in SNPS:
    name = snp['name']
    print(f"\n=== {name} (ожидается {snp['households']} ДХ) ===")
    bb = bbox_around(snp['lat'], snp['lon'], 3000)
    # Здания
    q_b = f'[out:json][timeout:180];(way["building"]({bb[0]},{bb[1]},{bb[2]},{bb[3]}););out geom;'
    data_b = overpass(q_b)
    # Дороги
    q_r = f'[out:json][timeout:180];(way["highway"]({bb[0]},{bb[1]},{bb[2]},{bb[3]}););out geom;'
    data_r = overpass(q_r)

    rec = {'snp': snp, 'bbox_query': bb, 'buildings': [], 'roads': []}
    if data_b:
        rec['buildings'] = [
            {'id': el['id'], 'tags': el.get('tags', {}), 'geom': [(p['lat'], p['lon']) for p in el['geometry']]}
            for el in data_b['elements'] if el.get('type') == 'way' and 'geometry' in el
        ]
    if data_r:
        rec['roads'] = [
            {'id': el['id'], 'tags': el.get('tags', {}), 'geom': [(p['lat'], p['lon']) for p in el['geometry']]}
            for el in data_r['elements'] if el.get('type') == 'way' and 'geometry' in el
        ]
    n_res = sum(1 for b in rec['buildings'] if b['tags'].get('building') not in (None,) )
    n_roads_res = sum(1 for r in rec['roads'] if r['tags'].get('highway') in
                      ('residential', 'unclassified', 'tertiary', 'secondary', 'primary', 'living_street', 'service'))
    print(f"  Зданий: {len(rec['buildings'])} | дорог (уличные): {n_roads_res} / всего {len(rec['roads'])}")
    results[name] = rec
    time.sleep(2)

with open('/home/z/my-project/work/osm_data.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False)
print("\nСохранено: work/osm_data.json")
