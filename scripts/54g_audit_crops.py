#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54g: кропы 23 зданий полного аудита (0-1 дроп, >=14 м, в кадре)
+ 2x-апскейл. Исключая уже проверенных."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
FIGS = BASE / 'work/altay_remarks'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']


def m2f(x, y):
    return (M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2],
            M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2])


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {b['id']: b for b in osm['buildings']}

audit = json.load(open(FIGS / 't54_audit_list.json'))
frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
FW, FH = frame.size
MARGIN = 18

made = []
for bid, w, h, nd, cx, cy in audit:
    b = BLD[bid]
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    m_px = MARGIN / mpp
    fx0, fy0 = m2f(min(xs) - m_px, min(ys) - m_px)
    fx1, fy1 = m2f(max(xs) + m_px, max(ys) + m_px)
    fx0, fx1 = sorted((fx0, fx1))
    fy0, fy1 = sorted((fy0, fy1))
    ix0, iy0 = int(max(0, math.floor(fx0))), int(max(0, math.floor(fy0)))
    ix1, iy1 = int(min(FW, math.ceil(fx1))), int(min(FH, math.ceil(fy1)))
    if ix1 - ix0 < 30 or iy1 - iy0 < 30:
        print(f'{bid}: вне кадра — пропуск')
        continue
    crop = frame.crop((ix0, iy0, ix1, iy1))
    pts_px = [(m2f(x, y)[0] - ix0, m2f(x, y)[1] - iy0) for x, y in pts]
    dr = ImageDraw.Draw(crop)
    dr.line(pts_px + [pts_px[0]], fill=(255, 0, 255), width=4)
    p = FIGS / f't54_audit_{bid}.png'
    crop.save(p)
    up = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    up.save(str(p).replace('.png', '_2x.png'))
    made.append(bid)

print(f'кропов: {len(made)}')
