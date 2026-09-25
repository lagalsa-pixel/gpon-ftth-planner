#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55d v2: кропы карты с ПРАВИЛЬНЫМИ подписями ID.
Цепочки: map->frame (y-300); frame->mosaic (M_full);
mosaic->frame (M_inv); frame->map (y+300)."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_full = tr['M_full']   # frame -> mosaic
M_inv = tr['M_inv']     # mosaic -> frame
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
import math
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def mos_to_map(x, y):
    fx = M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2]
    fy = M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2]
    return fx, fy + 300


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                         cx=sum(p[0] for p in pts) / len(pts),
                         cy=sum(p[1] for p in pts) / len(pts))

net = json.load(open(BASE / f'work/{KEY}/network_hh2.json'))
drops = net['drops']


def drops_at(bid, tol=14.0):
    b = BLD[bid]
    return [d for d in drops
            if b['poly'].distance(Point(d['poly'][-1])) <= tol]


mapimg = Image.open(DIR / 'map06_v4.jpg').convert('RGB')
FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 34)

REGIONS = {
    'img_9': [1604, 5856, 2129, 6247],
    'img_10': [1419, 6159, 1654, 6581],
    'img_11': [1844, 6588, 1984, 6938],
    'img_12': [2209, 6650, 2496, 6861],
}

for name, (x0, y0, x1, y1) in REGIONS.items():
    w, h = x1 - x0, y1 - y0
    X0, Y0 = max(0, x0 - w // 3), max(0, y0 - h // 3)
    X1 = min(mapimg.width, x1 + w // 3)
    Y1 = min(mapimg.height, y1 + h // 3)
    crop = mapimg.crop((X0, Y0, X1, Y1))
    dr = ImageDraw.Draw(crop)
    n = 0
    rows = []
    for bid, b in BLD.items():
        mx, my = mos_to_map(b['cx'], b['cy'])
        if not (X0 - 80 <= mx <= X1 + 80 and Y0 - 80 <= my <= Y1 + 80):
            continue
        pts = [(mos_to_map(x, y)[0] - X0, mos_to_map(x, y)[1] - Y0)
               for x, y in b['pts']]
        dr.line(pts + [pts[0]], fill=(255, 0, 255), width=5)
        dr.text((pts[0][0] + 4, pts[0][1] - 40), str(bid)[-3:],
                font=FONT, fill=(255, 0, 255), stroke_width=2,
                stroke_fill=(255, 255, 255))
        xs = [p[0] for p in b['pts']]
        ys = [p[1] for p in b['pts']]
        bw = (max(xs) - min(xs)) * mpp
        bh = (max(ys) - min(ys)) * mpp
        incore = x0 <= mx <= x1 and y0 <= my <= y1
        rows.append((bid, f'{bw:.1f}x{bh:.1f}', len(drops_at(bid)),
                     incore, f'map=({mx:.0f},{my:.0f})'))
        n += 1
    dr.rectangle([x0 - X0, y0 - Y0, x1 - X0, y1 - Y0],
                 outline=(0, 255, 0), width=4)
    out = DIR / f'region2_{name}.jpg'
    crop.save(out, quality=93)
    print(f'{name}: {out.name} {crop.size}, зданий в кропе: {n}')
    for bid, size, nd, ic, pos in sorted(rows, key=lambda r: -r[2]):
        print(f'   {bid} {size}м drops={nd} core={ic} {pos}')
