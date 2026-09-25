#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54n: решающие 4x-кропы БЕЗ контура (контур мог перекрывать антенны)
для 289/290/291/283/295 + пары «барак-близнец | подозреваемый»."""
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

# пары: (подтверждённый барак-эталон, подозреваемый)
PAIRS = [
    (637127282, 637127289),   # 13.5x39.8 vs 13.5x39.7 — близнецы!
    (637127284, 637127290),   # 14x35.1 vs 13.4x32.9
    (496463481, 637127291),   # 12.8x35.7 vs 12.7x34.1 — близнецы!
    (637127284, 637127283),   # сосед по ряду
]
SOLO = [637127295]  # 36.7x40.6 — большой, отдельный 4x

MARGIN = 8  # м — только само здание + край крыши (антенны у края!)


def crop4x(bid, margin_m=MARGIN, draw_contour=False):
    b = BLD[bid]
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    m_px = margin_m / mpp
    fx0, fy0 = m2f(min(xs) - m_px, min(ys) - m_px)
    fx1, fy1 = m2f(max(xs) + m_px, max(ys) + m_px)
    fx0, fx1 = sorted((fx0, fx1))
    fy0, fy1 = sorted((fy0, fy1))
    ix0, iy0 = int(max(0, math.floor(fx0))), int(max(0, math.floor(fy0)))
    ix1, iy1 = int(min(FW, math.ceil(fx1))), int(min(FH, math.ceil(fy1)))
    crop = frame.crop((ix0, iy0, ix1, iy1))
    if draw_contour:
        ppx = [(m2f(x, y)[0] - ix0, m2f(x, y)[1] - iy0) for x, y in pts]
        d = ImageDraw.Draw(crop)
        d.line(ppx + [ppx[0]], fill=(255, 0, 255), width=3)
    return crop


try:
    font = ImageFont.truetype(
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 26)
except Exception:
    font = ImageFont.load_default()

for ref_id, sus_id in PAIRS:
    a = crop4x(ref_id)
    b = crop4x(sus_id)
    H = 860

    def fit4(im):
        k = H / im.height
        w = int(im.width * k)
        return im.resize((w, H), Image.LANCZOS)

    a4, b4 = fit4(a), fit4(b)
    W = max(a4.width, b4.width) + 20
    canvas = Image.new('RGB', (W * 2 + 20, H + 60), (255, 255, 255))
    canvas.paste(a4, (10, 50))
    canvas.paste(b4, (W + 10, 50))
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), 'A: жилой барак (эталон)', fill=(180, 0, 0), font=font)
    d.text((W + 10, 8), f'B: здание ..{str(sus_id)[-3:]}', fill=(0, 0, 180), font=font)
    d.line([(W, 0), (W, H + 60)], fill=(0, 0, 0), width=3)
    out = FIGS / f't54_x4_pair_{sus_id}.png'
    canvas.save(out)
    print(f'{sus_id}: пара с {ref_id} -> {out.name} {canvas.size}')

for bid in SOLO:
    c = crop4x(bid, margin_m=15)
    H = 860
    k = H / c.height
    c4 = c.resize((int(c.width * k), H), Image.LANCZOS)
    out = FIGS / f't54_x4_solo_{bid}.png'
    c4.save(out)
    print(f'{bid}: соло -> {out.name} {c4.size}')
