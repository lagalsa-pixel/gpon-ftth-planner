#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55n: контур нового здания из СИНЕЙ ОБВОДКИ заказчика на img_12.
1) SIFT-матч img_12 -> карта v4 (гомография H)
2) синяя маска в img_12 -> варп в координаты карты -> полигон
3) полигон -> упрощение до прямоугольника -> кадр/мозаика/geo
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay2'
MAP = DIR / 'map06_v4.jpg'

tr = json.load(open(BASE / 'work/altaiskiy/crop_transform.json'))
M_full = tr['M_full']
M_inv = tr['M_inv']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))['altaiskiy']
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']

# ---------- 1) матч img_12 -> map ----------
map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
Hf, Wf = map_full.shape
map_half = cv2.resize(map_full, (Wf // 2, Hf // 2),
                      interpolation=cv2.INTER_AREA)
sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02)
k2, d2 = sift.detectAndCompute(map_half, None)
flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))

fig = cv2.imread(str(DIR / 'img_12.png'), cv2.IMREAD_GRAYSCALE)
bestH, best_inl, best_reg = None, 0, None
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
    if H is None:
        continue
    inl = int(msk.sum())
    if inl > best_inl:
        hh, ww = f2.shape
        corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                              [0, hh]]).reshape(-1, 1, 2)
        proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) * 2
        bestH, best_inl = H, inl
        best_reg = [proj[:, 0].min(), proj[:, 1].min(),
                    proj[:, 0].max(), proj[:, 1].max()]
print(f'матч: inliers={best_inl}, регион карты={best_reg}')

# ---------- 2) синяя маска ----------
img = cv2.imread(str(DIR / 'img_12.png'))  # BGR
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
h, s, v = cv2.split(hsv)
print('уникальные hue (гистограмма):')
hist = np.bincount(h.ravel(), minlength=180)
for hh in range(180):
    if hist[hh] > 200:
        print(f'  hue={hh}: {hist[hh]} px, mean S='
              f'{s[h == hh].mean():.0f} V={v[h == hh].mean():.0f}')

# синяя обводка: hue 100..135, насыщенная
blue = (((h >= 95) & (h <= 140) & (s > 90))).astype(np.uint8) * 255
n_blue = int((blue > 0).sum())
print(f'синих пикселей: {n_blue} из {img.shape[0] * img.shape[1]}')
if n_blue < 50:
    print('МАЛО синего — обводка другого цвета!')
else:
    # связная компонента максимальная
    nn, ll, stats, cent = cv2.connectedComponentsWithStats(blue, 8)
    order = np.argsort(-stats[1:, 4]) + 1
    for i in order[:5]:
        x, y, w, hh_, a = stats[i]
        print(f'  comp {i}: area={a} bbox=({x},{y},{w},{hh_})')

# ---------- 3) варп маски в карту ----------
if n_blue >= 50:
    # маска в масштабе s (тот же, что матч: используем s из best-матча —
    # пересчёт: гомография для s=best; варпим маску в том же масштабе)
    s_used = best_s = 2.0 if bestH is not None else None
    # найдём фактический масштаб матча через форму f2: возьмём из ранее
    # (для простоты повторим оба масштаба и выберем больший inl уже сделано:
    #  нужно знать, какой s дал best. Повторим честно:)
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
        if H is None:
            continue
        if int(msk.sum()) == best_inl:
            best_s = s
            bestH = H
    print('масштаб матча:', best_s)
    blue_s = cv2.resize(blue, (int(blue.shape[1] * best_s / 1.0),
                               int(blue.shape[0] * best_s / 1.0)),
                        interpolation=cv2.INTER_NEAREST)
    # маска -> карта (half) -> карта (full): H работает в half, умножаем на 2
    S2 = np.diag([2.0, 2.0, 1.0])
    Hfull = S2 @ bestH
    # варп в полноэкранный холст карты
    warped = cv2.warpPerspective(blue_s, Hfull, (Wf, Hf),
                                 flags=cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=0)
    nn, ll, stats, cent = cv2.connectedComponentsWithStats(warped, 8)
    order = np.argsort(-stats[1:, 4]) + 1
    polys = []
    for i in order[:3]:
        x, y, w, hh_, a = stats[i]
        if a < 30:
            continue
        comp = (ll == i).astype(np.uint8)
        cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                 cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)
        # минимальный прямоугольник (в map px)
        rect = cv2.minAreaRect(c)
        polys.append(rect)
        (rcx, rcy), (rw, rh), rang = rect
        # map -> frame -> mosaic
        fcx, fcy = rcx, rcy - 300
        mcx = M_full[0][0] * fcx + M_full[0][1] * fcy + M_full[0][2]
        mcy = M_full[1][0] * fcx + M_full[1][1] * fcy + M_full[1][2]
        w_m = rw * mpp / 2  # map px -> м (map = 2x мозаики по mpp/2)
        h_m = rh * mpp / 2
        print(f'  полигон: центр map=({rcx:.0f},{rcy:.0f}) '
              f'frame=({fcx:.0f},{fcy:.0f}) mosaic=({mcx:.0f},{mcy:.0f}); '
              f'{max(w_m, h_m):.1f}x{min(w_m, h_m):.1f} м, угол {rang:.1f}')
        out = dict(center_map=[round(float(rcx)), round(float(rcy))],
                   center_frame=[round(float(fcx)), round(float(fcy))],
                   center_mosaic=[round(float(mcx)), round(float(mcy))],
                   size_m=[round(max(w_m, h_m), 1), round(min(w_m, h_m), 1)],
                   angle_deg=round(float(rang), 1),
                   area_px=int(a))
        json.dump(out, open(DIR / 'new_bld_footprint.json', 'w'),
                  ensure_ascii=False, indent=1)
        # визуализация на карте
        box = cv2.boxPoints(rect).astype(int)
        vis = cv2.imread(str(MAP))
        cv2.drawContours(vis, [box], 0, (0, 255, 255), 6)
        cv2.imwrite(str(DIR / 'new_bld_on_map.jpg'), vis,
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
        break
    print('saved new_bld_footprint.json + new_bld_on_map.jpg')
