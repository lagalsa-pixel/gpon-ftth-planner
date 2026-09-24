#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Юнит-тест Task 51 (пучки кабелей/дропов) в 50_map_symbology.py.

Проверки:
 1. offset_polyline: перпендикулярность сдвига, сохранение длины на прямой;
 2. draw_cables_bundled: 4 кабеля на общем сегменте -> 4 раздельные полосы
    с промежутками (пиксельный контроль в средней трети сегмента);
 3. draw_cables_bundled: расхождение пучка (2 кабеля далее, 4 в начале)
    без потери линий;
 4. draw_drops_bundled: 3 дропа одной муфты к дому -> 3 параллельные линии
    с промежутком в середине пути, начало у муфты, конец в точках ДХ;
 5. _dashed_polyline: заполнённость штрихами ~ dash/(dash+gap).
"""
import sys, math
sys.path.insert(0, '/home/z/my-project/scripts')
import importlib.util
spec = importlib.util.spec_from_file_location('sym50', '/home/z/my-project/scripts/50_map_symbology.py')
sym = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sym)

from PIL import Image
import numpy as np

fails = []

# --- 1. offset_polyline -------------------------------------------------
pts = [(100, 100), (300, 100)]
off = 6.0
r = sym.offset_polyline(pts, off)
assert len(r) == 2
if abs(r[0][1] - (100 + off)) > 1e-6 or abs(r[0][0] - 100) > 1e-6:
    fails.append('1: сдвиг не перпендикулярен/не туда')
if abs(math.hypot(r[1][0] - r[0][0], r[1][1] - r[0][1]) - 200) > 1e-6:
    fails.append('1: длина не сохранена')
# излом 90 градусов: miter (поворот направо -> нормаль внутрь угла)
pts2 = [(100, 100), (200, 100), (200, 200)]
r2 = sym.offset_polyline(pts2, 5.0)
if not (len(r2) == 3 and abs(r2[1][0] - 195) < 2 and abs(r2[1][1] - 105) < 2):
    fails.append(f'1: внутренний miter при 90° неверен: {r2}')
r2n = sym.offset_polyline(pts2, -5.0)
if not (len(r2n) == 3 and abs(r2n[1][0] - 205) < 2 and abs(r2n[1][1] - 95) < 2):
    fails.append(f'1: внешний miter при 90° неверен: {r2n}')

# --- 2-3. draw_cables_bundled -------------------------------------------
im = Image.new('RGB', (600, 300), (20, 20, 20))
dr = im.convert('RGBA').draw if False else None
from PIL import ImageDraw
im = Image.new('RGBA', (600, 300), (20, 20, 20, 255))
dr = ImageDraw.Draw(im)
common = [(50, 150), (250, 150)]            # общий сегмент
cables = [
    dict(pts=common + [(400, 40)], color=(255, 255, 255, 255), width=4, sort_key=-0.5),
    dict(pts=common, color=(255, 0, 0, 255), width=4, dashed=True, phase=0, sort_key=0),
    dict(pts=common, color=(0, 255, 0, 255), width=4, dashed=True, phase=26, sort_key=1),
    dict(pts=common, color=(0, 0, 255, 255), width=4, dashed=True, phase=52, sort_key=2),
]
sym.draw_cables_bundled(dr, cables, gap=4.0, dash=18.0, gap_d=12.0)
a = np.asarray(im)
# вертикальный срез в середине общего сегмента (x=150): ищем полосы
# (фон непрозрачный -> ищем отличие от цвета фона)
col = a[:, 150, :]
on = np.where((col[:, 0] != 20) | (col[:, 1] != 20) | (col[:, 2] != 20))[0]
# группируем подряд идущие пиксели в полосы
runs = []
if len(on):
    s = prev = on[0]
    for y in on[1:]:
        if y - prev <= 1:
            prev = y
        else:
            runs.append((s, prev)); s = prev = y
    runs.append((s, prev))
n_bands = len(runs)
if n_bands != 4:
    fails.append(f'2: полос {n_bands}, ожидалось 4: {runs}')
else:
    gaps = [runs[i + 1][0] - runs[i][1] for i in range(3)]
    if min(gaps) < 1:
        fails.append(f'2: полосы слиплись, промежутки {gaps}')
    if max(runs[i][1] - runs[i][0] for i in range(4)) < 3:
        fails.append('2: полоса тоньше линии')
    center = (runs[0][0] + runs[-1][1]) / 2
    if abs(center - 150) > 12:
        fails.append(f'2: пучок не центрирован: {center}')
# 3: хвост кабеля 0 уходит отдельно (x=350)
col2 = a[:, 350, :]
on2 = np.where((col2[:, 0] != 20) | (col2[:, 1] != 20) | (col2[:, 2] != 20))[0]
if len(on2) < 3:
    fails.append('3: хвост кабеля потерялся при расхождении')

# --- 4. draw_drops_bundled ------------------------------------------------
im2 = Image.new('RGBA', (500, 300), (10, 10, 10, 255))
dr2 = ImageDraw.Draw(im2)
drops = []
for i, ex in enumerate([220, 230, 240]):
    drops.append(dict(pts=[(50, 150), (200, 150), (250, 150), (300, ex)],
                      coupler='C1', color=(255, 255, 0, 255), width=2))
sym.draw_drops_bundled(dr2, drops, gap=3.2, width=2, home_r_px=30.0)
b = np.asarray(im2)
colx = b[:, 220, :]          # срез в середине общего хвоста
onx = np.where((colx[:, 0] == 255) & (colx[:, 1] == 255) & (colx[:, 2] == 0))[0]
runs2 = []
if len(onx):
    s = prev = onx[0]
    for y in onx[1:]:
        if y - prev <= 1:
            prev = y
        else:
            runs2.append((s, prev)); s = prev = y
    runs2.append((s, prev))
if len(runs2) != 3:
    fails.append(f'4: дропных полос {len(runs2)}, ожидалось 3: {runs2}')
else:
    g2 = [runs2[i + 1][0] - runs2[i][1] for i in range(2)]
    if min(g2) < 1:
        fails.append(f'4: дропы слиплись: {g2}')
# начало у муфты: точка (50,150) должна быть жёлтой
if tuple(b[150, 50][:3]) != (255, 255, 0):
    fails.append('4: старт дропа не у муфты')
# конец в точках ДХ
for ex in (220, 230, 240):
    if tuple(b[ex, 300][:3]) != (255, 255, 0):
        fails.append(f'4: дроп не дошёл до точки ДХ y={ex}')
        break

# --- 5. пунктир ------------------------------------------------------------
im3 = Image.new('RGBA', (1000, 20), (0, 0, 0, 255))
dr3 = ImageDraw.Draw(im3)
sym._dashed_polyline(dr3, [(10, 10), (990, 10)], (255, 255, 255, 255), 3,
                     37.0, 30.0, 20.0)
c3 = np.asarray(im3)[7:13, :, 0].max(axis=0)   # красный канал, фон 0
fill = int((c3 > 100).sum())
expect = int(980 * 30.0 / 50.0)
if abs(fill - expect) > 0.15 * expect:
    fails.append(f'5: заполнение пунктира {fill}, ожидалось ~{expect}')

print('полос кабелей:', n_bands, '| дропных полос:', len(runs2), '| пунктир px:', fill)
if fails:
    print('ПРОВАЛЫ:')
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('ЮНИТ-ТЕСТ 51: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
