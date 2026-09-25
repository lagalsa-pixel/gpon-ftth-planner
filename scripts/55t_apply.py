#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55: применение замечаний заказчика (altay2.pdf через GitHub,
4 фрагмента, привязаны SIFT к карте v4: NCC 0.59-0.94 + template для img_10).

Заказчик: «Эти здания жилые». Идентификация фрагментов (VLM-пары, conf 0.95+):
  img_9  = бараки 637127290 + 637127291 — ПОДТВЕРЖДЕНО (уже 8+8 ДХ с Task 54)
  img_10 = барак 637127289      — ПОДТВЕРЖДЕНО (уже 8 ДХ)
  img_11 = 637127283 (9.3x28.9) — жилой 1-эт. барак, 4 крыльца
           (VLM-консенсус 4 проходов: lv=1) -> формула lv=1: 1 -> 4 ДХ
  img_12 = здание БЕЗ OSM-полигона (cv-hh 131, между бараками 282/271):
           1-эт. дуплекс, 2 крыльца (3 из 4 проходов) -> 1 -> 2 ДХ
Итого: +4 ДХ. Алтайский 635 -> 639; ВКО 3072 -> 3076.
"""
import json
import math
import shutil
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
NP = BASE / f'work/{KEY}' / 'network_hh2.json'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

# --- правка 1: 637127283 -> формула lv=1 (4 ДХ) ---
APT_BLD = [637127283]
# --- правка 2: cv-hh131 (img_12, без OSM) -> дуплекс 2 ДХ ---
HH131_SECOND = (3733.4, 7826.0)   # 5 м запад существующего дропа 131


def apt_n(b, lv=1.0):
    """Формула квартир пайплайна (как 53m/54q)."""
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    area = w * h
    long_m = max(w, h)
    podezdy = max(1, round(long_m / 28.0))
    n_a = round(min(lv * area / 55.0, lv * podezdy * 4))
    return max(2, min(n_a, 400)), w, h, long_m


def positions(b, N):
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    horiz = w >= h
    long_m = (w if horiz else h) * mpp
    spacing = min(6.0, long_m / (N + 1)) / mpp
    pos = []
    for i in range(N):
        off = (i - (N - 1) / 2.0) * spacing
        pos.append((b['cx'] + off, b['cy']) if horiz
                   else (b['cx'], b['cy'] + off))
    return pos


net = json.load(open(NP))
drops = net['drops']
max_id = max(d['hh_id'] for d in drops)
max_hh = max(d['hh'] for d in drops)
n0 = len(drops)


def drops_at(bid, tol=14.0):
    b = BLD[bid]
    return [d for d in drops
            if b['poly'].distance(Point(d['poly'][-1])) <= tol]


n_apt_added = 0
for bid in APT_BLD:
    b = BLD[bid]
    N, w, h, long_m = apt_n(b, lv=1.0)
    here = drops_at(bid)
    here.sort(key=lambda d: d['hh_id'])
    keep = here[0] if here else None
    for d in here[1:]:
        drops.remove(d)
    pos = positions(b, N)
    if keep is not None:
        for p in pos[1:]:
            max_id += 1
            max_hh += 1
            drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                              poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
            n_apt_added += 1
    else:
        for p in pos:
            max_id += 1
            max_hh += 1
            drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                              poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
            n_apt_added += 1
    print(f'  APT id={bid} {w:.1f}x{h:.1f} м (lv=1): N={N}, было дропов '
          f'{len(here)}, оставлен {keep["hh_id"] if keep else None}, '
          f'добавлено {N - (1 if keep else 0)}')

# --- правка 2: второй ДХ дуплекса img_12 (cv-hh131) ---
hh131_here = [d for d in drops
              if math.hypot(d['poly'][-1][0] - 3746.5,
                            d['poly'][-1][1] - 7826.0) < 40]
print(f'hh131 (img_12): существующих дропов рядом: {len(hh131_here)} '
      f'{[d["hh_id"] for d in hh131_here]}')
if len(hh131_here) == 1:
    max_id += 1
    max_hh += 1
    drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                      poly=[[HH131_SECOND[0], HH131_SECOND[1]],
                            [HH131_SECOND[0], HH131_SECOND[1]]],
                      length_m=0.0))
    n_apt_added += 1
    print(f'  дуплекс img_12: +1 ДХ (hh_id={max_id}) у '
          f'{HH131_SECOND} — стало 2')
else:
    print('  НЕОЖИДАННО: дропов у hh131 не 1 — правка пропущена!')

# --- итог ---
net['drops'] = drops
st = net.get('stats', {})
st['served'] = len(drops)
st['remark_task55'] = (
    f'+{n_apt_added} ДХ (altay2.pdf заказчика: 283 — жилой барак 1 эт. '
    f'1->4; cv-здание img_12 — дуплекс 1->2); бараки 289/290/291 '
    f'подтверждены заказчиком (без изменений)')
net['stats'] = st

shutil.copy(NP, NP.with_suffix('.json.bak_t55'))
json.dump(net, open(NP, 'w'), ensure_ascii=False)
print()
print(f'ИТОГО: дропов {n0} -> {len(drops)} (+{len(drops) - n0}); '
      f'добавлено {n_apt_added}')
