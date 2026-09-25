#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55k: точный кроп нового здания (4x) + сетка для VLM-оцифровки."""
from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
DIR = f'{BASE}/work/altay2'

frame = Image.open(f'{BASE}/upload/06_Алтайский_граница.jpg').convert('RGB')
# центр по VLM (2357, 6476), здание ~28x10 м => ~147x52 px на кадре
CX, CY = 2357, 6476
M = 110
c = frame.crop((CX - M, CY - M, CX + M, CY + M))  # 220x220
# сетка 20 px с подписями координат кропа
dr = ImageDraw.Draw(c)
f = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 11)
for gx in range(0, 2 * M + 1, 20):
    dr.line([(gx, 0), (gx, 2 * M)], fill=(255, 255, 0), width=1)
    dr.text((gx + 2, 2), str(gx), font=f, fill=(255, 255, 0))
for gy in range(0, 2 * M + 1, 20):
    dr.line([(0, gy), (2 * M, gy)], fill=(255, 255, 0), width=1)
    dr.text((2, gy + 2), str(gy), font=f, fill=(255, 255, 0))
c.save(f'{DIR}/new_bld_grid_1x.jpg', quality=96)
c.resize((c.width * 4, c.height * 4), Image.LANCZOS).save(
    f'{DIR}/new_bld_grid_4x.jpg', quality=96)
print('crop 220x220 сохранён, углы кропа в кадре:',
      (CX - M, CY - M), '-', (CX + M, CY + M))
