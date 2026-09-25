#!/usr/bin/env python3
"""Task 53: монтажи кропов зданий-кандидатов для VLM-классификации.

Кроп из кадра (0.19 м/px) вокруг каждого здания, подпись буквой.
Калибровка: R1 (многоэтажные по заказчику), R6 lv=1/lv=2 (по OSM).
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
FIGS = BASE / 'work/altay_remarks'
KEY = 'altaiskiy'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def geo_to_px(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def mosaic_to_frame(x, y):
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2])


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [mosaic_to_frame(*geo_to_px(la, lo)) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=np.array(pts), tags=b.get('tags', {}))

frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg').convert('RGB')
FW_, FH_ = frame.size

GROUPS = {
    'A_calib': [('R1_mnogo', 496463512), ('R1_mnogo', 496463513),
                ('R6_lv2', 496463491), ('R6_lv2', 496463494),
                ('R6_lv1', 496463498), ('R6_lv1', 496463500),
                ('R2_mnogo', 496463514), ('R2_mnogo', 496463485)],
    'B_r3a': [('R3', 637127294), ('R3', 637127280), ('R3', 637127287),
              ('R3', 637127285), ('R3', 637127272), ('R3', 637127278),
              ('R3', 637127293), ('R3', 637127295)],
    'C_r3b': [('R3', 637127270), ('R3', 637127289), ('R3', 637127282),
              ('R3', 637127271), ('R3', 637127284), ('R3', 637127292),
              ('R3', 637127291), ('R3', 637127290)],
    'D_r3c_r4': [('R3', 637127288), ('R3', 496463481), ('R3', 637127279),
                 ('R3', 637127286), ('R4', 759801038), ('R4', 759801037),
                 ('R4', 759801036), ('R4', 759801035)],
}

CROP = 260          # половина стороны кропа
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)

for gname, items in GROUPS.items():
    tiles = []
    for label, bid in items:
        b = BLD[bid]
        pts = b['pts']
        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        x0 = int(max(0, cx - CROP))
        y0 = int(max(0, cy - CROP))
        x1 = int(min(FW_, cx + CROP))
        y1 = int(min(FH_, cy + CROP))
        c = frame.crop((x0, y0, x1, y1))
        d = ImageDraw.Draw(c)
        # контур здания
        poly = [(p[0] - x0, p[1] - y0) for p in pts]
        d.line(poly + [poly[0]], fill=(255, 0, 255), width=3)
        tiles.append((label, bid, c))

    # монтаж 4x2
    TW, TH = 2 * CROP, 2 * CROP
    cols = 4
    rows = math.ceil(len(tiles) / cols)
    canvas = Image.new('RGB', (cols * TW, rows * (TH + 44)), (20, 20, 20))
    dr = ImageDraw.Draw(canvas)
    for i, (label, bid, c) in enumerate(tiles):
        r, col = divmod(i, cols)
        canvas.paste(c, (col * TW, r * (TH + 44) + 44))
        dr.text((col * TW + 10, r * (TH + 44) + 6),
                f'{chr(65 + i)} [{label} id={bid}]', font=FONT,
                fill=(255, 255, 0))
    p = FIGS / f'montage_{gname}.jpg'
    canvas.save(p, quality=88)
    print(f'{gname}: {canvas.size} -> {p.name}  '
          f'({[f"{chr(65+i)}={bid}" for i, (l, bid) in enumerate(items)]})')
