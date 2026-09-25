#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54l: обзорный кроп района бараков с подписями ID зданий —
арбитражная VLM-классификация всех корпусов сразу (контекст решает)."""
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


def m2f(x, y):
    return (M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2],
            M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2])


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {b['id']: b for b in osm['buildings']}

# район: ряды бараков. mosaic x 2950-3850, y 7300-7900
X0, X1, Y0, Y1 = 2950, 3850, 7300, 7900
frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
fx0, fy0 = m2f(X0, Y0)
fx1, fy1 = m2f(X1, Y1)
ix0, iy0 = int(math.floor(min(fx0, fx1))), int(math.floor(min(fy0, fy1)))
ix1, iy1 = int(math.ceil(max(fx0, fx1))), int(math.ceil(max(fy0, fy1)))
crop = frame.crop((ix0, iy0, ix1, iy1))
CW, CH = crop.size
print('обзорный кроп:', crop.size)

try:
    font = ImageFont.truetype(
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
except Exception:
    font = ImageFont.load_default()

# подписываем здания в области
SHOW = {}
for bid, b in BLD.items():
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    if not (X0 <= cx <= X1 and Y0 <= cy <= Y1):
        continue
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    if max(w, h) < 12:
        continue
    # короткая метка: последние 2-3 цифры id
    lab = str(bid)[-3:]
    SHOW[bid] = (lab, pts, cx, cy, w, h)

d = ImageDraw.Draw(crop)
for bid, (lab, pts, cx, cy, w, h) in SHOW.items():
    ppx = [(m2f(x, y)[0] - ix0, m2f(x, y)[1] - iy0) for x, y in pts]
    d.line(ppx + [ppx[0]], fill=(255, 0, 255), width=4)
    tx = m2f(cx, cy)[0] - ix0
    ty = m2f(cx, cy)[1] - iy0
    d.text((tx - 25, ty - 15), lab, fill=(255, 255, 0), font=font)

out = FIGS / 't54_overview_barracks.png'
crop.save(out)
print(f'{len(SHOW)} зданий подписано -> {out.name}')

# легенда для запроса
items = sorted(SHOW.items(), key=lambda kv: (kv[1][3], kv[1][2]))
print('\nметки (последние 3 цифры id):')
for bid, (lab, pts, cx, cy, w, h) in items:
    print(f'  {lab} = {bid}: {w:.0f}x{h:.0f} м @ ({cx:.0f},{cy:.0f})')
