#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55m: CV-сегментация крыши нового здания в регионе img_12.
Крыши бараков района — серо-коричневые, выделяются на фоне травы/земли.
Сравниваем с VLM-боксом (2267..2447, 6421..6511) в координатах кадра."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')
X0, Y0, X1, Y1 = 2200, 6340, 2520, 6600  # регион с запасом
crop = frame[Y0:Y1, X0:X1]
cv2.imwrite(f'{BASE}/work/altay2/cv_region.png', crop)

hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)

# крыши: серые/коричневые = низкая-средняя насыщенность, средняя яркость
s, v = hsv[:, :, 1], hsv[:, :, 2]
mask = ((s < 70) & (v > 60) & (v < 210)).astype(np.uint8) * 255
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
n, lab_img, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
print('компонент:', n - 1)
comps = []
for i in range(1, n):
    x, y, w, h, a = stats[i]
    if a < 400:
        continue
    comps.append((a, x, y, w, h, cent[i]))
comps.sort(reverse=True)
for a, x, y, w, h, c in comps[:8]:
    print(f'  comp: area={a} bbox=({x},{y},{w},{h}) center=({c[0]:.0f},'
          f'{c[1]:.0f}) frame=({X0 + c[0]:.0f},{Y0 + c[1]:.0f})')

# визуализация
vis = crop.copy()
for a, x, y, w, h, c in comps[:5]:
    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 2)
    cv2.putText(vis, str(a), (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 255, 255), 1)
# VLM-бокс для сравнения (в координатах кропа)
vx0, vy0 = 2267 - X0, 6421 - Y0
vx1, vy1 = 2447 - X0, 6511 - Y0
cv2.rectangle(vis, (vx0, vy0), (vx1, vy1), (0, 0, 255), 2)
cv2.putText(vis, 'VLM', (vx0, vy0 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (0, 0, 255), 1)
cv2.imwrite(f'{BASE}/work/altay2/cv_vis.png', vis)
print('saved cv_vis.png')
