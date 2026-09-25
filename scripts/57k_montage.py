#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57k: монтаж для заказчика — ответы на вопросы Task 55 исполнены.
Ряд 1: южный карман (вопрос -> результат, 4 дома подключены);
Ряд 2: здание 295 (многоэтажка, 8 ДХ) + карточка итогов."""
from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
DIR = f'{BASE}/work/altay2'

F = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
try:
    FT = ImageFont.truetype(F, 30)
    FS = ImageFont.truetype(FR, 22)
    FB = ImageFont.truetype(F, 44)
except Exception:
    FT = FS = FB = ImageFont.load_default()

# исходники
q = Image.open(f'{DIR}/south_check_3x.jpg').convert('RGB')      # вопрос
now = Image.open(f'{DIR}/south57_map_now_2x.jpg').convert('RGB')  # карман теперь
b295 = Image.open(f'{DIR}/south57_bld295_now_2x.jpg').convert('RGB')

COL_W = 1360
ROW_CAP = 46
PAD = 16
GAP = 14


def fit(im, w):
    r = w / im.width
    return im.resize((w, int(im.height * r)), Image.LANCZOS)


q_f = fit(q, COL_W)
now_f = fit(now, COL_W)
b295_f = fit(b295, COL_W // 2 - GAP // 2)

col1 = q_f.width
col2 = b295_f.width
H1 = ROW_CAP + q_f.height
H2 = ROW_CAP + b295_f.height
W = PAD * 2 + col1 + GAP + col2 + GAP + (COL_W - col2)  # не используем, ниже проще
W = PAD * 2 + COL_W + GAP + COL_W
H = 70 + H1 + GAP + H2 + PAD * 2

canvas = Image.new('RGB', (W, H), (14, 20, 30))
dr = ImageDraw.Draw(canvas)

dr.text((PAD, 14), 'Task 57 · ответы заказчика: южный карман (4 дома) + '
        'здание 637127295 (многоэтажка)', font=FT, fill=(140, 220, 255))

# --- ряд 1: вопрос -> результат ---
x = PAD
y = 70
dr.text((x, y + 8), 'ВОПРОС (Task 55): 4 частных дома — подключить?',
        font=FS, fill=(255, 220, 120))
canvas.paste(q_f, (x, y + ROW_CAP))
x2 = PAD + COL_W + GAP
dr.text((x2, y + 8), 'РЕЗУЛЬТАТ: 4 дома подключены (дропы от муфт M7/M27/M25)',
        font=FS, fill=(150, 255, 150))
canvas.paste(now_f, (x2, y + ROW_CAP))
y1 = y + H1

# --- ряд 2: здание 295 + карточка итогов ---
y = y1 + GAP
dr.text((x, y + 8), 'Здание 637127295 — многоэтажка: 1 -> 8 ДХ (формула lv=2)',
        font=FS, fill=(150, 255, 150))
canvas.paste(b295_f, (x, y + ROW_CAP))

# карточка итогов
cx = PAD + b295_f.width + GAP
cy = y + ROW_CAP
cw = COL_W - b295_f.width - GAP
ch = b295_f.height
card = Image.new('RGB', (cw, ch), (24, 34, 50))
d2 = ImageDraw.Draw(card)
d2.text((16, 14), 'ИТОГИ ЗАМЕТКИ', font=FT, fill=(140, 220, 255))
rows = [
    ('Южный карман', '+4 ДХ (частные дома)'),
    ('637127295', '1 -> 8 ДХ (многоэтажка)'),
    ('Алтайский', '639 -> 650 ДХ'),
    ('ВКО всего', '3076 -> 3087 ДХ'),
    ('Волокно', '1497,1 -> 1498,3 вол-км'),
    ('Сварки', '6914 -> 6938'),
    ('Зоны/ОРШ', '36 / 42 (без изм.)'),
    ('Муфты', '1103 (без изм.)'),
]
yy = 66
for k, v in rows:
    d2.text((16, yy), k, font=FS, fill=(170, 180, 195))
    d2.text((16, yy + 26), v, font=ImageFont.truetype(F, 20),
            fill=(240, 240, 250))
    yy += 62
d2.text((16, yy + 4), 'QA: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (84/84)', font=FS,
        fill=(150, 255, 150))
canvas.paste(card, (cx, cy))

OUT = f'{BASE}/download/snp_vko/altay_task57_result.jpg'
canvas.save(OUT, quality=90)
print('montage:', OUT, canvas.size)
