#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55p: сравнение высот по теням — [283 | барак 289 (эталон lv=2) |
новое здание img_12 | частный дом (эталон lv=1)] на одном масштабе."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts,
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

# частный дом-эталон lv=1: 637127281 (5.7x15.4, 1 дроп, частный по Task 54)
frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg').convert('RGB')

SUBJ = [
    ('A', '283 (9.3x28.9)', 637127283),
    ('B', 'барак 289 (13.5x39.7, 2 эт.)', 637127289),
    ('C', 'новое img_12 (cv hh131)', None),  # центр мозаики (3746,7826)
    ('D', 'частный 281 (5.7x15.4, 1 эт.)', 637127281),
]

CELL = 260  # квадрат кадра для каждого субъекта
tiles = []
for tag, desc, bid in SUBJ:
    if bid:
        cx, cy = mos_to_map(BLD[bid]['cx'], BLD[bid]['cy'])
        fx, fy = cx, cy - 300
    else:
        # hh131: мозаика (3746.5, 7826) -> кадр
        fx = M_inv[0][0] * 3746.5 + M_inv[0][1] * 7826.0 + M_inv[0][2]
        fy = M_inv[1][0] * 3746.5 + M_inv[1][1] * 7826.0 + M_inv[1][2]
    c = frame.crop((int(fx - CELL / 2), int(fy - CELL / 2),
                    int(fx + CELL / 2), int(fy + CELL / 2)))
    c = c.resize((CELL * 3, CELL * 3), Image.LANCZOS)  # 3x
    dr = ImageDraw.Draw(c)
    f = ImageFont.truetype(
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 42)
    dr.text((14, 10), tag, font=f, fill=(255, 255, 0),
            stroke_width=3, stroke_fill=(0, 0, 0))
    tiles.append((tag, desc, c))

W = sum(t[2].width for t in tiles) + 30 * (len(tiles) + 1)
H = CELL * 3 + 130
canvas = Image.new('RGB', (W, H), (16, 16, 16))
dr = ImageDraw.Draw(canvas)
f = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 26)
x = 30
for tag, desc, c in tiles:
    canvas.paste(c, (x, 90))
    dr.text((x, 24), f'{tag}: {desc}', font=f, fill=(240, 240, 240))
    x += c.width + 30
canvas.save(DIR / 'shadow_compare.jpg', quality=93)
print('saved shadow_compare.jpg', canvas.size)
