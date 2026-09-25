#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60k: разбор найденного маск-матчем региона карты (1597,6198,
Z=1.625, 282x208): какие элементы символики там есть и как они
расположены. Сравнение с ожидаемыми позициями из скриншота."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
X0, Y0, TW, TH = 1597, 6198, 282, 208

img = cv2.imread(MAP)
crop = img[Y0:Y0 + TH, X0:X0 + TW]
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
sat = s > 90

masks = {
    'yellow': sat & (v > 90) & (h >= 18) & (h <= 36),
    'blue': (s > 120) & (v > 80) & (h >= 95) & (h <= 120),
    'cyan': (s > 110) & (v > 90) & (h >= 75) & (h <= 95),
}
print(f'регион карты ({X0},{Y0}) {TW}x{TH}:')
for name, m in masks.items():
    mm = (m * 255).astype(np.uint8)
    n, lab, st, cent = cv2.connectedComponentsWithStats(mm, 8)
    print(f'== {name}: {int(m.sum())} px, {n-1} компонент ==')
    for i in sorted(range(1, n), key=lambda i: -st[i][4])[:12]:
        x, y, w2, h2, a = st[i]
        if a < 15:
            continue
        bgr = crop[lab == i].mean(axis=0).astype(int)
        print(f'   ({X0+x},{Y0+y}) {w2}x{h2} a={a} rgb=({bgr[2]},{bgr[1]},{bgr[0]})')
cv2.imwrite(f'{BASE}/work/altay3/t60_region_zoom.png',
            cv2.resize(crop, None, fx=1.625, fy=1.625,
                       interpolation=cv2.INTER_LANCZOS4))
print('saved t60_region_zoom.png')
