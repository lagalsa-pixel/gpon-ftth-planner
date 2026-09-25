#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 58d: монтаж для заказчика — МЖД одним значком + этап ручной
корректировки оператора (v2: фиксированная сетка, без переполнений).
Ряд 1: МЖД до/после (барак 637127272, n=32);
Ряд 2: операторская страница + карточки (итоги, как работает этап);
Ряд 3: легенда карты + карточка проверок."""
from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
DIR = f'{BASE}/work/qa/task58_before'

F = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FT = ImageFont.truetype(F, 30)
FS = ImageFont.truetype(FR, 22)
FSB = ImageFont.truetype(F, 22)

PAD, GAP, ROW_CAP, COL_W = 16, 14, 46, 1360


def fit(im, w):
    r = w / im.width
    return im.resize((w, int(im.height * r)), Image.LANCZOS)


before = fit(Image.open(f'{DIR}/crop_mzd_637127272_n32_before.jpg'), COL_W)
after = fit(Image.open(f'{DIR}/crop_mzd_637127272_n32_after.jpg'), COL_W)
editor = fit(Image.open(f'{DIR}/editor_03_edits.png'), COL_W)
legend_full = Image.open(f'{DIR}/crop_legend2.jpg')
# фрагмент легенды: нижняя часть (УСЛОВНЫЕ ОБОЗНАЧЕНИЯ со строкой МЖД)
lw, lh = legend_full.size
legend = fit(legend_full.crop((0, int(lh * 0.52), lw, lh)), 760)

W = PAD * 2 + COL_W * 2 + GAP
row1_h = ROW_CAP + before.height
row2_h = ROW_CAP + editor.height
row3_h = ROW_CAP + max(legend.height, 8 * 30 + 40)
H = 70 + row1_h + GAP + row2_h + GAP + row3_h + PAD
canvas = Image.new('RGB', (W, H), (14, 20, 30))
dr = ImageDraw.Draw(canvas)

dr.text((PAD, 14), 'Task 58 · МЖД одним значком с числом квартир + этап '
        'ручной корректировки оператора', font=FT, fill=(140, 220, 255))

# --- ряд 1: до -> после ---
y = 70
dr.text((PAD, y + 8), 'БЫЛО (v7): группа квартирных ДХ + пучок дропов',
        font=FS, fill=(255, 220, 120))
canvas.paste(before, (PAD, y + ROW_CAP))
x2 = PAD + COL_W + GAP
dr.text((x2, y + 8), 'СТАЛО (v8): один значок «32 квартиры»; дропы скрыты — расчёт сохранён',
        font=FS, fill=(150, 255, 170))
canvas.paste(after, (x2, y + ROW_CAP))

# --- ряд 2: операторская страница + карточки ---
y2 = y + row1_h + GAP
dr.text((PAD, y2 + 8), 'ЭТАП РУЧНОЙ КОРРЕКТИРОВКИ ОПЕРАТОРА: страница контроля ДХ '
        '(download/snp_vko/operator_review/<село>/index.html)',
        font=FS, fill=(255, 220, 120))
canvas.paste(editor, (PAD, y2 + ROW_CAP))
cx = PAD + COL_W + GAP + 10
cy = y2 + ROW_CAP + 6
card1 = [
    'ИТОГИ (схема D v8):',
    '• 31 МЖД-значок: Алтайский 24 (338 ДХ),',
    '   Верхнеберезовка 7 (144 ДХ)',
    '• дропы квартир и «этажные коробки» НЕ прорисованы',
    '• расчёт полностью сохранён: ВКО 3087 ДХ · 36 зон ·',
    '   42 ОРШ · 1498,3 вол-км · 6938 сварок',
    '• дуплексы (2 ДХ) и дворовые дома (3 ДХ) — как было',
]
card2 = [
    'КАК РАБОТАЕТ ЭТАП:',
    '1) оператор открывает index.html (браузер, без сервера):',
    '   спутник + ДХ + дропы + здания OSM + значки МЖД',
    '2) правки: добавить ДХ / удалить ДХ / задать число',
    '   квартир МЖД — клик по карте, с примечанием',
    '3) выгрузка corrections.json (кнопка на панели)',
    '4) 58c_apply_corrections.py применяет правки',
    '   идемпотентно (повтор — no-op), с бэкапом',
    '5) конвейер пересчитывает: 52d → 54 книга → 48b',
    '   карты → xlsx → PDF → zip → QA — правки не',
    '   теряются при перегенерации (отдельный слой-файл)',
]
for i, t in enumerate(card1):
    dr.text((cx, cy + i * 32), t, font=FSB if i == 0 else FS,
            fill=(255, 230, 150) if i == 0 else (215, 225, 240))
cy2 = cy + len(card1) * 32 + 26
for i, t in enumerate(card2):
    dr.text((cx, cy2 + i * 32), t, font=FSB if i == 0 else FS,
            fill=(255, 230, 150) if i == 0 else (215, 225, 240))

# --- ряд 3: легенда + проверки ---
y3 = y2 + row2_h + GAP
dr.text((PAD, y3 + 8), 'легенда карты v8: строка МЖД в условных обозначениях',
        font=FS, fill=(255, 220, 120))
canvas.paste(legend, (PAD, y3 + ROW_CAP))
vx = PAD + legend.width + GAP + 20
vy = y3 + ROW_CAP + 6
card3 = [
    'ПРОВЕРКИ:',
    '• VLM-контроль кропов: значок с числом читаем, пачки',
    '   синих квадратов и веера дропов у МЖД убраны, у',
    '   частных домов квадраты и дропы не тронуты',
    '• по всем 6 сёлам: Верхнеберезовка и Алтайский — значки,',
    '   в остальных МЖД нет (все группы — дуплексы/дворы)',
    '• QA v4: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (карты/книга/xlsx/zip)',
    '• идемпотентность правок: 650→653→повтор = все SKIP',
]
for i, t in enumerate(card3):
    dr.text((vx, vy + i * 32), t, font=FSB if i == 0 else FS,
            fill=(255, 230, 150) if i == 0 else (215, 225, 240))

out = f'{BASE}/download/snp_vko/task58_mzd_operator.jpg'
canvas.save(out, quality=90, subsampling=0)
print(out, canvas.size)
