#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60f: дебаг — что нарисовано на карте 06 в позициях квадратов
зоны-1 (hh53/88/102/248/172/130) и их муфт. Кропы + цвета пикселей."""
import json
import cv2
import numpy as np

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
HH = 300

tr = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']


def m2map(x, y):
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2] + HH)


net = json.load(open(f'{BASE}/work/{KEY}/network_hh3.json'))
drop_by_id = {d['hh_id']: d for d in net['drops']}
img = cv2.imread(MAP)
print('карта:', img.shape)

for hh_id in (53, 88, 102, 248, 172, 130):
    d = drop_by_id[hh_id]
    ex, ey = d['poly'][-1]
    mx, my = m2map(ex, ey)
    mx, my = int(round(mx)), int(round(my))
    crop = img[my - 40:my + 40, mx - 40:mx + 40]
    if crop.size == 0:
        print(f'hh{hh_id}: кроп пуст at ({mx},{my}) — ВНЕ КАРТЫ!')
        continue
    # цвет центра
    c = img[my, mx].astype(int)
    # 5x5 вокруг
    patch = img[my - 3:my + 4, mx - 3:mx + 4].reshape(-1, 3).mean(axis=0).astype(int)
    print(f'hh{hh_id}: map({mx},{my}) центр BGR={tuple(c)} '
          f'среднее 7x7 BGR={tuple(patch)}')
    cv2.imwrite(f'{BASE}/work/altay3/t60_dbg_hh{hh_id}.png', crop)
