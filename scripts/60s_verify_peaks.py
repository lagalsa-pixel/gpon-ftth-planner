#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60s: верификация пиков маск-матчинга на v7-карте: раскладка
символики в регионе полного кадра (кабель сверху, муфта справа на нём,
жёлтый дроп вертикально вниз, синий квадрат внизу) относительно
ожидаемых позиций со скриншота. Оба пика + сводка."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
MAP = f'{BASE}/work/altay3/map06_3de0c7a.jpg'
# пики: (полный кадр left-top на карте, Z)
PEAKS = [
    ('P1', 1955, 5729, 1.525),
    ('P2', 2168, 6660, 1.325),
    ('P2b', 2357 - 240 // 1.0, 6663, 1.4625),  # запасной вариант Z
]

# эталонные позиции элементов на скриншоте (459x339)
FIG_EL = {
    'кабель_x': (0, 295), 'кабель_y': (17, 36),
    'муфта': (283, 317, 13, 44),
    'дроп_x': (274, 303), 'дроп_y': (48, 154),
    'квадрат': (292, 317, 155, 179),
}


def analyze(name, fx, fy, Z):
    img = cv2.imread(MAP)
    Hf, Wf = int(459 / Z), int(339 / Z)
    x1, y1 = fx + Wf, fy + Hf
    crop = img[fy:y1, fx:x1]
    if crop.shape[0] < Hf - 2 or crop.shape[1] < Wf - 2:
        print(f'{name}: кроп вне карты')
        return
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    yel = ((s > 90) & (v > 90) & (h >= 18) & (h <= 36)).astype(np.uint8)
    blu = ((s > 150) & (v > 100) & (h >= 95) & (h <= 115)).astype(np.uint8)
    cyn = ((s > 110) & (v > 90) & (h >= 75) & (h <= 95)).astype(np.uint8)
    print(f'=== {name}: полный кадр map({fx},{fy}) {Wf}x{Hf} Z={Z} ===')
    # ожидаемые позиции (native = fig/Z + offset)
    ex = lambda x: x / Z
    ey = lambda y: y / Z
    print('ожидание: муфта центр', (ex(300), ey(28)),
          'квадрат центр', (ex(304), ey(167)),
          'дроп x', (ex(274), ex(303)), 'y', (ey(48), ey(154)))
    for nm, m in (('жёлтый', yel), ('синий', blu), ('циан', cyn)):
        n, lab, st, cent = cv2.connectedComponentsWithStats(m * 255, 8)
        print(f'-- {nm}: {n-1} компонент')
        for i in sorted(range(1, n), key=lambda i: -st[i][4])[:6]:
            x, y, w2, h2, a = st[i]
            if a < 15:
                continue
            bgr = crop[lab == i].mean(axis=0).astype(int)
            print(f'   at({x},{y}) {w2}x{h2} a={a} rgb=({bgr[2]},{bgr[1]},{bgr[0]})'
                  f' центр=({x+w2/2:.0f},{y+h2/2:.0f})')


analyze('P1', 1955, 5729, 1.525)
analyze('P2', 2168, 6660, 1.325)
# P2 при Z=1.4625: полный кадр left = 2357-240/1.4625, top = 6663-0
analyze('P2@1.4625', int(2357 - 240 / 1.4625), 6663, 1.4625)
