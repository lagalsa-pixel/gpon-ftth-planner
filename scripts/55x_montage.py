#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55x: монтаж-отчёт для заказчика по altay2.pdf (как Task 54 montage).
Верхний ряд: фрагменты заказчика; нижний ряд: те же здания на обновлённой
карте с дропами. Плюс кроп южного кармана — вопрос заказчику."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay2'
OUT = BASE / 'download/snp_vko/altay2_task55_result.jpg'

FB = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 34)
FS = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 27)

mapv5 = Image.open(
    BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg').convert('RGB')

CELL_H = 420  # нормированная высота ячеек верхнего ряда


def crop_map(mx, my, half=170):
    c = mapv5.crop((int(mx - half), int(my - half),
                    int(mx + half), int(my + half)))
    return c


# клетки: (файл фрагмента, подпись сверху, кроп карты (mx,my), подпись снизу)
cells = [
    ('img_9.png', 'Фрагмент 1: два жилых здания',
     (1812, 5990), 'Бараки 290 + 291 — по 8 ДХ'),
    ('img_10.png', 'Фрагмент 2: жилое здание',
     (1517, 6326), 'Барак 289 — 8 ДХ'),
    ('img_11.png', 'Фрагмент 3: жилое здание',
     (1918, 6688), 'Здание 283: 1 -> 4 ДХ (+3)'),
    ('img_12.png', 'Фрагмент 4: жилое здание',
     (2400, 6776), 'Дуплекс: 1 -> 2 ДХ (+1)'),
]

PAD = 16
GAP = 20
COL_W = 560

rows_top = []
for fig_f, cap_top, (mx, my), cap_bot in cells:
    fig = Image.open(DIR / fig_f).convert('RGB')
    w = int(fig.width * CELL_H / fig.height)
    fig = fig.resize((w, CELL_H), Image.LANCZOS)
    mp = crop_map(mx, my)
    mp = mp.resize((COL_W, COL_W), Image.LANCZOS)
    rows_top.append((fig, mp, cap_top, cap_bot))

W = PAD * 2 + COL_W * 4 + GAP * 3
ROW_CAP = 96
row1_h = ROW_CAP + CELL_H
row2_h = ROW_CAP + COL_W
H = PAD * 2 + row1_h + GAP + row2_h + 60
canvas = Image.new('RGB', (W, H), (14, 20, 30))
dr = ImageDraw.Draw(canvas)

# заголовок
dr.text((PAD, 12),
        'Замечания altay2.pdf (Алтайский): ВКО 3072 -> 3076 ДХ',
        font=FB, fill=(255, 220, 120))

y0 = 56
x = PAD
for fig, mp, cap_top, cap_bot in rows_top:
    dr.text((x, y0 + 6), cap_top, font=FS, fill=(200, 220, 255))
    canvas.paste(fig, (x, y0 + ROW_CAP))
    x += COL_W + GAP

y1 = y0 + row1_h + GAP
x = PAD
for fig, mp, cap_top, cap_bot in rows_top:
    dr.text((x, y1 + 6), cap_bot, font=FS, fill=(150, 255, 150))
    canvas.paste(mp, (x, y1 + ROW_CAP))
    x += COL_W + GAP

dr.text((PAD, H - 44),
        'Нижний ряд: обновлённая карта 06 — новые ДХ подключены',
        font=FS, fill=(180, 180, 190))

canvas.save(OUT, quality=90)
print('montage:', OUT, canvas.size)

# --- южный карман: вопрос заказчику ---
q = Image.open(DIR / 'south_check_3x.jpg').convert('RGB')
qc = Image.new('RGB', (q.width, q.height + 90), (14, 20, 30))
d2 = ImageDraw.Draw(qc)
d2.text((14, 12),
        'ВОПРОС ЗАКАЗЧИКУ: южнее фрагмента 4 — 4 частных дома, '
        'в данных только 1 (cv). Подключать?',
        font=FS, fill=(255, 220, 120))
qc.paste(q, (0, 84))
qc.save(BASE / 'download/snp_vko/altay2_task55_question_south.jpg',
         quality=92)
print('question:', qc.size)
