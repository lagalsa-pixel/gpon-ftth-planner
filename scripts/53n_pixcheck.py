#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 53: пиксельный контроль иконок ЦУ/ОРШ на новой карте Алтайского.

Позиции: зоны книги (orsh_px, mosaic) -> frame (M_inv) -> map (+шапка 300).
Сортировка зон и цвета — как в 48b (по числу ДХ, по убыванию; PALETTE).
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
HH = 300

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
PALETTE = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
           (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
           (160, 90, 44)]

db = json.load(open(BASE / 'work/boq_decentral_data_v4.json'))
v = next(x for x in db['villages'] if x['key'] == KEY)
net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))

img = Image.open(BASE / f'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg')
px = img.load()

ok = True


def chk(cond, msg):
    global ok
    print(('OK  ' if cond else 'FAIL ') + msg)
    ok = ok and cond


def to_map(mx, my):
    return (Mi[0][0] * mx + Mi[0][1] * my + Mi[0][2],
            Mi[1][0] * mx + Mi[1][1] * my + Mi[1][2] + HH)


# --- ЦУ на якоре ---
ax, ay = to_map(net['anchor']['x'], net['anchor']['y'])
print(f'ЦУ map=({ax:.0f},{ay:.0f})')
a = np.asarray(img.crop((int(ax) - 60, int(ay) - 70, int(ax) + 60, int(ay) + 80)))
cx, cy = 60, 70
p = a[cy, cx] if False else None


def g(x, y):
    return px[int(ax) + x, int(ay) + y]


# R = S(30)/2.6? В 48b: draw_olt_node(dr, x, y, S(74)/2.6) — проверим рамку/бейдж
# ищем красную рамку в верхней части
red = (224, 49, 49)
box = np.asarray(img.crop((int(ax) - 90, int(ay) - 110, int(ax) + 90,
                           int(ay) + 110)))
reds = (np.abs(box.astype(int) - np.array(red)).sum(axis=2) < 110).sum()
chk(reds > 150, f'ЦУ: красная рамка/элементы ({reds} красных px)')
whites = (box > 235).all(axis=2).sum()
chk(whites > 100, f'ЦУ: белые элементы здания/мачты ({whites} белых px)')
dark = (box.sum(axis=2) < 210).sum()
chk(dark > 200, f'ЦУ: тёмный бейдж ({dark} тёмных px)')

# --- ОРШ по зонам ---
zones = v['zones'][1:]                     # 0 = корневая (ЦУ)
# числа ДХ зон: из houses зоны (список ДХ)
zn = [(int(z.get('houses', 0)), z['orsh_px']) for z in zones]
zn.sort(key=lambda t: -t[0])
n_cu = 0
for i, (n_dh, orsh_px) in enumerate(zn):
    mx, my = to_map(*orsh_px)
    col = PALETTE[i]
    # корпус шкафа: цвет зоны в окне 30x40 вокруг центра
    box = np.asarray(img.crop((int(mx) - 24, int(my) - 32,
                               int(mx) + 24, int(my) + 32))).astype(int)
    d = np.abs(box - np.array(col)).sum(axis=2)
    frac = (d < 105).sum() / d.size
    chk(frac > 0.25, f'ОРШ-{i + 1}: корпус цвета зоны {col} '
        f'({frac:.0%} px, {n_dh} ДХ, map=({mx:.0f},{my:.0f}))')
    # белая окантовка
    w = (box > 225).all(axis=2).sum()
    chk(w > 30, f'ОРШ-{i + 1}: белая окантовка/цифра ({w} белых px)')

print()
print('ИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ОШИБКИ')
