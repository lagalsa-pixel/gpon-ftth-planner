#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50h (v2): контроль иконок ЦУ/OLT и ОРШ на карте Топольного — быстро."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage

MAP = '/home/z/my-project/work/topolnoe_test/download/07_Топольное_зоны_ОРШ.jpg'
DS = 4
im = Image.open(MAP).convert('RGB')
W, H = im.size
sm = im.resize((W // DS, H // DS), Image.BILINEAR)
a = np.asarray(sm).astype(int)
print('карта:', W, 'x', H, '| скан', a.shape[1], 'x', a.shape[0])

ok = True
def chk(cond, msg):
    global ok
    print(('OK  ' if cond else 'FAIL ') + msg)
    ok = ok and cond

def clusters(mask, min_px=8):
    lab, n = ndimage.label(mask)
    if n == 0:
        return []
    cnt = ndimage.sum_labels if hasattr(ndimage, 'sum_labels') else None
    sizes = np.bincount(lab.ravel())
    cents = ndimage.center_of_mass(mask, lab, index=range(1, n + 1))
    out = []
    for i, (cy, cx) in zip(range(1, n + 1), cents):
        if sizes[i] >= min_px:
            out.append((cx * DS, cy * DS, sizes[i] * DS * DS))
    return out

def near(c, t, tol=50):
    return (np.abs(a[:,:,0] - t[0]) < tol) & (np.abs(a[:,:,1] - t[1]) < tol) & (np.abs(a[:,:,2] - t[2]) < tol)

# --- ЦУ/OLT: красный бейдж ---
cl = clusters(near(a, (224, 49, 49), 55), min_px=10)
cl.sort(key=lambda c: -c[2])
print('красные кластеры (топ-3):', [(round(c[0]), round(c[1]), c[2]) for c in cl[:3]])
chk(len(cl) >= 1, 'ЦУ: найден красный бейдж OLT')
cx, cy = int(cl[0][0]), int(cl[0][1])

# структура в полном разрешении вокруг бейджа
full = np.asarray(im).astype(int)
def box(cx, cy, r):
    return full[max(0, cy-r):cy+r, max(0, cx-r):cx+r]

b = box(cx, cy, 80)
navy = ((np.abs(b[:,:,0]-16)<35) & (np.abs(b[:,:,1]-24)<35) & (np.abs(b[:,:,2]-42)<45)).sum()
wh = ((b[:,:,0]>235) & (b[:,:,1]>235) & (b[:,:,2]>235)).sum()
chk(navy > 300, f"ЦУ: тёмный корпус бейджа ({navy} px)")
chk(wh > 250, f"ЦУ: белые элементы здание/мачта/OLT ({wh} px)")

# --- ОРШ: корпуса цветов зон PALETTE 1..3 + белая цифра + цоколь ---
PAL = {1: (25, 113, 194), 2: (47, 158, 68), 3: (240, 140, 0)}
for zn, col in PAL.items():
    cand = clusters(near(a, col, 55), min_px=15)
    cand.sort(key=lambda c: -c[2])
    found = None
    for c in cand[:25]:
        x0, y0 = int(c[0]), int(c[1])
        bb = box(x0, y0, 45)
        wbox = ((bb[:,:,0]>235) & (bb[:,:,1]>235) & (bb[:,:,2]>235)).sum()
        dbox = ((np.abs(bb[:,:,0]-28)<45) & (np.abs(bb[:,:,1]-30)<45) & (np.abs(bb[:,:,2]-36)<50)).sum()
        if wbox >= 25 and dbox >= 25:
            found = (x0, y0, c[2], wbox, dbox)
            break
    if found:
        chk(True, f"ОРШ-{zn}: шкаф {col} ({found[2]}px), цифра {found[3]}px, цоколь {found[4]}px @({found[0]},{found[1]})")
    else:
        chk(False, f"ОРШ-{zn}: шкаф не найден ({len(cand)} кластеров)")

print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ')
sys.exit(0 if ok else 1)
