#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60 (монтаж): altay3 — «Это многоквартирный дом», ИСПРАВЛЕНИЕ
Task 59: здание в селе АЛТАЙСКИЙ (вне-OSM барак у муфты M24).
Ряд 1: скриншот заказа | та же зона на карте v4 (раскладка 1:1) |
       новая карта v10 со значком МЖД «4».
Ряд 2: карточки ИТОГИ / МЕТОД / ИСПРАВЛЕНИЕ."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path('/home/z/my-project')
OUT = BASE / 'download/snp_vko/altay3_task60_result.jpg'
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def F(sz, bold=True):
    return ImageFont.truetype(FB if bold else FR, sz)


def main():
    fig = Image.open(BASE / 'work/altay3/img_9_p1.png').convert('RGB')
    v4 = Image.open(BASE / 'work/altay3/t60_found_v4zoom.png').convert('RGB')
    mp = Image.open(BASE / 'download/snp_vko/'
                    '06_Алтайский_зоны_ОРШ_схема_D.jpg').convert('RGB')
    # значок на (2295, 6732); кроп как в Task 59: 560x440
    crop = mp.crop((2295 - 300, 6732 - 140, 2295 + 300, 6732 + 320))

    W = 1460
    ph = 58
    row_h = 400
    card_h = 268
    H = ph + row_h + 14 + card_h + 22
    canvas = Image.new('RGB', (W, H), (10, 16, 26))
    dr = ImageDraw.Draw(canvas)

    dr.text((24, 12), 'altay3.pdf: «Это многоквартирный дом» — ИСПРАВЛЕНИЕ: '
            'село Алтайский (барак вне OSM, муфта M24)',
            font=F(27), fill=(140, 220, 255))

    # ряд 1: три панели
    pw = (W - 48 - 32) // 3
    panels = [
        ('Скриншот заказчика (карта v4)', fig, (255, 220, 120)),
        ('Карта v4, найденная зона: раскладка 1:1', v4, (150, 255, 170)),
        ('Карта v10: значок МЖД «4» на здании', crop, (150, 255, 170)),
    ]
    for i, (title, im, col) in enumerate(panels):
        x = 24 + i * (pw + 16)
        c = Image.new('RGB', (pw, row_h - 46), (18, 26, 38))
        f = im.copy()
        f.thumbnail((pw - 8, row_h - 54), Image.LANCZOS)
        c.paste(f, ((pw - f.width) // 2, (row_h - 46 - f.height) // 2))
        canvas.paste(c, (x, ph + 36))
        dr.text((x, ph + 8), title, font=F(19), fill=col)
        dr.rectangle([x, ph + 36, x + pw, ph + 36 + row_h - 46],
                     outline=(90, 130, 170), width=2)

    # ряд 2: три карточки
    y0 = ph + row_h + 14
    cw = (W - 48 - 32) // 3
    cards = [
        ('ИТОГИ', [
            '• Формула квартир (lv=1, S=432 м²,',
            '  1 подъезд): N = 4',
            '• Алтайский: 650 -> 652 ДХ (+2)',
            '• ВКО: 3089 ДХ (как было) · 1499,2',
            '  вол-км (+0,9) · 6942 сварки',
            '• Значков МЖД 32, под ними 486 ДХ',
            '• QA: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ',
        ]),
        ('МЕТОД', [
            '• Цветовой маск-матчинг символики:',
            '  кабель+муфта+дроп+квадрат = 6/6',
            '  элементов на карте v4, отл. 1-2 px',
            '• Зум скриншота Z=1,46 определён по',
            '  толщине линий и размерам квадратов',
            '• Этажность: 1 (3 VLM-прохода, парa',
            '  с известным 2-эт бараком 637127282)',
        ]),
        ('ИСПРАВЛЕНИЕ TASK 59', [
            '• Task 59 ошибочно отнёс здание к',
            '  Пригородному (ложный цвет зоны) —',
            '  правка отменена: Пригородное 288 -> 286',
            '• Здание добавлено в OSM-слой',
            '  (полигон 29,8 x 14,5 м)',
            '• Легенда карты 06 более не накрывает',
            '  здание (вес значков МЖД поднят)',
        ]),
    ]
    for i, (title, lines) in enumerate(cards):
        x = 24 + i * (cw + 16)
        dr.rounded_rectangle([x, y0, x + cw, y0 + card_h], radius=12,
                             fill=(16, 28, 44), outline=(70, 120, 160),
                             width=2)
        dr.text((x + 16, y0 + 14), title, font=F(22), fill=(140, 220, 255))
        for j, t in enumerate(lines):
            dr.text((x + 16, y0 + 48 + j * 30), t, font=F(17, False),
                    fill=(225, 235, 245))

    canvas.save(OUT, quality=92)
    print('saved', OUT, canvas.size)


if __name__ == '__main__':
    main()
