#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54: инвентаризация кандидатов в пропущенные многоэтажки (Алтайский).

Новый критерий заказчика: ТВ-антенны на крыше = жилой многоэтажный дом.
Шаг 1: найти все здания, которые МОГЛИ быть пропущены:
  - длинные (>= 30 м) бараки/корпуса, не входящие в 19 APT_BLD Task 53;
  - building:levels >= 2;
  - кадр заказчика покрывает только юг мозаики — пометить in_frame.
Шаг 2: посчитать текущие дропы у каждого (расстояние до контура <= 14 м).
"""
import json
import math
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
MW, MH = geo['W'], geo['H']

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']
QUAD = tr['quad_old']  # [[x0,y0],[x1,y0],[x1,y1],[x0,y1]] в mosaic px
QX0, QX1 = QUAD[0][0], QUAD[1][0]
QY0, QY1 = QUAD[0][1], QUAD[2][1]


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def mosaic_to_frame(x, y):
    """mosaic px -> frame px (кадр заказчика 0.19 м/px)."""
    return (M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2],
            M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2])


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    BLD[b['id']] = dict(
        pts=pts, poly=Polygon(pts),
        cx=sum(xs) / len(xs), cy=sum(ys) / len(ys),
        w=w, h=h, long=max(w, h), area_bbox=w * h,
        lv=b.get('tags', {}).get('building:levels', ''),
        btype=b.get('tags', {}).get('building', 'yes'),
    )

# здания, уже обработанные в Task 53
APT_BLD = {496463512, 496463513, 496463514, 496463485, 496463483,
           496463515, 496463482, 496463480, 637127294, 637127280,
           637127287, 637127285, 637127272, 637127270, 637127282,
           637127271, 637127284, 637127292, 496463481}
DUPLEX = {496463491, 496463492, 496463493, 496463496, 496463495, 496463494}
ROW3 = {496463500, 496463499, 496463498, 496463497}
R4 = {759801038, 759801037, 759801036, 759801035}
RUINS = {637127293}
DONE53 = APT_BLD | DUPLEX | ROW3 | R4 | RUINS

# текущие дропы
net = json.load(open(BASE / f'work/{KEY}/network_hh2.json'))
drops = net['drops']

# -------- кандидаты --------
cands = []
for bid, b in BLD.items():
    if bid in DONE53:
        continue
    is_long = b['long'] >= 30.0
    try:
        is_lv = float(b['lv'] or 0) >= 2
    except ValueError:
        is_lv = False
    if not (is_long or is_lv):
        continue
    # дропы рядом
    n_dr = sum(1 for d in drops
               if b['poly'].distance(Point(d['poly'][-1])) <= 14.0)
    in_frame = (QX0 - 60 <= b['cx'] <= QX1 + 60 and
                QY0 - 60 <= b['cy'] <= QY1 + 60)
    cands.append(dict(id=bid, w=round(b['w'], 1), h=round(b['h'], 1),
                      long=round(b['long'], 1), lv=b['lv'],
                      btype=b['btype'], n_drops=n_dr,
                      in_frame=bool(in_frame),
                      cx=round(b['cx'], 1), cy=round(b['cy'], 1)))

cands.sort(key=lambda c: -c['long'])
print(f'кандидатов: {len(cands)} (из {len(BLD)} зданий,.done53={len(DONE53)})')
print(f'{"id":>12} {"w×h м":>14} {"long":>5} {"lv":>3} {"тип":>12} '
      f'{"дропы":>5} {"кадр":>4}')
for c in cands:
    print(f'{c["id"]:>12} {c["w"]:>6.1f}x{c["h"]:<6.1f} {c["long"]:>5.0f} '
          f'{c["lv"] or "-":>3} {c["btype"]:>12} {c["n_drops"]:>5} '
          f'{"да" if c["in_frame"] else "НЕТ":>4}')

json.dump(cands, open(BASE / 'work/altay_remarks/t54_candidates.json', 'w'),
          ensure_ascii=False, indent=1)
print('-> work/altay_remarks/t54_candidates.json')

# статистика по всем зданиям: сколько с дропами 0
no_drop = [bid for bid, b in BLD.items() if bid not in DONE53 and
           not any(b['poly'].distance(Point(d['poly'][-1])) <= 14.0
                   for d in drops)]
print(f'\nзданий без дропов вообще (вне DONE53): {len(no_drop)}')
