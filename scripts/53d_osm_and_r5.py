#!/usr/bin/env python3
"""Task 53: OSM-здания в регионах замечаний + SIFT-поиск fig-004-004 (R5)
на пользовательском кадре upload/06_Алтайский_граница.jpg.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M = tr['M_full']
HH = 300


def map_to_mosaic(x, y):
    fx, fy = x, y - HH
    return (M[0][0] * fx + M[0][1] * fy + M[0][2],
            M[1][0] * fx + M[1][1] * fy + M[1][2])


REGIONS = {
    'R1': (983, 2867, 2137, 3115),
    'R2': (1048, 4048, 2249, 4869),
    'R3': (932, 5310, 2820, 7364),
    'R4': (1843, 2439, 2088, 2721),
    'R6': (273, 1806, 676, 2530),
}

# --- OSM здания (geo -> mosaic px) ---
osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp = geo['mpp']
WEST, NORTH = geo['west'], geo['north']


def geo_to_px(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


bld = []
for b in osm.get('buildings', []):
    cx, cy = b['center']
    px, py = geo_to_px(cx, cy)
    nb = dict(b)
    nb['px'] = [px, py]
    bld.append(nb)
print('зданий OSM:', len(bld))
if bld:
    ex = bld[0]
    print('пример: id=%s px=(%.0f,%.0f) tags=%s' % (
        ex['id'], ex['px'][0], ex['px'][1],
        json.dumps(ex.get('tags', {}), ensure_ascii=False)))


def bld_center(b):
    return b['px']


for name, (x0, y0, x1, y1) in REGIONS.items():
    mx0, my0 = map_to_mosaic(x0, y0)
    mx1, my1 = map_to_mosaic(x1, y1)
    found = []
    for b in bld:
        c = bld_center(b)
        if c and mx0 - 30 <= c[0] <= mx1 + 30 and my0 - 30 <= c[1] <= my1 + 30:
            found.append(b)
    print(f'--- {name}: OSM зданий {len(found)}')
    for b in sorted(found, key=lambda b: b['px'][1]):
        c = b['px']
        area = b.get('area', 0)
        print(f"   id={b['id']} px=({c[0]:.0f},{c[1]:.0f}) area={area:.0f}м2 "
              f"tags={json.dumps(b.get('tags', {}), ensure_ascii=False)}")

# --- R5: SIFT fig-004-004 на кадре пользователя ---
print()
print('=== R5: матчинг fig-004-004 на кадре ===')
import math  # noqa
frame_full = cv2.imread(str(BASE / 'upload/06_Алтайский_граница.jpg'),
                        cv2.IMREAD_GRAYSCALE)
DOWN = 2
frame = cv2.resize(frame_full, (frame_full.shape[1] // DOWN,
                                 frame_full.shape[0] // DOWN),
                    interpolation=cv2.INTER_AREA)
print('frame full:', frame_full.shape[::-1], '-> match:', frame.shape[::-1])
fig0 = cv2.imread(str(BASE / 'work/altay_remarks/fig-004-004.png'),
                  cv2.IMREAD_GRAYSCALE)
print('fig:', fig0.shape[::-1])

sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.04)
k2, d2 = sift.detectAndCompute(frame, None)
print('kp frame:', len(k2))
best = None
for s in [1.0, 0.5, 0.25, 2.0]:
    h0, w0 = fig0.shape
    fig = fig0 if s == 1.0 else cv2.resize(
        fig0, (int(w0 * s), int(h0 * s)),
        interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    if min(fig.shape) < 40:
        continue
    k1, d1 = sift.detectAndCompute(fig, None)
    if d1 is None or len(k1) < 12:
        continue
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        print(f'  scale={s}: good={len(good)} (мало)')
        continue
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    inl = int(msk.sum()) if H is not None else 0
    print(f'  scale={s}: good={len(good)} inl={inl}')
    if inl >= 8 and (best is None or inl > best[0]):
        best = (inl, s, H, fig.shape[::-1])

if best:
    inl, s, H, (w, h) = best
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) * DOWN
    print(f'R5 MATCHED scale={s} inl={inl} frame corners: '
          f'{[(round(x), round(y)) for x, y in proj]}')
    # пересчёт в map px (шапка) и mosaic
    out = {'inliers': inl, 'fig_scale': s,
           'frame_corners': np.round(proj, 1).tolist(),
           'map_corners': [[round(x), round(y + HH)] for x, y in proj],
           'mosaic_corners': [[round(M[0][0] * x + M[0][1] * y + M[0][2]),
                               round(M[1][0] * x + M[1][1] * y + M[1][2])]
                              for x, y in proj]}
    print('map px:', out['map_corners'])
    print('mosaic px:', out['mosaic_corners'])
    json.dump(out, open(BASE / 'work/altay_remarks/fig_R5_match.json', 'w'),
              ensure_ascii=False, indent=1)
else:
    print('R5: НЕ найдено на кадре')
