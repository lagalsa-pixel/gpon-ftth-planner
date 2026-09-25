#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57i: применение правок заказчика (ответы на вопросы Task 55).

1) «4 частных дома подключи» — южный карман (вопросный кроп Task 55,
   привязка NCC 0.9992): 4 дома без дропов, каждый +1 ДХ:
     h1 (3652,7920) 11x15 м, белая/голубая крыша
     h2 (3701,7904) 11x7 м, светло-голубая
     h3 (3810,7899) 11x11 м, красная/розовая
     h4 (3844,7875) 7.6x11.4 м, белая/серая, крыльцо E3
   (cv-hh304 (3863,7996) — отдельный дом юго-восточнее, уже с дропом —
   не трогаем)
2) «Здание 637127295 — многоэтажка, увеличь абонентов» — VLM 2x/x4:
   2 этажа; формула пайплайна lv=2, подъезды=round(40.6/28)=1,
   N = round(min(2*1490/55, 2*1*4)) = 8 ДХ (было 1, +7; дроп hh_id=4
   сохранён как первая квартира).

Итого: +11 ДХ. Алтайский 639 -> 650; ВКО 3076 -> 3087.
"""
import json
import math
import shutil
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
NP = BASE / f'work/{KEY}' / 'network_hh2.json'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp = geo['mpp']


def g2p_local(la, lo, WEST=geo['west'], NORTH=geo['north']):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p_local(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

net = json.load(open(NP))
drops = net['drops']
max_id = max(d['hh_id'] for d in drops)
max_hh = max(d['hh'] for d in drops)
n0 = len(drops)

# ---------- правка 1: 637127295 -> многоэтажка, формула lv=2 ----------
bid = 637127295
b = BLD[bid]
xs = [p[0] for p in b['pts']]
ys = [p[1] for p in b['pts']]
w = (max(xs) - min(xs)) * mpp
h = (max(ys) - min(ys)) * mpp
S_bbox = w * h
long_m = max(w, h)
podezdy = max(1, round(long_m / 28.0))
lv = 2.0
n_a = round(min(lv * S_bbox / 55.0, lv * podezdy * 4))
N = max(2, min(n_a, 400))
print(f'637127295: {w:.1f}x{h:.1f} м, lv=2, подъезды={podezdy} -> N={N}')

here = [d for d in drops if b['poly'].distance(Point(d['poly'][-1])) <= 14.0]
here.sort(key=lambda d: d['hh_id'])
keep = here[0] if here else None
for d in here[1:]:
    drops.remove(d)
print(f'  было дропов: {len(here)}, сохранён hh_id='
      f'{keep["hh_id"] if keep else None}, удалено {len(here) - (1 if keep else 0)}')

# позиции вдоль длинной оси (как 53m/55t)
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
horiz = (x1 - x0) >= (y1 - y0)
spacing = min(6.0, long_m / (N + 1)) / mpp
pos = []
for i in range(N):
    off = (i - (N - 1) / 2.0) * spacing
    pos.append((b['cx'] + off, b['cy']) if horiz
               else (b['cx'], b['cy'] + off))
added_295 = 0
if keep is not None:
    for p in pos[1:]:
        max_id += 1
        max_hh += 1
        drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                          poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
        added_295 += 1
else:
    for p in pos:
        max_id += 1
        max_hh += 1
        drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                          poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
        added_295 += 1
print(f'  добавлено квартир: {added_295} -> всего {N} ДХ')

# ---------- правка 2: 4 частных дома южного кармана ----------
HOUSES = [
    ('h1', 3652.0, 7920.0),
    ('h2', 3701.0, 7904.0),
    ('h3', 3810.0, 7899.0),
    ('h4', 3844.0, 7875.0),
]
added_houses = 0
for name, hx, hy in HOUSES:
    # защита: не попасть в OSM-здание и не дублировать существующий дроп
    d_min_osm = min((bb['poly'].distance(Point(hx, hy)), bid2)
                    for bid2, bb in BLD.items())
    d_min_drop = min(math.hypot(d['poly'][-1][0] - hx,
                                d['poly'][-1][1] - hy) for d in drops)
    print(f'{name} ({hx:.0f},{hy:.0f}): до ближайшего OSM '
          f'{d_min_osm[0]:.1f} px ({d_min_osm[0] * mpp:.1f} м, id='
          f'{d_min_osm[1]}), до ближайшего дропа {d_min_drop:.1f} px')
    assert d_min_osm[0] > 15, f'{name}: слишком близко к OSM {d_min_osm}'
    assert d_min_drop > 15, f'{name}: слишком близко к существующему дропу'
    max_id += 1
    max_hh += 1
    drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                      poly=[[hx, hy], [hx, hy]], length_m=0.0))
    added_houses += 1
    print(f'  +1 ДХ (hh_id={max_id})')

# ---------- итог ----------
net['drops'] = drops
st = net.get('stats', {})
st['served'] = len(drops)
st['remark_task57'] = (
    f'+{added_295 + added_houses} ДХ (ответы заказчика на вопросы Task 55: '
    f'637127295 — многоэтажка, 1->{N} по формуле lv=2; южный карман — '
    f'4 частных дома по 1 ДХ)')
net['stats'] = st

shutil.copy(NP, NP.with_suffix('.json.bak_t57'))
json.dump(net, open(NP, 'w'), ensure_ascii=False)
print()
print(f'ИТОГО: дропов {n0} -> {len(drops)} (+{len(drops) - n0}); '
      f'295: +{added_295}, дома: +{added_houses}')
