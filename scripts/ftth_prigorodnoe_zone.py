#!/usr/bin/env python3
"""Подбор правила зоны для с. Пригородное: радиус + исключение landuse-полигонов Риддера."""
import json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftth_households import (parse_buildings, single_linkage, local_frame,
                             make_households, point_in_ring)

BASE = os.path.dirname(os.path.abspath(__file__))
OSM_DIR = os.path.join(BASE, 'osm_ftth')

ANCHOR = (50.32198100, 83.52094976)
PLACE_NODE = (50.32097, 83.51958)
VILLAGE_POLY_IDS = {1338095842, 919956284}  # полигоны села Пригородное (1338095843 — Аэродромное)

data = json.load(open(os.path.join(OSM_DIR, 'prigorodnoe.json')))
ky, kx = local_frame(ANCHOR[0])
blds = parse_buildings(data, ky, kx)

lu = json.load(open(os.path.join(OSM_DIR, 'prigorodnoe_landuse.json')))
city_rings, village_rings, allot_rings = [], [], []
for el in lu['elements']:
    if el['type'] != 'way' or 'geometry' not in el:
        continue
    pts = [(p['lat'], p['lon']) for p in el['geometry']]
    if len(pts) < 4 or pts[0] != pts[-1]:
        continue
    ring = pts[:-1]
    t = el.get('tags', {})
    if t.get('landuse') == 'allotments':
        allot_rings.append(ring)
    elif el['id'] in VILLAGE_POLY_IDS:
        village_rings.append(ring)
    else:
        city_rings.append(ring)
print(f'полигонов: городских {len(city_rings), } сельских {len(village_rings)}, дачных {len(allot_rings)}')

xy = np.array([[b['lat'] * ky, b['lon'] * kx] for b in blds])
axy = np.array([ANCHOR[0] * ky, ANCHOR[1] * kx])
d = np.hypot(xy[:, 0] - axy[0], xy[:, 1] - axy[1])


def zone_rule_A(R):
    keep = []
    for i, b in enumerate(blds):
        if d[i] > R:
            continue
        if any(point_in_ring(b['lat'], b['lon'], r) for r in city_rings):
            continue
        if any(point_in_ring(b['lat'], b['lon'], r) for r in allot_rings):
            continue
        keep.append(i)
    if not keep:
        return []
    cxy = xy[keep]
    labels = single_linkage(cxy, 350.0)
    ai = int(np.argmin(d))
    a_lab = labels[keep.index(ai)]
    return [keep[k] for k in range(len(keep)) if labels[k] == a_lab]


def zone_rule_B(buf=300.0):
    """Сельские полигоны + буфер."""
    from ftth_households import point_in_ring
    keep = []
    for i, b in enumerate(blds):
        # внутри сельского полигона?
        inp = any(point_in_ring(b['lat'], b['lon'], r) for r in village_rings)
        if not inp:
            # или ближе buf к любому узлу сельского полигона / place-узлу
            best = 1e18
            for r in village_rings:
                for (la, lo) in r:
                    dd = math.hypot((la - b['lat']) * ky, (lo - b['lon']) * kx)
                    best = min(best, dd)
            dd = math.hypot((PLACE_NODE[0] - b['lat']) * ky, (PLACE_NODE[1] - b['lon']) * kx)
            best = min(best, dd)
            if best > buf:
                continue
        if any(point_in_ring(b['lat'], b['lon'], r) for r in city_rings):
            continue
        if any(point_in_ring(b['lat'], b['lon'], r) for r in allot_rings):
            continue
        keep.append(i)
    return keep


for R in (950, 1000, 1050, 1100, 1200, 1300):
    zone = zone_rule_A(R)
    if not zone:
        print(f'A) R={R}: пусто'); continue
    zb = [blds[i] for i in zone]
    hh = make_households(zb, 18.0, ky, kx)
    lats = [b['lat'] for b in zb]; lons = [b['lon'] for b in zb]
    print(f'A) R={R} м: зданий {len(zb)}, ДХ@18м {len(hh)} (ожид. 365), '
          f'зона {(max(lons)-min(lons))*kx:.0f}x{(max(lats)-min(lats))*ky:.0f} м')

for buf in (200, 300, 450):
    zone = zone_rule_B(buf)
    if not zone:
        print(f'B) buf={buf}: пусто'); continue
    zb = [blds[i] for i in zone]
    hh = make_households(zb, 18.0, ky, kx)
    lats = [b['lat'] for b in zb]; lons = [b['lon'] for b in zb]
    print(f'B) полигоны+буфер {buf} м: зданий {len(zb)}, ДХ@18м {len(hh)} (ожид. 365), '
          f'зона {(max(lons)-min(lons))*kx:.0f}x{(max(lats)-min(lats))*ky:.0f} м')
