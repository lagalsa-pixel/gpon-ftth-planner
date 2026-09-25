#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57 (a): анализ объектов правок — здание 637127295 (многоэтажка,
заказчик) и южный карман (4 частных дома у cv-hh131)."""
import json
import math
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
print(f'Мозаика Алтайского: mpp={mpp} м/px')


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts),
                        tags=b.get('tags', {}))

# --- 1. Геометрия 637127295 ---
b = BLD[637127295]
xs = [p[0] for p in b['pts']]
ys = [p[1] for p in b['pts']]
w = (max(xs) - min(xs)) * mpp
h = (max(ys) - min(ys)) * mpp
S_bbox = w * h
S_poly = b['poly'].area * mpp * mpp
long_m = max(w, h)
podezdy = max(1, round(long_m / 28.0))
print(f'\n=== 637127295 ===')
print(f'bbox: {w:.1f} x {h:.1f} м | S_bbox={S_bbox:.0f} м2 | '
      f'S_poly={S_poly:.0f} м2 | long={long_m:.1f} м')
print(f'центр (px): ({b["cx"]:.1f}, {b["cy"]:.1f})')
print(f'подъезды по формуле: {podezdy}')
for lv in (1.0, 2.0):
    n_a = round(min(lv * S_bbox / 55.0, lv * podezdy * 4))
    N = max(2, min(n_a, 400))
    print(f'  lv={lv}: N = round(min({lv}*{S_bbox:.0f}/55, '
          f'{lv}*{podezdy}*4)) = {N} ДХ')

# --- 2. Существующие дропы у 295 ---
net = json.load(open(BASE / f'work/{KEY}/network_hh2.json'))
drops = net['drops']
here = [d for d in drops if b['poly'].distance(Point(d['poly'][-1])) <= 14.0]
print(f'существующих дропов у 295: {len(here)} '
      f'{[d["hh_id"] for d in here]}')

# --- 3. Южный карман: что рядом с cv-hh131 (3746.5, 7826) ---
print('\n=== Южный карман (квадрат 60x60 м вокруг cv-hh131) ===')
cx, cy = 3746.5, 7826.0
R = 30.0 / mpp  # 30 м в пикселях
near_bld = []
for bid, bb in BLD.items():
    if abs(bb['cx'] - cx) < R * 2 and abs(bb['cy'] - cy) < R * 2:
        if bb['poly'].distance(Point(cx, cy)) < R * 2:
            xs2 = [p[0] for p in bb['pts']]
            ys2 = [p[1] for p in bb['pts']]
            w2 = (max(xs2) - min(xs2)) * mpp
            h2 = (max(ys2) - min(ys2)) * mpp
            near_bld.append((bid, w2, h2, bb['cx'], bb['cy'],
                             bb['tags'].get('building', '?'),
                             bb['tags'].get('building:levels', '-')))
for bid, w2, h2, bx, by, t, lv2 in sorted(near_bld, key=lambda z: z[0]):
    print(f'  OSM {bid}: {w2:.1f}x{h2:.1f} м @ ({bx:.0f},{by:.0f}) '
          f'{t} lv={lv2}')
dr_near = [d for d in drops
           if abs(d['poly'][-1][0] - cx) < R * 2
           and abs(d['poly'][-1][1] - cy) < R * 2]
print(f'дропов в квадрате: {len(dr_near)}: '
      f'{[(d["hh_id"], round(d["poly"][-1][0]), round(d["poly"][-1][1])) for d in dr_near]}')
