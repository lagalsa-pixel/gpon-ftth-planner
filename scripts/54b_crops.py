#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54: кропы кандидатов из кадра заказчика (0.19 м/px) + кропы
вне кадра из тайлов z18 (0.38 м/px).

Выход: work/altay_remarks/t54_crop_<id>.png (+ подпись размеров).
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
FIGS = BASE / 'work/altay_remarks'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
MW, MH = geo['W'], geo['H']

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']
QX0, QX1 = tr['quad_old'][0][0], tr['quad_old'][1][0]
QY0, QY1 = tr['quad_old'][0][1], tr['quad_old'][2][1]


def m2f(x, y):
    return (M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2],
            M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2])


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    BLD[b['id']] = dict(
        pts=pts,
        cx=sum(xs) / len(xs), cy=sum(ys) / len(ys),
        w=(max(xs) - min(xs)) * mpp, h=(max(ys) - min(ys)) * mpp,
        lv=b.get('tags', {}).get('building:levels', ''),
        btype=b.get('tags', {}).get('building', 'yes'))

cands = json.load(open(FIGS / 't54_candidates.json'))

frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
FW, FH = frame.size
print('кадр:', frame.size)

MARGIN = 25  # м вокруг здания — видно соседей и крыши

made = []
for c in cands:
    bid = c['id']
    b = BLD[bid]
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    m_px = MARGIN / mpp
    # в mosaic px с запасом
    mx0, mx1 = x0 - m_px, x1 + m_px
    my0, my1 = y0 - m_px, y1 + m_px
    # уголок кадра
    fx0, fy0 = m2f(mx0, my0)
    fx1, fy1 = m2f(mx1, my1)
    fx0, fx1 = sorted((fx0, fx1))
    fy0, fy1 = sorted((fy0, fy1))
    ix0, iy0 = int(max(0, math.floor(fx0))), int(max(0, math.floor(fy0)))
    ix1, iy1 = int(min(FW, math.ceil(fx1))), int(min(FH, math.ceil(fy1)))
    if ix1 - ix0 < 40 or iy1 - iy0 < 40:
        print(f'{bid}: вне кадра ({ix1-ix0}x{iy1-iy0}) — пропуск')
        continue
    crop = frame.crop((ix0, iy0, ix1, iy1))
    # контур здания (переводим вершины в координаты кропа)
    pts_px = [(m2f(x, y)[0] - ix0, m2f(x, y)[1] - iy0) for x, y in b['pts']]
    dr = ImageDraw.Draw(crop)
    dr.line(pts_px + [pts_px[0]], fill=(255, 0, 255), width=4)
    p = FIGS / f't54_crop_{bid}.png'
    crop.save(p)
    made.append((bid, c['w'], c['h'], c['n_drops'], crop.size))

print(f'\nсделано {len(made)} кропов:')
for bid, w, h, nd, sz in made:
    print(f'  {bid}: {w}x{h} м, дропов {nd}, кроп {sz[0]}x{sz[1]}')
