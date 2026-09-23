#!/usr/bin/env python3
"""Анализ OSM-данных: теги зданий, пространственное распределение, проверка краёв бокса."""
import json, math, os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'osm_ftth')

VILLAGES = [
    ('verkhneberezovka', 'Верхнеберезовка', 50.28420545, 82.20951200, 0.018, 0.025, 940),
    ('solnechnoe',       'Солнечное',       50.05177550, 82.71438134, 0.018, 0.025, 366),
    ('perevalnoe',       'Перевальное',     50.24139084, 82.28314297, 0.018, 0.025, 339),
    ('vinnoe',           'Винное',          50.05844487, 82.82687999, 0.018, 0.025, 490),
    ('prigorodnoe',      'Пригородное',     50.32198100, 83.52094976, 0.025, 0.035, 365),
    ('altayskiy',        'Алтайский',       50.24399825, 82.36103064, 0.018, 0.025, 716),
]

def dist_m(lat0, lon0, lat, lon):
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(lat0))
    return math.hypot((lat - lat0) * ky, (lon - lon0) * kx)

for key, name, alat, alon, mlat, mlon, exp in VILLAGES:
    data = json.load(open(os.path.join(OUT, f'{key}.json')))
    blds, roads = [], []
    for el in data['elements']:
        if el['type'] != 'way' or 'geometry' not in el:
            continue
        t = el.get('tags', {})
        if 'building' in t:
            blds.append(el)
        elif 'highway' in t:
            roads.append(el)
    tags = Counter(e['tags'].get('building', '?') for e in blds)
    hw = Counter(e['tags'].get('highway', '?') for e in roads)
    # распределение по расстоянию от якоря
    dists = []
    edge_hits = 0
    lat_lo, lat_hi, lon_lo, lon_hi = alat - mlat, alat + mlat, alon - mlon, alon + mlon
    for e in blds:
        lat = sum(p['lat'] for p in e['geometry']) / len(e['geometry'])
        lon = sum(p['lon'] for p in e['geometry']) / len(e['geometry'])
        dists.append(dist_m(alat, alon, lat, lon))
        # близость к краю бокса (<150 м)
        d_edge = min((lat - lat_lo) * 111132, (lat_hi - lat) * 111132,
                     (lon - lon_lo) * 111320 * math.cos(math.radians(alat)),
                     (lon_hi - lon) * 111320 * math.cos(math.radians(alat)))
        if d_edge < 150:
            edge_hits += 1
    dists.sort()
    n = len(dists)
    print(f'=== {name}: зданий {n} (ожид. ДХ {exp}), дорог {len(roads)}')
    print(f'    building-теги: {dict(tags.most_common(8))}')
    print(f'    highway-теги: {dict(hw.most_common(8))}')
    print(f'    расстояние от якоря: медиана {dists[n//2]:.0f} м, 90% {dists[int(n*0.9)]:.0f} м, макс {dists[-1]:.0f} м')
    print(f'    зданий ближе 150 м к краю бокса: {edge_hits}')
