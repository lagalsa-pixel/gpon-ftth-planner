#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59h: монтаж для заказчика — altay3 «Это многоквартирный дом».
Ряд 1: скриншот заказа | та же зона на обновлённой карте (значок МЖД «4»).
Ряд 2: карточки ИТОГИ и МЕТОД (идентификация скриншота)."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
OUT = BASE / 'download/snp_vko/altay3_task59_result.jpg'
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def F(sz, bold=True):
    return ImageFont.truetype(FB if bold else FR, sz)


def main():
    fig = Image.open(BASE / 'work/altay3/img_9_p1.png').convert('RGB')
    # зона на карте: значок на (3491, 4080), здание ниже; кроп 560x440
    mp = Image.open(BASE / 'download/snp_vko/'
                    '05_Пригородное_зоны_ОРШ_схема_D.jpg')
    cx, cy = 3491, 4080
    crop = mp.crop((cx - 280, cy - 120, cx + 280, cy + 320))

    W = 1240
    ph = 60
    row_h = 420
    card_h = 240
    H = ph + row_h + 16 + card_h + 24
    canvas = Image.new('RGB', (W, H), (10, 16, 26))
    dr = ImageDraw.Draw(canvas)

    dr.text((24, 14), 'altay3.pdf: «Это многоквартирный дом» — Пригородное, '
            'здание OSM 688327687 (10,9 x 25,6 м)',
            font=F(26), fill=(140, 220, 255))

    # ряд 1: скриншот | карта
    pw = (W - 48 - 16) // 2
    f1 = fig.copy()
    f1.thumbnail((pw, row_h - 44), Image.LANCZOS)
    c1 = Image.new('RGB', (pw, row_h - 44), (18, 26, 38))
    c1.paste(f1, ((pw - f1.width) // 2, (row_h - 44 - f1.height) // 2))
    canvas.paste(c1, (24, ph + 36))
    dr.text((24, ph + 8), 'Скриншот заказчика (altay3.pdf)',
            font=F(22), fill=(255, 220, 120))

    c2 = Image.new('RGB', (pw, row_h - 44), (18, 26, 38))
    f2 = crop.copy()
    f2.thumbnail((pw, row_h - 44), Image.LANCZOS)
    c2.paste(f2, ((pw - f2.width) // 2, (row_h - 44 - f2.height) // 2))
    canvas.paste(c2, (24 + pw + 16, ph + 36))
    dr.text((24 + pw + 16, ph + 8),
            'Карта v9: значок МЖД «4» (дропы скрыты, расчёт сохранён)',
            font=F(22), fill=(150, 255, 170))

    # рамки
    for x in (24, 24 + pw + 16):
        dr.rectangle([x, ph + 36, x + pw, ph + 36 + row_h - 44],
                     outline=(90, 130, 170), width=2)

    # ряд 2: карточки
    y0 = ph + row_h + 16
    cw = (W - 48 - 16) // 2
    dr.rounded_rectangle([24, y0, 24 + cw, y0 + card_h], radius=12,
                         fill=(16, 28, 44), outline=(70, 120, 160), width=2)
    dr.rounded_rectangle([24 + cw + 16, y0, 24 + cw + 16 + cw, y0 + card_h],
                         radius=12, fill=(16, 28, 44),
                         outline=(70, 120, 160), width=2)
    dr.text((40, y0 + 16), 'ИТОГИ', font=F(24), fill=(140, 220, 255))
    lines = [
        '• Формула квартир (lv=1, S=279,5 м², 1 подъезд): N = 4',
        '• Пригородное: 286 -> 288 ДХ (+2)',
        '• ВКО: 3087 -> 3089 ДХ · 1498,3 вол-км · 6942 сварки',
        '• Значков МЖД теперь 32 (Пригородное +1)',
        '• QA: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (84/84)',
    ]
    for i, t in enumerate(lines):
        dr.text((40, y0 + 56 + i * 34), t, font=F(20, False),
                fill=(225, 235, 245))

    dr.text((40 + cw + 16, y0 + 16), 'КАК ИДЕНТИФИЦИРОВАНО',
            font=F(24), fill=(140, 220, 255))
    lines2 = [
        '• Скриншот привязан к карте 05: то же здание,',
        '  та же муфта 108 и трасса дропа',
        '• 1 этаж: двускатная крыша, ширина 10,8 м,',
        '  тени как у соседних 1-эт. домов (VLM, 85%)',
        '• Квартирные ДХ — вдоль длинной оси здания',
    ]
    for i, t in enumerate(lines2):
        dr.text((40 + cw + 16, y0 + 56 + i * 34), t, font=F(20, False),
                fill=(225, 235, 245))

    canvas.save(OUT, quality=92)
    print('saved', OUT, canvas.size)


if __name__ == '__main__':
    main()
