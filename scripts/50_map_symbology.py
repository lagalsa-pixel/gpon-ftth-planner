#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 50 (директива 23.09.2026): интуитивно понятные обозначения на картах зон.

Иконки для 48b_zone_maps_v4.py (и последующих рендеров):

  draw_olt_node(dr, x, y, R, ...)  — узел ЦУ / OLT: здание со шпилем-антенной,
      сигнальные дуги по бокам (читается как «станция/узел связи»),
      табличка-бейдж «OLT» на фасаде. Красный акцент сохранён (цвет корня).

  draw_orsh(dr, x, y, R, color, number) — зонный ОРШ: уличный шкаф — корпус
      цвета зоны с белой окантовкой, две дверцы с ручками, вентиляционные
      щели, цоколь-опора, крупный НОМЕР зоны на корпусе.

Обе функции рисуют в PIL ImageDraw; (x, y) — центр значка, R — масштаб
(половина габарита). Шрифты — DejaVu (есть в системе).
"""
import os
from PIL import ImageDraw

_FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
_FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

_font_cache = {}


def _font(sz):
    """DejaVu Bold кэшированный; sz<=0 -> None (нет текста)."""
    sz = int(round(sz))
    if sz <= 0:
        return None
    if sz not in _font_cache:
        from PIL import ImageFont
        _font_cache[sz] = ImageFont.truetype(_FB, sz)
    return _font_cache[sz]


# ----------------------------------------------------------------- ЦУ/OLT ---
def draw_olt_node(dr, x, y, R, *, plate_h=0.52, show_text=True):
    """Узел ЦУ/OLT. R — полу-габарит значка (~высота/2.6).

    Слои: гало -> тёмный бейдж со скруглением и двойной рамкой (красная
    внешняя + белая внутренняя) -> здание (крыша+корпус, белое) -> мачта
    с огоньком -> сигнальные дуги слева/справа -> красная табличка «OLT».
    """
    x, y, R = float(x), float(y), float(R)
    W2, H2 = 1.15 * R, 1.30 * R          # полуширина/полувысота бейджа
    # 0) гало (читаемость на любом снимке)
    dr.ellipse([x - 1.45 * R, y - 1.45 * R, x + 1.45 * R, y + 1.45 * R],
               fill=(0, 0, 0, 105))
    # 1) бейдж: красная внешняя рамка -> тёмный корпус -> белая внутренняя
    dr.rounded_rectangle([x - W2, y - H2, x + W2, y + H2], radius=0.28 * R,
                         fill=(224, 49, 49, 255))
    pad = max(1.0, 0.09 * R)
    dr.rounded_rectangle([x - W2 + pad, y - H2 + pad, x + W2 - pad, y + H2 - pad],
                         radius=0.22 * R, fill=(16, 24, 40, 252))
    pad2 = max(1.0, 0.16 * R)
    # 2) сигнальные дуги + мачта (верхняя зона бейджа)
    mast_top = y - 0.92 * R
    roof_apex = y - 0.28 * R
    arc_c = (x, mast_top)
    for rr_ in (0.34 * R, 0.58 * R):
        w = max(1, int(round(0.10 * R)))
        dr.arc([arc_c[0] - rr_, arc_c[1] - rr_, arc_c[0] + rr_, arc_c[1] + rr_],
               118, 242, fill=(255, 255, 255, 255), width=w)      # левая
        dr.arc([arc_c[0] - rr_, arc_c[1] - rr_, arc_c[0] + rr_, arc_c[1] + rr_],
               -62, 62, fill=(255, 255, 255, 255), width=w)       # правая
    mw = max(1, int(round(0.09 * R)))                              # мачта
    dr.line([(x, mast_top), (x, roof_apex)], fill=(255, 255, 255, 255), width=mw)
    dr.ellipse([x - 0.14 * R, mast_top - 0.14 * R, x + 0.14 * R, mast_top + 0.14 * R],
               fill=(255, 120, 90, 255))                           # огонёк
    # 3) здание: крыша + корпус (белые, тёмная дверь)
    hw, roof_base = 0.52 * R, y + 0.10 * R
    dr.polygon([(x, roof_apex), (x - hw, roof_base), (x + hw, roof_base)],
               fill=(245, 248, 252, 255))
    body_top, body_bot = roof_base, y + (0.90 - plate_h) * R + 0.06 * R
    dr.rectangle([x - 0.46 * R, body_top, x + 0.46 * R, body_bot],
                 fill=(245, 248, 252, 255))
    dr.rectangle([x - 0.11 * R, body_bot - 0.34 * R, x + 0.11 * R, body_bot],
                 fill=(16, 24, 40, 255))                           # дверь
    # 4) табличка «OLT»
    if show_text:
        ph = plate_h * R
        pl_top, pl_bot = y + 0.90 * R - ph, y + 0.90 * R
        dr.rounded_rectangle([x - 0.82 * R, pl_top, x + 0.82 * R, pl_bot],
                             radius=0.10 * R, fill=(224, 49, 49, 255),
                             outline=(255, 255, 255, 255), width=max(1, int(0.05 * R)))
        f = _font(0.40 * R)
        if f is not None:
            tb = dr.textbbox((0, 0), 'OLT', font=f)
            dr.text((x - (tb[2] - tb[0]) / 2 - tb[0], pl_top + (ph - (tb[3] - tb[1])) / 2 - tb[1]),
                    'OLT', font=f, fill=(255, 255, 255, 255))


# -------------------------------------------------------------------- ОРШ ---
def draw_orsh(dr, x, y, R, color, number):
    """Зонный ОРШ — уличный шкаф. R — полу-габарит по ширине (~w/1.5).

    Слои: тень -> цоколь -> корпус (цвет зоны, белая окантовка) ->
    вентиляционные щели -> линия дверец + ручки -> крупный НОМЕР зоны.
    """
    x, y, R = float(x), float(y), float(R)
    col = tuple(color[:3]) + (255,)
    w2, h2 = 0.75 * R, 1.08 * R                 # полуширина/полувысота корпуса
    # 0) тень (лёгкое смещение вправо-вниз)
    dr.rounded_rectangle([x - w2 + 0.10 * R, y - h2 + 0.12 * R, x + w2 + 0.10 * R,
                          y + h2 + 0.12 * R], radius=0.12 * R, fill=(0, 0, 0, 95))
    # 1) цоколь-опора
    dr.rectangle([x - 0.55 * R, y + h2 - 0.02 * R, x + 0.55 * R, y + h2 + 0.20 * R],
                 fill=(28, 30, 36, 255))
    # 2) корпус: тёмная внешняя окантовка -> цвет зоны -> белая рамка
    dr.rounded_rectangle([x - w2, y - h2, x + w2, y + h2], radius=0.10 * R,
                         fill=(20, 22, 28, 255))
    p1 = max(1.0, 0.085 * R)
    dr.rounded_rectangle([x - w2 + p1, y - h2 + p1, x + w2 - p1, y + h2 - p1],
                         radius=0.08 * R, fill=col,
                         outline=(255, 255, 255, 255), width=max(1, int(0.075 * R)))
    # 3) вентиляционные щели (верх)
    sw = max(1, int(round(0.055 * R)))
    for k in range(3):
        yy = y - h2 + (0.24 + 0.13 * k) * R
        dr.line([(x - 0.44 * R, yy), (x + 0.44 * R, yy)], fill=(255, 255, 255, 235),
                width=sw)
    # 4) номер зоны — крупно, по центру верхней половины
    f = _font(0.62 * R)
    if f is not None and number is not None:
        txt = str(number)
        tb = dr.textbbox((0, 0), txt, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        cy = y - 0.30 * R
        dr.text((x - tw / 2 - tb[0], cy - th / 2 - tb[1]), txt, font=f,
                fill=(255, 255, 255, 255),
                stroke_width=max(1, int(0.055 * R)), stroke_fill=(15, 15, 15, 255))
    # 5) дверцы: линия раздела (нижняя половина) + ручки
    dl = max(1, int(round(0.05 * R)))
    dr.line([(x, y + 0.10 * R), (x, y + h2 - p1 - 0.04 * R)],
            fill=(255, 255, 255, 235), width=dl)
    hr = max(1.0, 0.055 * R)
    for hx in (x - 0.14 * R, x + 0.14 * R):
        dr.ellipse([hx - hr, y + 0.48 * R - hr, hx + hr, y + 0.48 * R + hr],
                   fill=(255, 255, 255, 255))


# --------------------------------------------------------------- самопроверка
if __name__ == '__main__':
    """Отрисовка образцов иконок: work/symbology_preview.png."""
    from PIL import Image, ImageFont
    import math
    S = 3.2                                    # как на карте ~S(1)
    W, H = int(560 * S / 3.2), int(420 * S / 3.2)
    im = Image.new('RGB', (W, H), (92, 104, 88))          # «снимок»-имитация
    dr = ImageDraw.Draw(im, 'RGBA')
    # сетка «улиц» для контекста
    for gx in range(0, W, 90):
        dr.line([(gx, 0), (gx, H)], fill=(120, 120, 110), width=6)
    for gy in range(0, H, 90):
        dr.line([(0, gy), (W, gy)], fill=(120, 120, 110), width=6)
    demo = [(255, 255, 255, 255), (30, 120, 60, 255), (60, 60, 70, 255)]
    dr.rectangle([0, 0, W, H], fill=(96, 108, 88, 60))
    # ЦУ/OLT крупно + ОРШ разного размера/цвета
    draw_olt_node(dr, W * 0.30, H * 0.32, 17 * S / 3.2)
    draw_orsh(dr, W * 0.62, H * 0.30, 15 * S / 3.2, (25, 113, 194), 1)
    draw_orsh(dr, W * 0.80, H * 0.30, 15 * S / 3.2, (47, 158, 68), 2)
    draw_orsh(dr, W * 0.30, H * 0.72, 15 * S / 3.2, (240, 140, 0), 3)
    draw_orsh(dr, W * 0.52, H * 0.72, 15 * S / 3.2, (156, 54, 181), 12)
    draw_olt_node(dr, W * 0.76, H * 0.74, 12 * S / 3.2)
    fr = ImageFont.truetype(_FR, 16)
    dr.text((12, H - 40), 'образцы: ЦУ·OLT (здание+антенна+бейдж OLT), ОРШ (шкаф с номером зоны)',
            font=fr, fill=(255, 255, 255))
    out = os.path.join(os.path.dirname(__file__), '..', 'work', 'symbology_preview.png')
    im.save(out)
    print('образцы ->', os.path.abspath(out))
