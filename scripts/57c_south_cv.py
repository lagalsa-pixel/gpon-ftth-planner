#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57c: CV-детекция построек южного кармана (мозаика 3560-3960 x
7700-8080). Кропы с номерами + таблица координат -> VLM-классификация."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')
# регион: мозаика (3560,7700)-(3960,8080) -> кадр (2027,6224)-(2827,6984)
X0, Y0, X1, Y1 = 2027, 6224, 2827, 6984
crop = frame[Y0:Y1, X0:X1]
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_region.png', crop)

hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
s, v = hsv[:, :, 1], hsv[:, :, 2]
# крыши: низкая-средняя насыщенность, средняя яркость (как 55m)
mask = ((s < 70) & (v > 60) & (v < 210)).astype(np.uint8) * 255
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
n, lab_img, stats, cent = cv2.connectedComponentsWithStats(mask, 8)

# масштаб: кадр = мозаика*2 -> 1 px кадра = 0.1909 м (mpp/2)
MPP_F = 0.38183224357587775 / 2.0
comps = []
for i in range(1, n):
    x, y, w, h, a = stats[i]
    w_m, h_m = w * MPP_F, h * MPP_F
    # частные дома 5-16 м по большей стороне, отсечь мелочь и гигантов
    if max(w_m, h_m) < 5.0 or min(w_m, h_m) < 3.5:
        continue
    if max(w_m, h_m) > 18.0:
        continue
    # центр -> мозаика
    cx_f, cy_f = X0 + cent[i][0], Y0 + cent[i][1]
    cx_m = (cx_f + 5092.873104891791) / 2.0
    cy_m = (cy_f + 9176.0432) / 2.0
    comps.append((cx_m, cy_m, w_m, h_m, a, x, y, w, h))

comps.sort(key=lambda c: (round(c[1] / 40), c[0]))
print(f'найдено компонентов 5-18 м: {len(comps)}')
vis = crop.copy()
font = cv2.FONT_HERSHEY_SIMPLEX
for k, (cx_m, cy_m, w_m, h_m, a, x, y, w, h) in enumerate(comps, 1):
    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 3)
    cv2.putText(vis, str(k), (x - 6, y - 8), font, 1.3, (0, 255, 255), 3)
    print(f'  #{k}: {w_m:.1f}x{h_m:.1f} м  мозаика=({cx_m:.0f},{cy_m:.0f})'
          f'  crop=({x},{y},{w},{h})')
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_vis.png', vis)

# 2x-версия для VLM
vis2 = cv2.resize(vis, (vis.shape[1] * 2, vis.shape[0] * 2),
                  interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_vis_2x.jpg', vis2,
            [cv2.IMWRITE_JPEG_QUALITY, 92])
crop3 = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3),
                   interpolation=cv2.INTER_LANCZOS4)
cv2.imwrite(f'{BASE}/work/altay2/south57_clean_3x.jpg', crop3,
            [cv2.IMWRITE_JPEG_QUALITY, 92])
print('saved: south57_cv_vis.png / south57_cv_vis_2x.jpg / south57_clean_3x.jpg')

# опорные точки в кропе: дроп 131 (дуплекс), hh304, известные дропы
for name, mx, my in [('duplex-131', 3746.5, 7826.0), ('hh304', 3863.0, 7996.5)]:
    fx = (mx * 2 - 5092.873104891791) - X0
    fy = (my * 2 - 9176.0432) - Y0
    cv2.circle(vis2, (int(fx * 2), int(fy * 2)), 22, (0, 0, 255), 5)
    cv2.putText(vis2, name, (int(fx * 2) + 26, int(fy * 2) - 14),
                font, 1.2, (0, 0, 255), 3)
cv2.imwrite(f'{BASE}/work/altay2/south57_cv_markers_2x.jpg', vis2,
            [cv2.IMWRITE_JPEG_QUALITY, 92])
print('saved: south57_cv_markers_2x.jpg (с маркерами duplex-131 и hh304)')
