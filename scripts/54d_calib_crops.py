#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54d: калибровка антенного критерия.
Кропы ИЗВЕСТНЫХ многоэтажек Task 53 (APT_BLD) + зданий R3, классифицированных
тогда как частные дома (289/291/290/288/279), + 2x-апскейл для видимости
мачт антенн. Плюс все кропы кандидатов в 2x.
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
tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']


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
    BLD[b['id']] = dict(pts=pts, cx=sum(xs)/len(xs), cy=sum(ys)/len(ys),
                         w=(max(xs)-min(xs))*mpp, h=(max(ys)-min(ys))*mpp)

# калибровка: заведомо жилые многоэтажки Task 53 (R1 два корпуса + барак 272
# + пара корпусов R2/R3) и «частные дома» R3, классификация которых под
# вопросом
CALIB = {
    # APT_BLD Task 53 (заведомо жилые, 2 этажа)
    496463512: 'APT_R1', 496463513: 'APT_R1',
    637127272: 'APT_R3_barracks',
    637127280: 'APT_R3', 637127294: 'APT_R2',
    496463485: 'APT_R2',
    # R3 «частные дома» Task 53 — под вопросом теперь
    637127288: 'R3_private?', 637127289: 'R3_private?',
    637127290: 'R3_private?', 637127291: 'R3_private?',
    637127279: 'R3_private?',
}

frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
FW, FH = frame.size
MARGIN = 18  # м

for bid, tag in CALIB.items():
    if bid not in BLD:
        print(f'{bid} ({tag}): НЕТ в OSM!')
        continue
    b = BLD[bid]
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    m_px = MARGIN / mpp
    mx0, mx1 = min(xs) - m_px, max(xs) + m_px
    my0, my1 = min(ys) - m_px, max(ys) + m_px
    fx0, fy0 = m2f(mx0, my0)
    fx1, fy1 = m2f(mx1, my1)
    fx0, fx1 = sorted((fx0, fx1))
    fy0, fy1 = sorted((fy0, fy1))
    ix0, iy0 = int(max(0, math.floor(fx0))), int(max(0, math.floor(fy0)))
    ix1, iy1 = int(min(FW, math.ceil(fx1))), int(min(FH, math.ceil(fy1)))
    if ix1 - ix0 < 30 or iy1 - iy0 < 30:
        print(f'{bid} ({tag}): вне кадра')
        continue
    crop = frame.crop((ix0, iy0, ix1, iy1))
    pts_px = [(m2f(x, y)[0] - ix0, m2f(x, y)[1] - iy0) for x, y in b['pts']]
    dr = ImageDraw.Draw(crop)
    dr.line(pts_px + [pts_px[0]], fill=(255, 0, 255), width=4)
    crop.save(FIGS / f't54_calib_{bid}.png')
    print(f'{bid} ({tag}): {b["w"]:.1f}x{b["h"]:.1f} м -> {crop.size[0]}x{crop.size[1]}')

# 2x-апскейл всех кропов кандидатов + калибровки (лanczos)
import glob
for p in glob.glob(str(FIGS / 't54_crop_*.png')) + glob.glob(str(FIGS / 't54_calib_*.png')):
    im = Image.open(p)
    if im.width * im.height > 4_000_000:
        continue
    up = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    up.save(str(p).replace('.png', '_2x.png'))
print('2x-апскейлы готовы')
