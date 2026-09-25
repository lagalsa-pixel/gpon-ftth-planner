#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54: применение правок по новому замечанию заказчика (3 фото,
канал загрузок не работал — правки по антенному критерию заказчика
«ТВ-антенны на крыше = жилой многоэтажный дом»).

Полный аудит кадра Алтайского (VLM 4 прохода: 1x/2x/пары-эталоны/4x-близнецы
+ обзор района + текстура крыши):
  + 637127289 (13.5x39.7 м) — барак: 2-3 антенны, ряд входов, близнец
    подтверждённого барака 637127282 (13.5x39.8) -> 8 квартирных ДХ
  + 637127290 (13.4x32.9 м) — барак: 3 антенны, 4 подъезда, lv=2 -> 8 ДХ
  + 637127291 (12.7x34.1 м) — барак: 4 антенны, 4 входа, плоская крыша,
    lv=2, близнец 496463481 (12.8x35.7) -> 8 ДХ
  - дроп 326 — второй ложный ДХ внутри руин 637127293 (в Task 53 удалён
    hh_id=6, этот остался)
  Не тронуты (противоречивые свидетельства, вопрос заказчику):
  637127283 (руины/гараж?), 637127295 (админздание), 637127288 (сарай?)
  — все остаются с их текущими 1 ДХ.
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

APT_NEW = [637127289, 637127290, 637127291]
RUINS_REMOVE = [326]           # hh_id ложного ДХ в руинах 637127293


def apt_n(b):
    """Формула квартир пайплайна (как в 53m): lv=2."""
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

# ---------- 1) руины: удалить ложный дроп ----------
drops = [d for d in drops if d['hh_id'] not in RUINS_REMOVE]
removed = n0 - len(drops)
print(f'удалено ложных ДХ (руины, hh_id={RUINS_REMOVE}): {removed}')


def drops_at(bid, tol=14.0):
    b = BLD[bid]
    return [d for d in drops if b['poly'].distance(Point(d['poly'][-1])) <= tol]


n_apt_added = 0
for bid in APT_NEW:
    b = BLD[bid]
    N, w, h, long_m = apt_n(b)
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
    print(f'  APT id={bid} {w:.1f}x{h:.1f} м: N={N}, было дропов {len(here)}, '
          f'оставлен {keep["hh_id"] if keep else None}, '
          f'добавлено {N - (1 if keep else 0)}')

# ---------- итог ----------
net['drops'] = drops
st = net.get('stats', {})
st['served'] = len(drops)
st['remark_task54'] = (f'+{n_apt_added} ДХ (квартиры бараков 289/290/291 — '
                       f'антенный критерий заказчика), -{removed} ложный (руины 293, дроп 326)')
net['stats'] = st

shutil.copy(NP, NP.with_suffix('.json.bak_t54'))
json.dump(net, open(NP, 'w'), ensure_ascii=False)
print()
print(f'ИТОГО: дропов {n0} -> {len(drops)} '
      f'(+{len(drops) - n0}); удалено {removed}; добавлено {n_apt_added}')
