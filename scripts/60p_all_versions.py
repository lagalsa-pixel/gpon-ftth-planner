#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60p: найти ВСЕ P0-синие квадраты (25,113,194) на каждой версии
карты 06 (v4=a56adfc, v5=e63024c, v6=acf0e47, v7=3de0c7a, v8) и
проверить отпечаток скриншота: квадрат + жёлтый дроп, идущий ВВЕРХ
(север) к муфте на горизонтальном кабеле. Версии с разной зонной
раскраской дадут разные множества кандидатов."""
import json
import cv2
import numpy as np

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
HH = 300
VERSIONS = {
    'v4': f'{BASE}/work/altay3/map06_a56adfc.jpg',
    'v5': f'{BASE}/work/altay3/map06_e63024c.jpg',
    'v6': f'{BASE}/work/altay3/map06_acf0e47.jpg',
    'v7': f'{BASE}/work/altay3/map06_3de0c7a.jpg',
    'v8': f'{BASE}/work/altay3/map06_v8.jpg',
}

tr = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
# обратное преобразование map->mosaic
Mm = np.linalg.inv(np.array([
    [Mi[0][0], Mi[0][1], Mi[0][2]],
    [Mi[1][0], Mi[1][1], Mi[1][2]],
    [0, 0, 1]]))


def map2mos(x, y):
    p = Mm @ np.array([x, y - HH, 1.0])
    return p[0], p[1]


def main():
    for ver, path in VERSIONS.items():
        img = cv2.imread(path)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        # P0 (25,113,194): H~104, S~222, V~194
        blu = ((s > 170) & (v > 150) & (h >= 98) & (h <= 110)).astype(np.uint8)
        n, lab, st, cent = cv2.connectedComponentsWithStats(blu * 255, 8)
        squares = []
        for i in range(1, n):
            x, y, w2, h2, a = st[i]
            if not (12 <= w2 <= 24 and 12 <= h2 <= 24):
                continue
            if a < 100:
                continue
            cx, cy = x + w2 / 2, y + h2 / 2
            # компактность (квадрат, не линия)
            if a / (w2 * h2) < 0.55:
                continue
            squares.append((cx, cy, a))
        print(f'{ver}: P0-квадратов {len(squares)}')
        # для каждого квадрата: есть ли жёлтый дроп, уходящий ВВЕРХ (север)
        yel = ((s > 90) & (v > 90) & (h >= 18) & (h <= 36)).astype(np.uint8)
        hits = []
        for (cx, cy, a) in squares:
            # ищем жёлтые пиксели в столбе выше квадрата (до 140 px)
            col = yel[int(cy) - 140:int(cy) - 10, int(cx) - 8:int(cx) + 9]
            cnt = col.sum()
            if cnt > 40:      # вертикальный жёлтый след вверх
                hits.append((cx, cy, int(cnt)))
        print(f'   с жёлтым дропом вверх: {len(hits)}')
        for cx, cy, cnt in hits:
            mx, my = map2mos(cx, cy)
            print(f'    квадрат map({cx:.0f},{cy:.0f}) = мозаика({mx:.0f},{my:.0f}) '
                  f'жёлтых {cnt}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
