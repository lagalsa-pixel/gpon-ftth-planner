#!/usr/bin/env python3
"""Task 53: классификация этажности зданий по длине теней.

Кадр пользователя = 2x-зум мозаики (0.19 м/px). Тень пропорциональна высоте.
Калибровка: R6-дома с OSM building:levels 1 и 2.
Метод: для каждого здания идём перпендикулярно длинной стороне в обе стороны,
ищем тёмную полосу (тень) от стены; длина полосы -> метры -> этажность.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']                      # mosaic -> frame
FRAME_MPP = 0.38183224357587775 / 2   # 0.1909 м/px

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
    BLD[b['id']] = dict(pts=pts, tags=b.get('tags', {}),
                        area_osm=b.get('area'))


def shadow_len(bid, sun_dir=None):
    """Длина тени здания: тёмная полоса от стены наружу.
    Возвращает (best_dir, len_px) — максимум по 4 направлениям."""
    b = BLD[bid]
    pts = np.array(b['pts'])
    xs, ys = pts[:, 0], pts[:, 1]
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    horiz = w >= h
    # длинная сторона: сэмплы вдоль неё
    results = []
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if sun_dir:
        dirs = [sun_dir]
    for d in dirs:
        lens = []
        n_s = 24
        for i in range(n_s):
            t = (i + 0.5) / n_s
            if horiz:
                px_ = x0 + w * t
                py_ = y0 if d[1] < 0 else y1
                if d[0] != 0:
                    py_ = cy
                    px_ = x1 if d[0] > 0 else x0
            else:
                py_ = y0 + h * t
                px_ = x0 if d[0] < 0 else x1
                if d[1] != 0:
                    px_ = cx
                    py_ = y1 if d[1] > 0 else y0
            # марш наружу от стены
            run = 0.0
            dark_run = 0.0
            max_dark = 0.0
            xx, yy = px_, py_
            step = 1.0
            for k in range(1, 120):
                xx += d[0] * step
                yy += d[1] * step
                xi, yi = int(round(xx)), int(round(yy))
                if not (0 <= xi < FW and 0 <= yi < FH):
                    break
                v = img[yi, xi]
                # локальный порог: медиана окрестности здания
                if v < 95:
                    dark_run += step
                    max_dark = max(max_dark, dark_run)
                else:
                    dark_run = 0.0
            lens.append(max_dark)
        lens.sort()
        results.append((d, lens[len(lens) // 2]))  # медиана
    results.sort(key=lambda r: -r[1])
    return results[0]      # (dir, len_px) с максимальной тенью


# ---------- калибровка на R6 ----------
CAL = [496463491, 496463492, 496463493, 496463496, 496463495, 496463494,
       496463500, 496463499, 496463498, 496463497]
print('=== Калибровка R6 (OSM levels известны) ===')
cal_data = []
for bid in CAL:
    b = BLD[bid]
    lv = b['tags'].get('building:levels', '?')
    d, L = shadow_len(bid)
    m = L * FRAME_MPP
    print(f'  id={bid} lv={lv} тень={L:.0f}px = {m:.1f}м dir={d}')
    cal_data.append((float(lv), m))

lv1 = [m for lv, m in cal_data if lv == 1]
lv2 = [m for lv, m in cal_data if lv == 2]
lv1m = sorted(lv1)[len(lv1) // 2] if lv1 else 0
lv2m = sorted(lv2)[len(lv2) // 2] if lv2 else 0
per_floor = (lv2m - lv1m) if (lv1m and lv2m and lv2m > lv1m) else None
base_h = lv1m
print(f'медиана тени lv=1: {lv1m:.1f}м, lv=2: {lv2m:.1f}м, '
      f'прирост/этаж: {per_floor}')

# ---------- кандидаты ----------
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
for reg, ids in CAND.items():
    print(f'=== {reg} ===')
    for bid in ids:
        b = BLD[bid]
        pts = np.array(b['pts'])
        xs, ys = pts[:, 0], pts[:, 1]
        w = (xs.max() - xs.min()) * FRAME_MPP
        h = (ys.max() - ys.min()) * FRAME_MPP
        d, L = shadow_len(bid)
        m = L * FRAME_MPP
        est = ''
        if per_floor:
            floors = 1 + (m - base_h) / per_floor
            est = f'-> этажей ~{floors:.1f}'
        print(f'  id={bid} bbox={w:.1f}x{h:.1f}м тень={m:.1f}м dir={d} {est}')
