#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55d: кропы карты в сматченных регионах + подписи ID зданий
для визуальной/VLM сверки с фрагментами заказчика."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_full = tr['M_full']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def m2f(x, y):
    return (M_full[0][0] * x + M_full[0][1] * y + M_full[0][2],
            M_full[1][0] * x + M_full[1][1] * y + M_full[1][2])


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts,
                         cx=sum(p[0] for p in pts) / len(pts),
                         cy=sum(p[1] for p in pts) / len(pts))

mapimg = Image.open(DIR / 'map06_v4.jpg').convert('RGB')
FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)

figs = json.load(open(DIR / 'fig_match.json'))
for name, m in figs.items():
    if m is None:
        continue
    x0, y0, x1, y1 = m['region']
    # расширяем контекст на 25%
    w, h = x1 - x0, y1 - y0
    X0, Y0 = max(0, x0 - w // 4), max(0, y0 - h // 4)
    X1 = min(mapimg.width, x1 + w // 4)
    Y1 = min(mapimg.height, y1 + h // 4)
    crop = mapimg.crop((X0, Y0, X1, Y1))
    dr = ImageDraw.Draw(crop)
    # здания в расширенном регионе: map -> frame -> mosaic
    mm = [m2f(X0, Y0 - 300), m2f(X1, Y1 - 300)]
    mx0, my0 = min(mm[0][0], mm[1][0]), min(mm[0][1], mm[1][1])
    mx1, my1 = max(mm[0][0], mm[1][0]), max(mm[0][1], mm[1][1])
    n = 0
    for bid, b in BLD.items():
        if not (mx0 - 60 <= b['cx'] <= mx1 + 60
                and my0 - 60 <= b['cy'] <= my1 + 60):
            continue
        pts = [(m2f(x, y)[0], m2f(x, y)[1] + 300 - Y0)
               for x, y in b['pts']]
        dr.line(pts + [pts[0]], fill=(255, 0, 255), width=5)
        c = (m2f(b['cx'], b['cy'])[0], m2f(b['cx'], b['cy'])[1] + 300 - Y0)
        dr.text((c[0] + 4, c[1] - 16), str(bid)[-3:], font=FONT,
                fill=(255, 0, 255), stroke_width=2,
                stroke_fill=(255, 255, 255))
        n += 1
    # рамка исходного региона матчинга
    dr.rectangle([x0 - X0, y0 - Y0, x1 - X0, y1 - Y0],
                 outline=(0, 255, 0), width=4)
    out = DIR / f'map_region_{name.replace(".png", "")}.jpg'
    crop.save(out, quality=92)
    print(f'{name}: {out.name} {crop.size} зданий подписано: {n}')
