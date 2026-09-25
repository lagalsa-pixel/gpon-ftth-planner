#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54r: верификация рендера — кроп карты Алтайского с районом бараков
289/290/291 + пиксельная проверка новых дропов (как 53n)."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
FIGS = BASE / 'work/altay_remarks'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']
HH = 300  # шапка карты


def m2f(x, y):
    return (M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2],
            M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2])


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {b['id']: b for b in osm['buildings']}
net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))
drops = net['drops']
couplers = {c['node']: c for c in net['couplers']}

# ---- 1) пиксельная проверка новых дропов ----
NEW_BLD = {637127289: 8, 637127290: 8, 637127291: 8}
from shapely.geometry import Point, Polygon

print('=== пиксельная проверка бараков Task 54 ===')
ok_all = True
for bid, N in NEW_BLD.items():
    b = BLD[bid]
    pts = [g2p(la, lo) for la, lo in b['poly']]
    poly = Polygon(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    here = [d for d in drops if poly.distance(Point(d['poly'][-1])) <= 20.0]
    # все дропы заканчиваются внутри/у контура?
    inside = sum(1 for d in here if poly.distance(Point(d['poly'][-1])) <= 3.0)
    # муфта назначена?
    no_c = sum(1 for d in here if d.get('coupler') is None)
    lens = [d['length_m'] for d in here if d.get('length_m')]
    status = 'OK' if len(here) == N and no_c == 0 else 'FAIL'
    if status != 'OK':
        ok_all = False
    print(f'{bid} ({w:.0f}x{h:.0f} м): дропов {len(here)}/{N}, у контура '
          f'{inside}, без муфты {no_c}, длины '
          f'{min(lens):.0f}-{max(lens):.0f} м -> {status}')

# дроп в руинах должен исчезнуть
ruins = BLD[637127293]
rpts = [g2p(la, lo) for la, lo in ruins['poly']]
rpoly = Polygon(rpts)
n_ruins = sum(1 for d in drops if rpoly.distance(Point(d['poly'][-1])) <= 3.0)
print(f'руины 637127293: дропов внутри {n_ruins} (ожидается 0) -> '
      f'{"OK" if n_ruins == 0 else "FAIL"}')
if n_ruins:
    ok_all = False
print('ПИКСЕЛЬНАЯ ПРОВЕРКА:', 'ВСЕ OK' if ok_all else 'ЕСТЬ ОШИБКИ')

# ---- 2) кроп карты с районом бараков ----
X0, X1, Y0, Y1 = 2950, 3850, 7250, 7900  # mosaic
fx0, fy0 = m2f(X0, Y0)
fx1, fy1 = m2f(X1, Y1)
ix0, iy0 = int(min(fx0, fx1)), int(min(fy0, fy1)) + HH
ix1, iy1 = int(max(fx0, fx1)), int(max(fy0, fy1)) + HH
mp = BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg'
m = Image.open(mp)
crop = m.crop((max(0, ix0), max(0, iy0), min(m.width, ix1), min(m.height, iy1)))
out = FIGS / 't54_map_render_check.png'
crop.save(out)
print('кроп карты:', crop.size, '->', out.name)

# ---- 3) общий итог по сети Алтайского ----
st = net.get('stats', {})
print('\nСеть Алтайского (hh3):', json.dumps(
    {k: st[k] for k in ['served', 'couplers', 'feeder_km', 'drop_km']
     if k in st}, ensure_ascii=False))
