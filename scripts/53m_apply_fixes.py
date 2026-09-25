#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 53: применение замечаний заказчика по Алтайскому к network_hh2.json.

Замечания (download/snp_vko/altay.pdf, 6 рисунков, регионы верифицированы
SIFT+NCC 0.94-0.98):
  R1 (2 корпуса), R2 (6 корпусов), R3 (10 корпусов) — многоэтажные жилые
      дома: каждому N квартир по формуле пайплайна
      (N = max(2, min(round(min(lv*S_bbox/55, lv*подъезды*4)), 400)),
       lv=2, подъезды = max(1, round(long/28))); позиции вдоль длинной оси.
  R4 — 4 частных дома без дропов: добавить 4 ДХ.
  R5 — фундамент будущего дома (mosaic 3942,5863): добавить 1 ДХ.
  R6 — 6 двухквартирных домов (по 2 ДХ): +6 ДХ; рядом ряд из 4 жилых домов
      без дропов: +4 ДХ.
  Руины 637127293 — ложный ДХ hh_id=6 (внутри руин): удалить.
"""
import json
import math
import shutil
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
NP = BASE / f'work/{KEY}' / 'network_hh2.json'

# ---------- геометрия ----------
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

# ---------- множества правок ----------
# id -> число квартир (формула, посчитана вручную выше, пересчёт в скрипте)
APT_BLD = [496463512, 496463513,
           496463514, 496463485, 496463483, 496463515, 496463482, 496463480,
           637127294, 637127280, 637127287, 637127285, 637127272,
           637127270, 637127282, 637127271, 637127284, 637127292, 496463481]
DUPLEX = [496463491, 496463492, 496463493, 496463496, 496463495, 496463494]
ROW3 = [496463500, 496463499, 496463498, 496463497]
R4 = [759801038, 759801037, 759801036, 759801035]
R5_PT = (3942.0, 5863.0)
RUINS_REMOVE = [6]          # hh_id ложных ДХ (руины 637127293)


def apt_n(b):
    """Формула квартир пайплайна (ftth_pipeline _hh2_refine C)."""
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    area = w * h
    long_m = max(w, h)
    lv = 2.0
    podezdy = max(1, round(long_m / 28.0))
    n_a = round(min(lv * area / 55.0, lv * podezdy * 4))
    return max(2, min(n_a, 400)), w, h, long_m


def positions(b, N):
    """N позиций вдоль длинной оси (как в пайплайне)."""
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    horiz = w >= h
    long_px = w if horiz else h
    long_m = long_px * mpp
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

# ---------- 1) руины: удалить ложные ----------
drops = [d for d in drops if d['hh_id'] not in RUINS_REMOVE]
removed = n0 - len(drops)
print(f'удалено ложных ДХ (руины): {removed}')

# ---------- 2) многоэтажки ----------
def drops_at(bid, tol=14.0):
    b = BLD[bid]
    return [d for d in drops
            if b['poly'].distance(Point(d['poly'][-1])) <= tol]


n_apt_added = n_apt_removed = 0
for bid in APT_BLD:
    b = BLD[bid]
    N, w, h, long_m = apt_n(b)
    here = drops_at(bid)
    here.sort(key=lambda d: d['hh_id'])
    keep = here[0] if here else None
    for d in here[1:]:
        drops.remove(d)
        n_apt_removed += 1
    pos = positions(b, N)
    if keep is not None:
        # первая позиция = существующий дроп (сохраняем его маршрут/двор)
        for i, p in enumerate(pos[1:], start=1):
            max_id += 1
            max_hh += 1
            drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                              poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
            n_apt_added += 1
    else:
        for i, p in enumerate(pos):
            max_id += 1
            max_hh += 1
            drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                              poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
            n_apt_added += 1
    print(f'  APT id={bid} {w:.1f}x{h:.1f}м: N={N}, было дропов {len(here)}, '
          f'оставлен {keep["hh_id"] if keep else None}, '
          f'добавлено {N - (1 if keep else 0)}')

# ---------- 3) двухквартирные R6 ----------
for bid in DUPLEX:
    b = BLD[bid]
    here = drops_at(bid)
    if not here:
        print(f'  !! DUPLEX id={bid}: нет существующего дропа')
        continue
    # вторая позиция: смещение на четверть длины вдоль длинной оси
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    horiz = (x1 - x0) >= (y1 - y0)
    off = ((x1 - x0) / 4.0 if horiz else 0.0,
           0.0 if horiz else (y1 - y0) / 4.0)
    p = (b['cx'] + off[0], b['cy'] + off[1])
    max_id += 1
    max_hh += 1
    drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                      poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
    n_apt_added += 1
print(f'DUPLEX: +{len(DUPLEX)} ДХ (по 2 на дом)')

# ---------- 4) R4 + ряд R6 + фундамент R5 ----------
for group, name in [(R4, 'R4'), (ROW3, 'R6row3')]:
    for bid in group:
        b = BLD[bid]
        p = (b['cx'], b['cy'])
        max_id += 1
        max_hh += 1
        drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                          poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
        n_apt_added += 1
    print(f'{name}: +{len(group)} ДХ')

max_id += 1
max_hh += 1
drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                  poly=[[R5_PT[0], R5_PT[1]], [R5_PT[0], R5_PT[1]]],
                  length_m=0.0))
print(f'R5 фундамент: +1 ДХ (hh_id={max_id})')

# ---------- итог ----------
net['drops'] = drops
st = net.get('stats', {})
st['served'] = len(drops)
st['remark_task53'] = (f'+{n_apt_added} ДХ (квартиры многоэтажек R1-R3, '
                       f'двухквартирные R6, новые дома R4/R6row3, фундамент R5), '
                       f'-{n_apt_removed + removed} ложных/лишних')
net['stats'] = st

shutil.copy(NP, NP.with_suffix('.json.bak_t53'))
json.dump(net, open(NP, 'w'), ensure_ascii=False)
print()
print(f'ИТОГО: дропов {n0} -> {len(drops)} '
      f'(+{len(drops) - n0}); удалено {n_apt_removed + removed}; '
      f'добавлено {n_apt_added + 1}')
