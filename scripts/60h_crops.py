#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60h: кропы вокруг hh324 (квадрат зоны-P0, муфта M4 севернее,
дроп 17м) — карта 06 и спутниковая мозаика. Плюс кропы остальных
зона-P0 дропов для контроля."""
import json
import cv2

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
HH = 300

tr = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
M_fwd = tr['M_full']


def m2map(x, y):
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2] + HH)


def map2m(x, y):
    yy = y - HH
    return (M_fwd[0][0] * x + M_fwd[0][1] * yy + M_fwd[0][2],
            M_fwd[1][0] * x + M_fwd[1][1] * yy + M_fwd[1][2])


def crop_map(name, mx, my, rw=340, rh=280, zoom=1.55):
    img = cv2.imread(MAP)
    x0, y0 = int(mx - rw / 2), int(my - rh / 2)
    x1, y1 = int(mx + rw / 2), int(my + rh / 2)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.shape[1], x1), min(img.shape[0], y1)
    crop = img[y0:y1, x0:x1]
    # апскейл как на скриншоте заказчика
    big = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(f'{BASE}/work/altay3/t60_{name}_map.png', big)
    print(f'{name}: map crop {crop.shape[1]}x{crop.shape[0]} at({x0},{y0}) '
          f'-> zoom {zoom} -> {big.shape[1]}x{big.shape[0]}')


targets = {324: (3470, 8222)}
# все P0 для контроля
tt = json.load(open(f'{BASE}/work/altay3/t60_zone_truth.json'))
for r in tt['z1_rows']:
    targets[r['hh']] = tuple(r['sq'])

mosaic = cv2.imread(f'{BASE}/{tr["new_image"]}')
print('мозаика:', mosaic.shape)
for hh, (ex, ey) in sorted(targets.items()):
    mx, my = m2map(ex, ey)
    crop_map(f'hh{hh}', mx, my, rw=340, rh=280)
    # спутник: new_image (кадр заказчика 0.19 м/px), координаты через Mi
    sx = Mi[0][0] * ex + Mi[0][1] * ey + Mi[0][2]
    sy = Mi[1][0] * ex + Mi[1][1] * ey + Mi[1][2]
    rw2, rh2 = 170, 140        # 0.19 м/px => ~32x27 м контекст
    x0, y0 = int(sx - rw2), int(sy - rh2)
    x1, y1 = int(sx + rw2), int(sy + rh2)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(mosaic.shape[1], x1), min(mosaic.shape[0], y1)
    crop = mosaic[y0:y1, x0:x1]
    big = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(f'{BASE}/work/altay3/t60_hh{hh}_sat4x.png', big)
    print(f'hh{hh}: sat crop {crop.shape[1]}x{crop.shape[0]} at({x0},{y0}) '
          f'-> 4x -> {big.shape[1]}x{big.shape[0]}')
