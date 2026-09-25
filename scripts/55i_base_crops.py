#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55i: кропы базового кадра (без оверлея) для 283 и региона img_12."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def mos_to_map(x, y):
    fx = M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2]
    fy = M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2]
    return fx, fy + 300


frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg').convert('RGB')
print('frame:', frame.size)

osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=__import__('shapely.geometry',
        fromlist=['Polygon']).Polygon(pts),
        cx=sum(p[0] for p in pts) / len(pts),
        cy=sum(p[1] for p in pts) / len(pts))

# --- 283: кроп с рамкой и ближ. контекстом, 2x и 4x ---
b = BLD[637127283]
mx, my = mos_to_map(b['cx'], b['cy'])
fx, fy = mx, my - 300  # frame coords центра
print(f'283 center: map=({mx:.0f},{my:.0f}) frame=({fx:.0f},{fy:.0f})')
M = 120
c = frame.crop((int(fx - M), int(fy - M), int(fx + M), int(fy + M)))
dr = ImageDraw.Draw(c)
# контур 283 в координатах кропа
pts = [(mos_to_map(x, y)[0] - (fx - M), mos_to_map(x, y)[1] - 300 - (fy - M))
       for x, y in b['pts']]
dr.line(pts + [pts[0]], fill=(255, 0, 255), width=4)
c.save(DIR / 'base_283_1x.jpg', quality=95)
c.resize((c.width * 2, c.height * 2), Image.LANCZOS).save(
    DIR / 'base_283_2x.jpg', quality=95)

# --- регион img_12 на кадре: без зданий OSM, ищем неизвестное ---
X0, Y0, X1, Y1 = 2209 - 100, 6350 - 100, 2496 + 100, 6561 + 100
c2 = frame.crop((X0, Y0, X1, Y1))
c2.save(DIR / 'base_img12_1x.jpg', quality=95)
c2.resize((c2.width * 2, c2.height * 2), Image.LANCZOS).save(
    DIR / 'base_img12_2x.jpg', quality=95)
c2.resize((c2.width * 3, c2.height * 3), Image.LANCZOS).save(
    DIR / 'base_img12_3x.jpg', quality=95)
print('283 crop:', c.size, ' img12 crop:', c2.size)

# что за здания OSM ближайшие к центру региона img_12
cx_m, cy_m = (X0 + X1) / 2, (Y0 + Y1) / 2 + 300  # map coords центра
best = []
for bid, bb in BLD.items():
    mx, my = mos_to_map(bb['cx'], bb['cy'])
    d = math.hypot(mx - cx_m, my - cy_m)
    best.append((d, bid, mx, my))
best.sort()
print('ближайшие OSM к центру img_12 (map px):')
for d, bid, mx, my in best[:5]:
    print(f'   {bid}: {d:.0f} px, map=({mx:.0f},{my:.0f})')
