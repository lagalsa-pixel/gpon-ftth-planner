#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54t: монтаж для заказчика — три найденных барака (289/290/291)
крупным планом с выносками, для сверки с его 3 фото."""
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
frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
FW, FH = frame.size

BARRACKS = [
    (637127289, '№1 · 13,5×39,7 м', '2-3 ТВ-антенны, ряд входов'),
    (637127290, '№2 · 13,4×32,9 м', '3 антенны, 4 подъезда'),
    (637127291, '№3 · 12,7×34,1 м', '4 антенны, 4 входа'),
]

try:
    f_big = ImageFont.truetype(
        '/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf', 34)
    f_small = ImageFont.truetype(
        '/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf', 26)
except Exception:
    f_big = ImageFont.load_default()
    f_small = f_big

PANEL_H = 640
panels = []
for bid, t1, t2 in BARRACKS:
    b = BLD[bid]
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    m_px = 10.0 / mpp
    fx0, fy0 = m2f(min(xs) - m_px, min(ys) - m_px)
    fx1, fy1 = m2f(max(xs) + m_px, max(ys) + m_px)
    fx0, fx1 = sorted((fx0, fx1))
    fy0, fy1 = sorted((fy0, fy1))
    ix0, iy0 = int(max(0, math.floor(fx0))), int(max(0, math.floor(fy0)))
    ix1, iy1 = int(min(FW, math.ceil(fx1))), int(min(FH, math.ceil(fy1)))
    crop = frame.crop((ix0, iy0, ix1, iy1))
    # повернуть: длинная ось горизонтально
    if crop.height > crop.width:
        crop = crop.rotate(90, expand=True)
    k = (PANEL_H - 90) / crop.height
    crop = crop.resize((int(crop.width * k), int(crop.height * k)),
                       Image.LANCZOS)
    panel = Image.new('RGB', (crop.width + 20, PANEL_H), (255, 255, 255))
    panel.paste(crop, (10, 80))
    d = ImageDraw.Draw(panel)
    d.text((12, 10), t1, fill=(160, 0, 0), font=f_big)
    d.text((12, 46), t2 + ' · 8 квартирных ДХ', fill=(60, 60, 60), font=f_small)
    panels.append(panel)

W = sum(p.width for p in panels) + 40
H = PANEL_H + 60
canvas = Image.new('RGB', (W, H), (255, 255, 255))
x = 10
for i, p in enumerate(panels):
    canvas.paste(p, (x, 50))
    if i:
        ImageDraw.Draw(canvas).line([(x - 5, 0), (x - 5, H)], fill=(0, 0, 0), width=3)
    x += p.width + 10
d = ImageDraw.Draw(canvas)
d.text((12, 8), 'Алтайский: три пропущенных жилых барака — критерий заказчика «ТВ-антенны на крыше» (снимок 0,19 м/px)',
       fill=(0, 0, 0), font=f_small)
out = BASE / 'download' / 'snp_vko' / 'altay_task54_barracks.jpg'
canvas.save(out, quality=92)
print('монтаж:', canvas.size, '->', out.name)
