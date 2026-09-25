#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57f: точная CV-детекция построек в кармане (мозаика 3636-3856 x
7868-7963). Три маски: серые крыши, красные, тёмные. Нумерованные боксы
+ таблица координат в мозаике и метрах."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')

MX0, MY0, MX1, MY1 = 3636, 7868, 3856, 7963
fx0, fy0 = int(MX0 * 2 - 5092.87), int(MY0 * 2 - 9176.04)
fx1, fy1 = int(MX1 * 2 - 5092.87), int(MY1 * 2 - 9176.04)
crop = frame[fy0:fy1, fx0:fx1]
h, w = crop.shape[:2]
MPP_F = 0.38183224357587775 / 2.0  # 1 px кропа = 0.191 м

hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
s, v = hsv[:, :, 1], hsv[:, :, 2]
hue = hsv[:, :, 0]

# маска 1: серые крыши (как 55m/57c)
m_gray = ((s < 70) & (v > 60) & (v < 210)).astype(np.uint8)
# маска 2: красные/оранжевые крыши
m_red = (((hue < 12) | (hue > 168)) & (s > 60) & (v > 60)).astype(np.uint8)
# маска 3: синие крыши
m_blue = ((hue > 90) & (hue < 130) & (s > 50) & (v > 60)).astype(np.uint8)

mask = (m_gray | m_red | m_blue).astype(np.uint8) * 255
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
cv2.imwrite(f'{BASE}/work/altay2/south57_mask.png', mask * 255)

n, lab_img, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
comps = []
for i in range(1, n):
    x, y, cw, ch, a = stats[i]
    w_m, h_m = cw * MPP_F, ch * MPP_F
    if a < 250:  # отсечь мелочь (<2.5 м2)
        continue
    cx_f, cy_f = fx0 + cent[i][0], fy0 + cent[i][1]
    cx_m = (cx_f + 5092.873104891791) / 2.0
    cy_m = (cy_f + 9176.0432) / 2.0
    comps.append((cy_m, cx_m, w_m, h_m, a, x, y, cw, ch))

comps.sort()
print(f'построек найдено: {len(comps)}')
vis = crop.copy()
font = cv2.FONT_HERSHEY_SIMPLEX
for k, (cy_m, cx_m, w_m, h_m, a, x, y, cw, ch) in enumerate(comps, 1):
    cv2.rectangle(vis, (x, y), (x + cw, y + ch), (0, 255, 255), 2)
    cv2.putText(vis, str(k), (x - 4, y - 5), font, 0.9, (0, 255, 255), 2)
    print(f'  #{k}: {w_m:.1f}x{h_m:.1f} м ({a}px)  мозаика=({cx_m:.0f},'
          f'{cy_m:.0f})  crop=({x},{y},{cw},{ch})')
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_vis.png', vis)
big = cv2.resize(vis, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_vis_3x.jpg', big,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
print('saved: south57_cv_vis.png / south57_cv_vis_3x.jpg')

import json
json.dump([{'n': k + 1, 'mos_x': round(c[1], 1), 'mos_y': round(c[0], 1),
            'w_m': round(c[2], 1), 'h_m': round(c[3], 1), 'area_px': int(c[4]),
            'crop_xywh': [int(c[5]), int(c[6]), int(c[7]), int(c[8])]}
           for k, c in enumerate(comps)],
          open(f'{BASE}/work/altay2/south57_cv_comps.json', 'w'),
          ensure_ascii=False, indent=1)
print('saved: south57_cv_comps.json')
