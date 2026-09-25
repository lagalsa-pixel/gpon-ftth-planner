#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57j: верификация правок Task 57.
(1) 637127295: ровно 8 дропов у контура, муфт внутри нет, длины разумные;
(2) 4 дома кармана: у каждого ровно 1 новый дроп, длины, ближайшая муфта."""
import json
import math
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp = geo['mpp']
WEST, NORTH = geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts))

net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))
drops = net['drops']
couplers = net['couplers']  # муфты: node, x, y, label
print(f'дропов в сети: {len(drops)}, муфт: {len(couplers)}')

# --- 1. 637127295 ---
b = BLD[637127295]
here = sorted([d for d in drops
               if b['poly'].distance(Point(d['poly'][-1])) <= 14.0],
              key=lambda d: d['hh_id'])
print(f'\n=== 637127295 (многоэтажка, ожидается 8 дропов) ===')
print(f'дропов у контура: {len(here)} (hh_id: {[d["hh_id"] for d in here]})')
assert len(here) == 8, 'Ожидалось 8 дропов!'
inside = [c for c in couplers if b['poly'].contains(Point(c['x'], c['y']))]
print(f'муфт внутри контура: {len(inside)}')
lens = [d['length_m'] for d in here]
print(f'длины дропов: {min(lens):.1f}..{max(lens):.1f} м')
near = sorted(here, key=lambda d: d['length_m'])[0]
print(f'исходный дроп hh_id=4 сохранён: '
      f'{"да" if any(d["hh_id"] == 4 for d in here) else "НЕТ!"}')

# --- 2. 4 дома ---
print(f'\n=== 4 дома южного кармана ===')
for name, hx, hy in [('h1', 3652.0, 7920.0), ('h2', 3701.0, 7904.0),
                     ('h3', 3810.0, 7899.0), ('h4', 3844.0, 7875.0)]:
    near_dr = [d for d in drops
               if math.hypot(d['poly'][-1][0] - hx,
                             d['poly'][-1][1] - hy) <= 20]
    near_sp = sorted(couplers, key=lambda c: math.hypot(
        c['x'] - hx, c['y'] - hy))[0]
    d_sp = math.hypot(near_sp['x'] - hx, near_sp['y'] - hy) * mpp
    print(f'{name} ({hx:.0f},{hy:.0f}): дропов в радиусе 20 px: '
          f'{len(near_dr)} (hh_id {[d["hh_id"] for d in near_dr]}, '
          f'длины {[round(d["length_m"], 1) for d in near_dr]}), '
          f'ближайшая муфта {near_sp.get("label", near_sp.get("node"))} '
          f'в {d_sp:.1f} м')
    assert len(near_dr) == 1, f'{name}: ожидался 1 дроп!'

# --- 3. полный итог ---
st = net.get('stats', {})
print(f'\nstats.served: {st.get("served")} ; всего дропов: {len(drops)}')
print('ВЕРИФИКАЦИЯ OK')
