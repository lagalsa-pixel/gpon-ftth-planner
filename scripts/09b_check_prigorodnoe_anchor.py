# -*- coding: utf-8 -*-
"""Анализ кандидатов ОРШ для Пригородного в границах кадра: поиск нормального здания >= 80 м²."""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json

BASE = '/home/z/my-project'
key = 'prigorodnoe'
g = load_json(f'{BASE}/work/mosaic_geo.json')[key]
t = load_json(f'{vdir(key)}/crop_transform.json')
d = load_json(f'{vdir(key)}/osm.json')
hhs = load_json(f'{vdir(key)}/households.json')
mpp, west, north = g['mpp'], g['west'], g['north']

q = t['quad_old']
x0 = min(p[0] for p in q); x1 = max(p[0] for p in q)
y0 = min(p[1] for p in q); y1 = max(p[1] for p in q)
print(f'кадр: x [{x0:.0f}..{x1:.0f}], y [{y0:.0f}..{y1:.0f}]')

clat = sum(h['lat'] for h in hhs) / len(hhs)
clon = sum(h['lon'] for h in hhs) / len(hhs)
print(f'центроид ДХ (все {len(hhs)}): {clat:.5f}, {clon:.5f}')
hhs_in = [h for h in hhs if x0 <= h['cx'] <= x1 and y0 <= h['cy'] <= y1]
clat_i = sum(h['lat'] for h in hhs_in) / len(hhs_in)
clon_i = sum(h['lon'] for h in hhs_in) / len(hhs_in)
print(f'центроид ДХ в кадре ({len(hhs_in)}): {clat_i:.5f}, {clon_i:.5f}')

def geo_to_px(lat, lon):
    return ((lon - west) * 111320 * math.cos(math.radians(lat)) / mpp,
            (north - lat) * 111320 / mpp)

cands = []
for b in d['buildings']:
    la, lo = b['center']
    x, y = geo_to_px(la, lo)
    if not (x0 + 15 <= x <= x1 - 15 and y0 + 15 <= y <= y1 - 15):
        continue
    tags = b.get('tags', {})
    bt = tags.get('building', 'yes')
    if bt in ('garage', 'garages', 'barn', 'shed', 'greenhouse', 'roof', 'kiosk', 'hut'):
        continue
    cands.append(dict(id=b['id'], x=x, y=y, lat=la, lon=lo, area=b['area'], bt=bt,
                      name=tags.get('name', ''), amenity=tags.get('amenity', '')))

cands.sort(key=lambda c: -c['area'])
print(f'\nзданий-кандидатов в кадре: {len(cands)}; топ-15 по площади:')
for c in cands[:15]:
    dcent = math.hypot((c['lat'] - clat_i) * 111320, (c['lon'] - clon_i) * 111320 * math.cos(math.radians(c['lat'])))
    print(f"  id={c['id']} {c['area']:6.0f} м²  ({c['x']:5.0f},{c['y']:5.0f})  "
          f"тег={c['bt']}/{c['amenity']}/{c['name']}  от центра {dcent:4.0f} м")
