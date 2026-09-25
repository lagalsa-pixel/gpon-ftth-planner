#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55o: выделение АННОТАЦИИ заказчика из синей маски img_12.
Синее заказчика = синее img_12 МИНУС синие элементы карты (варп карты
обратно в img_12 через инверсную гомографию)."""
import json
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay2'
MAP = DIR / 'map06_v4.jpg'

tr = json.load(open(BASE / 'work/altaiskiy/crop_transform.json'))
M_full = tr['M_full']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))['altaiskiy']
mpp = geo['mpp']

# ---------- матч (как в 55n) ----------
map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
Hf, Wf = map_full.shape
map_half = cv2.resize(map_full, (Wf // 2, Hf // 2),
                      interpolation=cv2.INTER_AREA)
sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02)
k2, d2 = sift.detectAndCompute(map_half, None)
flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))

fig = cv2.imread(str(DIR / 'img_12.png'), cv2.IMREAD_GRAYSCALE)
results = {}
for s in [2.0, 4.0]:
    f2 = cv2.resize(fig, (int(fig.shape[1] * s), int(fig.shape[0] * s)),
                    interpolation=cv2.INTER_CUBIC)
    k1, d1 = sift.detectAndCompute(f2, None)
    ms = flann.knnMatch(d1, d2, k=2)
    good = [m for m, n in ms if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        continue
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is not None:
        results[s] = (int(msk.sum()), H)
best_s = max(results, key=lambda k: results[k][0])
best_inl, H = results[best_s]
print(f'матч s={best_s} inliers={best_inl}')

img = cv2.imread(str(DIR / 'img_12.png'))
Himg, Wimg = img.shape[:2]


def blue_mask(bgr, min_sat=80):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    return (((h >= 95) & (h <= 140) & (s > min_sat) & (v > 40))
            ).astype(np.uint8) * 255


blue_cust = blue_mask(img)

# карта -> пространство img_12 (s=best_s)
# H: fig(s) -> map_half. Полный: map_full -> fig(s): S2^-1 @ H^-1
S2 = np.diag([2.0, 2.0, 1.0])
Hfull = S2 @ H                       # fig(s) -> map_full
Hinv = np.linalg.inv(Hfull)          # map_full -> fig(s)
warped_map = cv2.warpPerspective(
    cv2.imread(str(MAP)), Hinv,
    (int(Wimg * best_s), int(Himg * best_s)),
    flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
    borderValue=0)
blue_map = blue_mask(warped_map)
# к масштабу 1x
blue_map_1 = cv2.resize(blue_map, (Wimg, Himg),
                        interpolation=cv2.INTER_NEAREST)
blue_map_d = cv2.dilate(blue_map_1,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))

annot = cv2.bitwise_and(blue_cust, cv2.bitwise_not(blue_map_d))
annot = cv2.morphologyEx(annot, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
print(f'синего у заказчика: {(blue_cust > 0).sum()}, '
      f'синего на карте (в кадре img): {(blue_map_1 > 0).sum()}, '
      f'аннотация: {(annot > 0).sum()}')

# визуализация: img + аннотация красным
vis = img.copy()
vis[annot > 0] = (0, 0, 255)
cv2.imwrite(str(DIR / 'annot_vis.png'), vis)

# ---------- аннотация -> карта ----------
annot_s = cv2.resize(annot, (int(Wimg * best_s), int(Himg * best_s)),
                     interpolation=cv2.INTER_NEAREST)
warped = cv2.warpPerspective(annot_s, Hfull, (Wf, Hf),
                             flags=cv2.INTER_NEAREST,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=0)
nn, ll, stats, cent = cv2.connectedComponentsWithStats(warped, 8)
order = np.argsort(-stats[1:, 4]) + 1
print('компоненты аннотации на карте:')
polys = []
for i in order[:6]:
    x, y, w, h, a = stats[i]
    if a < 40:
        continue
    comp = (ll == i).astype(np.uint8)
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                             cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea)
    rect = cv2.minAreaRect(c)
    (rcx, rcy), (rw, rh), rang = rect
    fcx, fcy = rcx, rcy - 300
    mcx = M_full[0][0] * fcx + M_full[0][1] * fcy + M_full[0][2]
    mcy = M_full[1][0] * fcx + M_full[1][1] * fcy + M_full[1][2]
    w_m = rw * mpp / 2
    h_m = rh * mpp / 2
    print(f'  a={a}: центр map=({rcx:.0f},{rcy:.0f}) '
          f'mosaic=({mcx:.0f},{mcy:.0f}), {max(w_m, h_m):.1f}x'
          f'{min(w_m, h_m):.1f} м, угол {rang:.1f}')
    polys.append(dict(area=int(a), center_map=[round(float(rcx)),
                                               round(float(rcy))],
                      center_mosaic=[round(float(mcx)), round(float(mcy))],
                      size_m=[round(max(w_m, h_m), 1), round(min(w_m, h_m), 1)],
                      angle=round(float(rang), 1)))

json.dump(dict(match=dict(scale=best_s, inliers=best_inl),
               annotation_px=int((annot > 0).sum()),
               polys=polys),
          open(DIR / 'annot_polys.json', 'w'), ensure_ascii=False, indent=1)
print('saved annot_polys.json')

# наложить на карту для контроля
vismap = cv2.imread(str(MAP))
for p in polys:
    cx, cy = p['center_map']
    w, h = p['size_m']
    ang = p['angle']
    # размер в map px
    wpx = w / (mpp / 2)
    hpx = h / (mpp / 2)
    box = cv2.boxPoints(((cx, cy), (wpx, hpx), ang)).astype(int)
    cv2.drawContours(vismap, [box], 0, (0, 0, 255), 8)
cv2.imwrite(str(DIR / 'annot_on_map.jpg'), vismap,
            [cv2.IMWRITE_JPEG_QUALITY, 85])
print('saved annot_on_map.jpg')
