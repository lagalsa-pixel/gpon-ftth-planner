#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55r: объективное измерение длины тени — профиль темноты
вдоль горизонтали через центр здания (тень слева по VLM img_10).
Эталоны: 282/289/290/291 (lv=2), 281 (lv=1). Проверяемые: 283, hh131."""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

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


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts,
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

frame = np.asarray(Image.open(
    BASE / 'upload/06_Алтайский_граница.jpg').convert('L')).astype(float)
Hf, Wf = frame.shape

SUBJ = {
    '289_barracks_lv2': 637127289,
    '290_barracks_lv2': 637127290,
    '291_barracks_lv2': 637127291,
    '282_barracks_lv2': 637127282,
    '281_private_lv1': 637127281,
    '283_check': 637127283,
}


def mos_to_frame(x, y):
    fx = M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2]
    fy = M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2]
    return fx, fy


def shadow_len(bid, side='left'):
    """Профиль яркости по горизонтали через центр здания;
    тень = тёмный пробег от края здания наружу."""
    b = BLD[bid]
    fx, fy = mos_to_frame(b['cx'], b['cy'])
    xs = [mos_to_frame(x, y)[0] for x, y in b['pts']]
    x0f, x1f = min(xs), max(xs)
    y0 = max(1, int(fy) - 4)
    y1 = min(Hf - 1, int(fy) + 4)
    if side == 'left':
        xs_range = range(max(0, int(x0f) - 130), int(x0f) + 2)
    else:
        xs_range = range(int(x1f) - 2, min(Wf, int(x1f) + 130))
    prof = []
    for x in xs_range:
        prof.append(frame[y0:y1, x].mean())
    prof = np.array(prof)
    if side == 'right':
        prof = prof[::-1]  # от края наружу
    # ищем тёмный пробег от края здания: первые подряд идущие
    # пиксели темнее порога (медиана окрестки - 25)
    tail = prof[10:] if len(prof) > 20 else prof
    med = np.median(tail) if len(tail) else 128
    thr = med - 28
    run = 0
    for v in prof:
        if v < thr:
            run += 1
        else:
            break
    return run, round(float(med), 1), round(float(thr), 1)


print(f'{"субъект":22s} {"тень слева px":>13s} {"тень справа px":>14s}')
res = {}
for name, bid in SUBJ.items():
    sl, _, _ = shadow_len(bid, 'left')
    sr, _, _ = shadow_len(bid, 'right')
    res[name] = dict(shadow_left_px=sl, shadow_right_px=sr)
    print(f'{name:22s} {sl:13d} {sr:14d}')

# hh131 (новое здание img_12): центр мозаики (3746.5, 7826)
fx, fy = mos_to_frame(3746.5, 7826.0)
y0, y1 = max(1, int(fy) - 4), min(Hf - 1, int(fy) + 4)
prof_l = [frame[y0:y1, x].mean() for x in range(int(fx) - 130, int(fx) + 2)]
prof_r = [frame[y0:y1, x].mean() for x in range(int(fx) - 2, int(fx) + 130)]
med = np.median(prof_l[10:] + prof_r[:-10])
thr = med - 28


def runlen(prof, thr):
    r = 0
    for v in prof:
        if v < thr:
            r += 1
        else:
            break
    return r


sl = runlen(prof_l[::-1], thr)   # от центра влево — грубо
sr = runlen(prof_r, thr)
res['hh131_check'] = dict(shadow_left_px=sl, shadow_right_px=sr,
                          note='центр здания, не край')
print(f'{"hh131_check":22s} {sl:13d} {sr:14d}   (от центра)')

json.dump(res, open(DIR / 'shadow_measure.json', 'w'), indent=1)
print('saved shadow_measure.json')
