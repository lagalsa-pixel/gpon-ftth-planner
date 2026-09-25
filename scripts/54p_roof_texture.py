#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54p: объективная проверка 283 — текстура крыши (HSV-статистика
внутри полигона) против эталонов: жилые бараки 282/284/481 vs руины 293."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

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

frame = cv2.imread(str(BASE / 'upload/06_Алтайский_граница.jpg'))
FH, FW = frame.shape[:2]

GROUPS = {
    'ЖИЛОЙ_БАРАК (эталон)': [637127282, 637127284, 496463481, 637127287],
    'НОВЫЕ бараки': [637127289, 637127290, 637127291],
    'РУИНЫ (эталон)': [637127293],
    'ПРОВЕРЯЕМЫЙ 283': [637127283],
    'АДМИН 295': [637127295],
}

print(f'{"группа":28} {"id":>11} {"крыша%":>7} {"раст%":>6} {"яркость":>8} '
      f'{"текстура":>9} {"ровность":>8}')


def stats(bid):
    b = BLD[bid]
    pts_m = [g2p(la, lo) for la, lo in b['poly']]
    # маска в координатах кадра
    pts_f = [m2f(x, y) for x, y in pts_m]
    xs = [p[0] for p in pts_f]
    ys = [p[1] for p in pts_f]
    x0, x1 = int(max(0, min(xs))), int(min(FW, max(xs)))
    y0, y1 = int(max(0, min(ys))), int(min(FH, max(ys)))
    if x1 - x0 < 5 or y1 - y0 < 5:
        return None
    mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
    poly = np.array([[(p[0] - x0, p[1] - y0)] for p in pts_f], np.int32)
    cv2.fillPoly(mask, [poly], 255)
    patch = frame[y0:y1, x0:x1]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    m = mask > 0
    n = m.sum()
    if n < 50:
        return None
    h = hsv[:, :, 0][m].astype(float)
    s = hsv[:, :, 1][m].astype(float)
    v = hsv[:, :, 2][m].astype(float)
    # крыша: низкая насыщенность (серые/бурые кровли) или синие тона, не зелень
    veg = ((h >= 35) & (h <= 85) & (s > 60)).mean()          # зелень
    roofish = 1.0 - veg
    # ровность крыши: std яркости внутри (у руин выше из-за провалов)
    # текстура: средний градиент Лапласа
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(float)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_64F))
    tex = lap[m].mean()
    return roofish * 100, veg * 100, v.mean(), tex, v.std()


for gname, ids in GROUPS.items():
    for bid in ids:
        r = stats(bid)
        if not r:
            print(f'{gname:28} {bid:>11} вне кадра')
            continue
        print(f'{gname:28} {bid:>11} {r[0]:>6.1f} {r[1]:>5.1f} '
              f'{r[2]:>8.1f} {r[3]:>9.2f} {r[4]:>8.1f}')
