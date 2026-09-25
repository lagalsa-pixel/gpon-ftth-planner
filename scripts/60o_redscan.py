#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60o: CV-скан всей базы Алтайского (0.19 м/px) на вытянутые
здания с РЫЖИМИ секциями крыши (признак со скриншота: рыжие торцы +
светлая середина). Рыжие крыши редки -> короткий список на VLM-проверку.
Выход: кропы-кандидаты t60_red_<n>.png"""
import cv2
import numpy as np

BASE = '/home/z/my-project'
IMG = f'{BASE}/upload/06_Алтайский_граница.jpg'

img = cv2.imread(IMG)
H, W = img.shape[:2]
print(f'база {W}x{H}, {W*0.19:.0f}x{H*0.19:.0f} м')
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
# ржаво-рыжая крыша: H 3..25 (opencv 0-180), насыщенная, средняя яркость
red = ((h >= 2) & (h <= 28) & (s > 90) & (v > 80) &
       (v < 230)).astype(np.uint8)
# морфология: убрать мелкий шум
red = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
n, lab, st, cent = cv2.connectedComponentsWithStats(red, 8)
print(f'рыжих блобов: {n-1}')
# блики: вытянутые блобы (крышные секции) площадью 100-4000 px
# (секция ~5x15..10x40 м = 26x79..52x210 px при 0.19 м/px)
cands = []
for i in range(1, n):
    x, y, w2, h2, a = st[i]
    if a < 120 or a > 6000:
        continue
    ar = max(w2, h2) / max(1, min(w2, h2))
    if ar < 1.3:
        continue
    fill = a / (w2 * h2)
    if fill < 0.35:
        continue
    cands.append((i, x, y, w2, h2, a, ar, fill))

print(f'блобов-кандидатов секций: {len(cands)}')
# группировка: секции одного здания рядом -> кластеры блобов
boxes = [(x, y, x + w2, y + h2) for _, x, y, w2, h2, *_ in cands]
used = [False] * len(boxes)
groups = []
for i in range(len(boxes)):
    if used[i]:
        continue
    grp = [i]
    used[i] = True
    changed = True
    while changed:
        changed = False
        for j in range(len(boxes)):
            if used[j]:
                continue
            ax0, ay0, ax1, ay1 = boxes[j]
            for k in grp:
                bx0, by0, bx1, by1 = boxes[k]
                # близость (расстояние между боксами < 60 px)
                dx = max(bx0 - ax1, ax0 - bx1, 0)
                dy = max(by0 - ay1, ay0 - by1, 0)
                if math.hypot(dx, dy) if False else (dx < 60 and dy < 60):
                    grp.append(j)
                    used[j] = True
                    changed = True
                    break
        # пересчёт
    xs0 = min(boxes[k][0] for k in grp)
    ys0 = min(boxes[k][1] for k in grp)
    xs1 = max(boxes[k][2] for k in grp)
    ys1 = max(boxes[k][3] for k in grp)
    groups.append((xs0, ys0, xs1, ys1, len(grp),
                   sum(cands[k][5] for k in grp)))

import math
print(f'групп рыжих секций: {len(groups)}')
out = []
for gi, (x0, y0, x1, y1, nsec, area) in enumerate(
        sorted(groups, key=lambda g: -g[5])):
    w_m = (x1 - x0) * 0.19
    h_m = (y1 - y0) * 0.19
    L = max(w_m, h_m)
    if L < 18:            # слишком мелко
        continue
    out.append((x0, y0, x1, y1, nsec, area, w_m, h_m))
    print(f'  гр{gi}: ({x0},{y0})-({x1},{y1}) {w_m:.0f}x{h_m:.0f} м '
          f'{nsec} секц, рыжего {area} px')

print(f'\nитоговых групп: {len(out)}')
for gi, (x0, y0, x1, y1, nsec, area, w_m, h_m) in enumerate(out):
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    m = 120
    crop = img[max(0, cy - m):cy + m, max(0, cx - m):cx + m]
    big = cv2.resize(crop, None, fx=2.5, fy=2.5,
                     interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(f'{BASE}/work/altay3/t60_red_g{gi}.png', big)
    print(f'saved t60_red_g{gi}.png центр ({cx},{cy})')
np.save(f'{BASE}/work/altay3/t60_red_groups.npy', np.array(out))
