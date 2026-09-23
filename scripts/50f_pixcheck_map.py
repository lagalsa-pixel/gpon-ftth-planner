#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50f: пиксельный контроль новых иконок на итоговой карте ВБ (кропы 50d)."""
import os, sys
from PIL import Image

Q = '/home/z/my-project/work/qa/symbology_t50'
ok = True

def chk(cond, msg):
    global ok
    print(('OK  ' if cond else 'FAIL ') + msg)
    ok = ok and cond

def near(c, t, tol=45):
    return all(abs(a - b) <= tol for a, b in zip(c, t))

# ---------- ЦУ / OLT: кроп 520x520, иконка в центре (R=30) ----------
cu = Image.open(f'{Q}/01_cu_olt.jpg').convert('RGB')
cx, cy = cu.width // 2, cu.height // 2
px = cu.load()
chk(near(px[cx, cy - 39], (224, 49, 49), 55), f"ЦУ: красная рамка сверху {px[cx, cy-39]}")
chk(near(px[cx - 34, cy], (224, 49, 49), 55), f"ЦУ: красная рамка сбоку {px[cx-34, cy]}")
chk(near(px[cx - 9, cy + 8], (245, 248, 252), 35), f"ЦУ: белое здание (слева от двери) {px[cx-9, cy+8]}")
chk(near(px[cx, cy + 10], (16, 24, 40), 45), f"ЦУ: тёмная дверь здания {px[cx, cy+10]}")
chk(near(px[cx - 22, cy + 19], (224, 49, 49), 55), f"ЦУ: красная табличка OLT {px[cx-22, cy+19]}")
row = [px[x, cy + 19] for x in range(cx - 24, cx + 25)]
chk(any(near(c, (255, 255, 255), 25) for c in row), "ЦУ: белый текст OLT на табличке")
col = [px[cx, y] for y in range(cy - 28, cy - 5)]
chk(any(near(c, (255, 255, 255), 30) for c in col), "ЦУ: белая мачта антенны")
# подпись ЦУ где-то рядом (белый текст с тёмной обводкой) — ищем светлые кластеры вне иконки
box = cu.crop((0, 0, cu.width, cu.height - 70))
import numpy as np
arr = np.asarray(box)
white = ((arr > 235).all(axis=2)).sum()
chk(white > 400, f"ЦУ: подпись/элементы читаемы ({white} белых px вне нижней зоны)")

# ---------- ОРШ-1: кроп 440x440, иконка в центре (R=16), зона 1 = синяя ----------
o1 = Image.open(f'{Q}/02_orsh_1.jpg').convert('RGB')
cx, cy = o1.width // 2, o1.height // 2
px = o1.load()
chk(near(px[cx - 8, cy - 6], (25, 113, 194), 50), f"ОРШ1: синий корпус зоны {px[cx-8, cy-6]}")
chk(near(px[cx + 8, cy - 6], (25, 113, 194), 50), f"ОРШ1: синий корпус справа {px[cx+8, cy-6]}")
col = [px[cx, y] for y in range(cy - 12, cy + 2)]
chk(any(near(c, (255, 255, 255), 25) for c in col), "ОРШ1: белая цифра номера")
chk(near(px[cx, cy + 10], (255, 255, 255), 60), f"ОРШ1: линия дверец {px[cx, cy+10]}")
chk(near(px[cx, cy + 19], (28, 30, 36), 45), f"ОРШ1: тёмный цоколь {px[cx, cy+19]}")
chk(near(px[cx + 14, cy + 20], (0, 0, 0), 80) or near(px[cx + 15, cy + 19], (20, 22, 28), 60),
    f"ОРШ1: тень/контур {px[cx+14, cy+20]}")

print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ')
sys.exit(0 if ok else 1)
