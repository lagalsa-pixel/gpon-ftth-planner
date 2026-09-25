#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57e-v2: сетка на базовом кропе кармана с ПОЛНОЙ разметкой.
Ячейка = 20 px кропа = 10 px мозаики = 3.82 м. Столбцы A-V (22), строки 0-9."""
import cv2

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')

MX0, MY0, MX1, MY1 = 3636, 7868, 3856, 7963
fx0, fy0 = MX0 * 2 - 5092.87, MY0 * 2 - 9176.04
fx1, fy1 = MX1 * 2 - 5092.87, MY1 * 2 - 9176.04
crop = frame[int(fy0):int(fy1), int(fx0):int(fx1)]
print('crop 1x:', crop.shape, '= мозаика', (MX1 - MX0), 'x', (MY1 - MY0),
      'px =', (MX1 - MX0) * 0.3818, 'x', (MY1 - MY0) * 0.3818, 'м')

UP = 4
big = cv2.resize(crop, (crop.shape[1] * UP, crop.shape[0] * UP),
                 interpolation=cv2.INTER_LANCZOS4)
vis = big.copy()
STEP = 20 * UP  # 80 px на 4x
cols = 'ABCDEFGHIJKLMNOPQRSTUV'
h, w = vis.shape[:2]
for i, gx in enumerate(range(0, w + 1, STEP)):
    x = min(gx, w)
    cv2.line(vis, (x, 0), (x, h), (180, 255, 255), 1)
    cv2.putText(vis, cols[i] if i < len(cols) else '?', (x + 3, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
for j, gy in enumerate(range(0, h + 1, STEP)):
    y = min(gy, h)
    cv2.line(vis, (0, y), (w, y), (180, 255, 255), 1)
    cv2.putText(vis, str(j), (3, y + 22), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 255, 255), 2)
cv2.imwrite(f'{BASE}/work/altay2/south57_pocket_grid2.jpg', vis,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
print(f'saved south57_pocket_grid2.jpg {vis.shape}')
print('ячейка 3.82 м; col A = мозаика x=%d; row 0 = y=%d; шаг 10 px мозаики'
      % (MX0, MY0))
print('col_i -> мозаика x = %d + i*10; row_j -> y = %d + j*10' % (MX0, MY0))
