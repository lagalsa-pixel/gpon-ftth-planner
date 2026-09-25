#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57b: кропы южного кармана с базового кадра (без оверлея)
+ координатная сетка для позиционирования 4 частных домов."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']

frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg').convert('RGB')
print('frame:', frame.size)


def mos_to_frame(x, y):
    fx = M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2]
    fy = M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2]
    return fx, fy  # без шапки: кадр = карта - 300 по y


# регион южного кармана (координаты мозаики)
X0, Y0, X1, Y1 = 3560, 7700, 3960, 8080
fx0, fy0 = mos_to_frame(X0, Y0)
fx1, fy1 = mos_to_frame(X1, Y1)
print(f'регион мозаика ({X0},{Y0})-({X1},{Y1}) -> '
      f'кадр ({fx0:.0f},{fy0:.0f})-({fx1:.0f},{fy1:.0f})')

c = frame.crop((int(fx0), int(fy0), int(fx1), int(fy1)))
c.save(DIR / 'south57_base_1x.jpg', quality=95)
c3 = c.resize((c.width * 3, c.height * 3), Image.LANCZOS)

# сетка 40 px (1x) = 15.3 м, метки A-Z по x, 0-9 по y
dr = ImageDraw.Draw(c3)
try:
    font = ImageFont.truetype(
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 26)
except Exception:
    font = ImageFont.load_default()

STEP = 40 * 3
cols = 'ABCDEFGHIJKLMNOPQRST'
for i, gx in enumerate(range(0, c3.width + 1, STEP)):
    x = min(gx, c3.width)
    dr.line([(x, 0), (x, c3.height)], fill=(0, 255, 255), width=2)
    if i < len(cols) and x < c3.width:
        dr.text((x + 4, 4), cols[i], fill=(255, 255, 0), font=font)
for j, gy in enumerate(range(0, c3.height + 1, STEP)):
    y = min(gy, c3.height)
    dr.line([(0, y), (c3.width, y)], fill=(0, 255, 255), width=2)
    if j < 10 and y < c3.height:
        dr.text((4, y + 4), str(j), fill=(255, 255, 0), font=font)

# опорные маркеры: дропы 131 (3746,7826), 702 (3733,7826), hh304 (3863,7996)
for hx, hy, name, col in [
        (3746.5, 7826.0, 'duplex-131', (255, 0, 0)),
        (3863.0, 7996.5, 'hh304', (0, 255, 0)),
        (3831.0, 7767.0, 'barrack-271', (0, 128, 255)),
        (3602.0, 7776.0, 'barrack-282', (0, 128, 255))]:
    mx, my = mos_to_frame(hx, hy)
    px, py = (mx - fx0) * 3, (my - fy0) * 3
    if 0 <= px < c3.width and 0 <= py < c3.height:
        dr.ellipse([px - 14, py - 14, px + 14, py + 14],
                   outline=col, width=5)
        dr.text((px + 16, py - 14), name, fill=col, font=font)

c3.save(DIR / 'south57_grid_3x.jpg', quality=95)
print('кропы: south57_base_1x.jpg', c.size, '+ south57_grid_3x.jpg', c3.size)

# соответствие сетки и мозаики для обратного преобразования
grid = dict(step_px_1x=40, x0_mos=X0, y0_mos=Y0,
            frame_x0=fx0, frame_y0=fy0,
            cols={cols[i]: X0 + (i * 40) for i in range(min(len(cols), 11))},
            rows={j: Y0 + j * 40 for j in range(10)})
json.dump(grid, open(DIR / 'south57_grid.json', 'w'), ensure_ascii=False,
          indent=1)
print('сетка: столбец A = мозаика x=%d, строка 0 = y=%d, шаг 40 px' % (X0, Y0))
