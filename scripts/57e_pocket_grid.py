#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57e: базовый кроп регионa вопросного кропа (мозаика 3636-3856 x
7868-7963) с мелкой сеткой (ячейка 4x) для точного позиционирования домов."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')

# мозаика -> кадр: f = m*2 - (5092.87, 9176.04)
MX0, MY0, MX1, MY1 = 3636, 7868, 3856, 7963
fx0, fy0 = MX0 * 2 - 5092.87, MY0 * 2 - 9176.04
fx1, fy1 = MX1 * 2 - 5092.87, MY1 * 2 - 9176.04
print(f'кадр: ({fx0:.0f},{fy0:.0f})-({fx1:.0f},{fy1:.0f})')

crop = frame[int(fy0):int(fy1), int(fx0):int(fx1)]
print('crop 1x:', crop.shape)

UP = 4
big = cv2.resize(crop, (crop.shape[1] * UP, crop.shape[0] * UP),
                 interpolation=cv2.INTER_LANCZOS4)
vis = big.copy()
# сетка: каждые 10 px кропа (3.8 м) -> 40 px на 4x
STEP = 10 * UP
cols = 'ABCDEFGHIJKLMNOP'
h, w = vis.shape[:2]
for i, gx in enumerate(range(0, w + 1, STEP)):
    x = min(gx, w)
    cv2.line(vis, (x, 0), (x, h), (255, 255, 0), 1)
    if i < len(cols):
        cv2.putText(vis, cols[i], (x + 2, 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 255), 2)
for j, gy in enumerate(range(0, h + 1, STEP)):
    y = min(gy, h)
    cv2.line(vis, (0, y), (w, y), (255, 255, 0), 1)
    cv2.putText(vis, str(j), (2, y + 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 255, 255), 2)
cv2.imwrite(f'{BASE}/work/altay2/south57_pocket_grid.jpg', vis,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
print(f'saved south57_pocket_grid.jpg {vis.shape}; ячейка = 10 px кропа = '
      f'{10 * 0.3818:.1f} м')
print(f'col A = мозаика x={MX0}; row 0 = мозаика y={MY0}; шаг 10 px')
