#!/usr/bin/env python3
"""Task 53 (v2): этажность по теням — адаптивный порог + единое направление.

1) Направление тени: 8 кандидатов; для каждого меряем тень калибровочных
   домов R6 (lv=1 и lv=2 известны). Направление с максимальным разделением
   групп = направление тени.
2) Адаптивный порог: тень = темнее локальной медианы окрестности на DELTA.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
FRAME_MPP = 0.1909

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
img = cv2.imread(str(BASE / 'upload/06_Алтайский_граница.jpg'),
                 cv2.IMREAD_GRAYSCALE).astype(np.float64)
FH, FW = img.shape

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


def bbox_of(bid):
    pts = BLD[bid]['pts']
    return pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max()


def ring_median(bid, pad=90):
    x0, x1, y0, y1 = bbox_of(bid)
    X0, X1 = max(0, int(x0 - pad)), min(WW, int(x1 + pad))
    Y0, Y1 = max(0, int(y0 - pad)), min(FH, int(y1 + pad))
    if X1 <= X0 or Y1 <= Y0:
        return 128.0
    patch = img[Y0:Y1, X0:X1].copy()
    # маска здания + его внутренности исключаем
    cv2.fillPoly(patch.astype(np.uint8),
                 [BLD[bid]['pts'].astype(np.int32) -
                  np.array([[[X0, Y0]]]).astype(np.int32)], 255)
    patch = patch[patch < 250]
    return float(np.median(patch)) if patch.size else 128.0


WW = FW


def shadow_towards(bid, direction, max_m=30.0):
    """Тень от стены здания в заданном направлении direction=(dx,dy).
    Возвращает медианную длину в метрах."""
    x0, x1, y0, y1 = bbox_of(bid)
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    med = ring_median(bid)
    thr = med - 22.0
    dx, dy = direction
    lens = []
    n_s = 28
    # точки старта: вдоль стены, перпендикулярной направлению
    for i in range(n_s):
        t = (i + 0.5) / n_s
        if abs(dx) >= abs(dy):
            # старт с вертикальной стены x0 или x1
            sx = x1 if dx > 0 else x0
            sy = y0 + h * t
            # если направление диагонально — старт с угла сектора
            if dy != 0:
                sy = y1 if dy > 0 else y0
                sx = (x1 if dx > 0 else x0)
                sy = sy - (h * (1 - t)) * (1 if dy > 0 else -1)
                sy = min(max(sy, y0), y1)
        else:
            sy = y1 if dy > 0 else y0
            sx = x0 + w * t
            if dx != 0:
                sx = x1 if dx > 0 else x0
                sx = sx - (w * (1 - t)) * (1 if dx > 0 else -1)
                sx = min(max(sx, x0), x1)
        xx, yy = sx + dx * 1.5, sy + dy * 1.5
        dark = 0.0
        best = 0.0
        gap = 0.0
        max_px = max_m / FRAME_MPP
        for k in range(int(max_px)):
            xi, yi = int(round(xx)), int(round(yy))
            if not (0 <= xi < WW and 0 <= yi < FH):
                break
            v = img[yi, xi]
            if v < thr:
                dark += 1.0
                best = max(best, dark)
                gap = 0.0
            else:
                gap += 1.0
                dark = 0.0
                if gap > 14:      # 2.7 м яркого разрыва = тень кончилась
                    break
            xx += dx
            yy += dy
        lens.append(best * FRAME_MPP)
    lens.sort()
    return lens[len(lens) // 2]


DIRS = {
    'E': (1, 0), 'W': (-1, 0), 'S': (0, 1), 'N': (0, -1),
    'SE': (1, 1), 'SW': (-1, 1), 'NE': (1, -1), 'NW': (-1, -1),
}
CAL2 = [496463491, 496463492, 496463493, 496463496, 496463495, 496463494]
CAL1 = [496463500, 496463499, 496463498, 496463497]

print('=== Определение направления тени (разделение lv=2 / lv=1) ===')
best_dir, best_sep = None, -1
for nm, d in DIRS.items():
    s2 = [shadow_towards(b, d) for b in CAL2]
    s1 = [shadow_towards(b, d) for b in CAL1]
    m2, m1 = sorted(s2)[3], sorted(s1)[2]
    sep = m2 - m1
    print(f'  {nm}: lv2 med={m2:.1f}м lv1 med={m1:.1f}м sep={sep:+.1f}')
    if sep > best_sep:
        best_dir, best_sep = nm, sep
print(f'НАПРАВЛЕНИЕ ТЕНИ: {best_dir} (sep={best_sep:.1f}м)')

d = DIRS[best_dir]
print()
print('=== Калибровка в направлении тени ===')
for b in CAL2:
    print(f'  lv=2 id={b}: {shadow_towards(b, d):.1f}м')
for b in CAL1:
    print(f'  lv=1 id={b}: {shadow_towards(b, d):.1f}м')

CAND = {
    'R1': [496463512, 496463513],
    'R2': [496463514, 496463485, 496463483, 496463515, 496463482, 496463480],
    'R3': [637127294, 637127280, 637127293, 637127270, 637127289,
           637127282, 637127287, 637127271, 637127285, 637127272,
           637127284, 637127292, 637127291, 637127290, 637127288,
           496463481, 637127278, 637127295, 637127279, 637127286],
    'R4': [759801038, 759801037, 759801036, 759801035],
}
print()
out = {}
for reg, ids in CAND.items():
    print(f'=== {reg} (тень в направлении {best_dir}) ===')
    out[reg] = []
    for bid in ids:
        s = shadow_towards(bid, d)
        out[reg].append(dict(id=bid, shadow_m=round(s, 1)))
        print(f'  id={bid}: тень {s:.1f}м')
json.dump(dict(dir=best_dir, sep=best_sep, shadows=out),
          open(BASE / 'work/altay_remarks/shadows_v2.json', 'w'), indent=1)
