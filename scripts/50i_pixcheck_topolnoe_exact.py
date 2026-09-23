#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50i: точный контроль иконок ЦУ/ОРШ карты Топольного (по позициям из данных).

Позиции: boq.json -> zones[i]['px'] (мозаика), anchor; мозаика -> кадр через
M_inv (crop_transform), кадр -> карта: +HH_HDR по Y. Иконки: ЦУ R=30k,
ОРШ R=16k, k=1/scale.
"""
import json, sys
import numpy as np
from PIL import Image

BASE = '/home/z/my-project/work/topolnoe_test/work/topolnoe'
MAP = '/home/z/my-project/work/topolnoe_test/download/07_Топольное_зоны_ОРШ.jpg'

db = json.load(open(f'{BASE}/boq.json', encoding='utf-8'))
net = json.load(open(f"{BASE}/{db['net']}", encoding='utf-8'))
ct = json.load(open(f'{BASE}/crop_transform.json', encoding='utf-8'))
Minv, scale = ct['M_inv'], ct['scale']
k = 1.0 / scale
im = Image.open(MAP).convert('RGB')
W, H = im.size
HH = 150                      # шапка карты (см. HH_HDR в ftth_outputs)
a = np.asarray(im).astype(int)

def T(p):
    x, y = p
    return (Minv[0][0]*x + Minv[0][1]*y + Minv[0][2],
            Minv[1][0]*x + Minv[1][1]*y + Minv[1][2])

def px(x, y):
    xx, yy = int(round(x)), int(round(y + HH))
    return a[yy, xx] if 0 <= yy < H and 0 <= xx < W else None

ok = True
def chk(cond, msg):
    global ok
    print(('OK  ' if cond else 'FAIL ') + msg)
    ok = ok and cond

def near(c, t, tol):
    return c is not None and all(abs(int(x)-y) <= tol for x, y in zip(c, t))

# ---------- ЦУ ----------
ax, ay = T((net['anchor']['x'], net['anchor']['y']))
R = 30 * k
print(f"ЦУ @({ax:.0f},{ay:.0f}+{HH}), R={R:.1f}")
cx, cy = int(round(ax)), int(round(ay + HH))
chk(near(px(cx, cy - int(1.28*R)), (224, 49, 49), 60), f"рамка сверху {px(cx, cy-int(1.28*R))}")
chk(near(px(cx - int(1.1*R), cy), (224, 49, 49), 60), f"рамка сбоку {px(cx-int(1.1*R), cy)}")
chk(near(px(cx, cy + int(0.75*R)), (16, 24, 40), 50), f"тёмный корпус {px(cx, cy+int(0.75*R))}")
row_w = [px(x, cy - int(0.2*R)) for x in range(cx - int(0.5*R), cx + int(0.5*R))]
chk(any(near(c, (255, 255, 255), 30) for c in row_w), "белые элементы (мачта/дуги/крыша)")
row_p = [px(x, cy + int(0.72*R)) for x in range(cx - int(0.7*R), cx + int(0.7*R))]
chk(any(near(c, (224, 49, 49), 60) for c in row_p), "табличка OLT красная")

# ---------- ОРШ зоны ----------
PAL = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181)]
zones = [z for z in db['zones'] if not str(z.get('zone', '')).startswith('ЦУ')]
print(f"зонных ОРШ: {len(zones)}")
for i, z in enumerate(zones):
    zx, zy = T(z['px'])
    Rz = 16 * k
    cx, cy = int(round(zx)), int(round(zy + HH))
    col = PAL[i % len(PAL)]
    print(f"ОРШ-{i+1} @({cx},{cy}), R={Rz:.1f}, цвет {col}")
    chk(near(px(cx - int(0.4*Rz), cy - int(0.3*Rz)), col, 55), f"ОРШ-{i+1}: корпус цвета зоны {px(cx-int(0.4*Rz), cy-int(0.3*Rz))}")
    col_v = [px(cx, y) for y in range(cy - int(0.7*Rz), cy + int(0.1*Rz))]
    chk(any(near(c, (255, 255, 255), 35) for c in col_v), f"ОРШ-{i+1}: белая цифра")
    chk(near(px(cx, cy + int(1.1*Rz)), (28, 30, 36), 50), f"ОРШ-{i+1}: цоколь {px(cx, cy+int(1.1*Rz))}")

print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ')
sys.exit(0 if ok else 1)
