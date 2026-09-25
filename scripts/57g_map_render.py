#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57g: рендер кармана с ТЕКУЩЕЙ карты v6 (мозаика 3560-3960 x
7790-8090, с запасом вокруг вопросного кропа) — видно, у каких зданий
есть дропы. Плюс кроп вопросного региона без изменений."""
import cv2

BASE = '/home/z/my-project'
mp = cv2.imread(f'{BASE}/download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg')
HDR = 300

# мозаика -> карта: mx = f, my = f + 300, f = m*2 - (5092.87, 9176.04)
MX0, MY0, MX1, MY1 = 3560, 7790, 3960, 8090
x0, y0 = int(MX0 * 2 - 5092.87), int(MY0 * 2 - 9176.04) + HDR
x1, y1 = int(MX1 * 2 - 5092.87), int(MY1 * 2 - 9176.04) + HDR
print(f'карта регион: ({x0},{y0})-({x1},{y1})')
crop = mp[y0:y1, x0:x1]
cv2.imwrite(f'{BASE}/work/altay2/south57_map_now.jpg', crop,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
big = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2),
                 interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f'{BASE}/work/altay2/south57_map_now_2x.jpg', big,
            [cv2.IMWRITE_JPEG_QUALITY, 90])
print('saved: south57_map_now.jpg', crop.shape, '+ 2x')

# вопросный регион из карты (то, что видел заказчик в Task 55)
qx0, qy0 = 2180, 6860
qx1, qy1 = 2620, 7050
q = mp[qy0:qy1, qx0:qx1]
q3 = cv2.resize(q, (q.shape[1] * 3, q.shape[0] * 3),
                interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f'{BASE}/work/altay2/south57_map_question_3x.jpg', q3,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
print('saved: south57_map_question_3x.jpg', q3.shape)
