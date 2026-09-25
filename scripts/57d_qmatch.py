#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57d: привязка вопросного кропа south_check_3x.jpg к карте 06
(шаблон-матчинг) -> координаты 4 домов южного кармана на мозаике."""
import cv2
import numpy as np

BASE = '/home/z/my-project'

q = cv2.imread(f'{BASE}/work/altay2/south_check_3x.jpg')
print('question crop:', q.shape)
mp = cv2.imread(f'{BASE}/download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg')
print('map06:', mp.shape)

# вопросный кроп 3x от карты v5 -> даунскейл кропа до масштаба карты (÷3)
q_gray = cv2.cvtColor(q, cv2.COLOR_BGR2GRAY)
m_gray = cv2.cvtColor(mp, cv2.COLOR_BGR2GRAY)
qh = cv2.resize(q_gray, (q_gray.shape[1] // 3, q_gray.shape[0] // 3),
                interpolation=cv2.INTER_AREA)
print('qh (масштаб карты):', qh.shape)

res = cv2.matchTemplate(m_gray, qh, cv2.TM_CCOEFF_NORMED)
_, score, _, loc = cv2.minMaxLoc(res)
print(f'template NCC: {score:.4f} at map {loc}')

# область карты (полн. разрешение) = loc, размер = q/3
x0, y0 = loc[0], loc[1]
x1, y1 = x0 + qh.shape[1], y0 + qh.shape[0]
print(f'регион на карте: ({x0},{y0})-({x1},{y1}), размер {x1-x0}x{y1-y0}')

# сверка: вырезать из карты этот регион и сравнить с кропом
sub = m_gray[y0:y1, x0:x1]
sub = cv2.resize(sub, (qh.shape[1], qh.shape[0]))
ncc = cv2.matchTemplate(sub, qh, cv2.TM_CCOEFF_NORMED)[0, 0]
print(f'проверка NCC регион-кроп: {ncc:.4f}')

# карта = кадр + шапка 300; кадр -> мозаика: m = (f + offset)/2
HDR = 300
# СЕТКА на кропе: 40 px кропа = 40/3 px карты = 40/3/2 px мозаики = 6.36 м
vis = q.copy()
h, w = vis.shape[:2]
for gx in range(0, w, 120):
    cv2.line(vis, (gx, 0), (gx, h), (0, 255, 255), 1)
for gy in range(0, h, 120):
    cv2.line(vis, (0, gy), (w, gy), (0, 255, 255), 1)
cv2.imwrite(f'{BASE}/work/altay2/south57_question_grid.jpg', vis,
            [cv2.IMWRITE_JPEG_QUALITY, 93])

# сохранить координатную привязку: (0,0) кропа 3x = карта (x0,y0)
import json
json.dump({'map_x0': x0, 'map_y0': y0, 'scale': 3, 'ncc': float(ncc),
           'crop_w': q.shape[1], 'crop_h': q.shape[0]},
          open(f'{BASE}/work/altay2/south57_qmatch.json', 'w'), indent=1)
print('saved south57_qmatch.json')


def qpx_to_mosaic(qx, qy):
    """пиксель вопросного кропа (3x) -> мозаика."""
    mx_map = x0 + qx / 3.0          # карта (с шапкой)
    my_map = y0 + qy / 3.0
    fx, fy = mx_map, my_map - HDR   # кадр
    return (fx + 5092.873104891791) / 2.0, (fy + 9176.0432) / 2.0


# контрольные точки: дроп дуплекса 131 (3746.5,7826) -> куда попадает в кроп?
def mosaic_to_qpx(mx, my):
    fx, fy = mx * 2 - 5092.873104891791, my * 2 - 9176.0432
    mx_map, my_map = fx, fy + HDR
    return (mx_map - x0) * 3.0, (my_map - y0) * 3.0


ok_in = 0
for name, mx, my in [('duplex-131', 3746.5, 7826.0),
                      ('hh304', 3863.0, 7996.5)]:
    qx, qy = mosaic_to_qpx(mx, my)
    print(f'{name}: мозаика ({mx},{my}) -> кроп ({qx:.0f},{qy:.0f})')
    if 0 <= qx < w and 0 <= qy < h:
        ok_in += 1
        cv2.circle(vis, (int(qx), int(qy)), 20, (0, 0, 255), 4)
        cv2.putText(vis, name, (int(qx) + 24, int(qy) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
print(f'маркеров в кадре: {ok_in} из 2')
cv2.imwrite(f'{BASE}/work/altay2/south57_question_markers.jpg', vis,
            [cv2.IMWRITE_JPEG_QUALITY, 93])
print('saved: south57_question_grid.jpg / south57_question_markers.jpg')
