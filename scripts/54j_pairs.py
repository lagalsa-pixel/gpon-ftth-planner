#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54j: сравнительные пары «эталонный барак | подозреваемый»
для финальной VLM-сверки типов зданий."""
import json
from pathlib import Path

from PIL import Image, ImageDraw

FIGS = Path('/home/z/my-project/work/altay_remarks')

# эталон: подтверждённый заказчиком жилой барак 637127280 (8 антенн,
# 14x54 м, квартиры по формуле) — t54_calib_637127280_2x.png
REF = FIGS / 't54_calib_637127280_2x.png'

SUSPECTS = [
    (637127276, 't54_audit_637127276_2x.png', '29.9x7.9 плоская, 4 крыльца, apt=T'),
    (637127283, 't54_audit_637127283_2x.png', '9.3x28.9, 4 крыльца/гараж?'),
    (759801027, 't54_audit_759801027_2x.png', '11x18.5, 2 антенны, 3 крыльца'),
    (496463521, 't54_audit_496463521_2x.png', '11x19.4, 2 крыльца, плоская'),
    (637127279, 't54_calib_637127279_2x.png', '22.1x16.1, 1 антенна, плоская'),
    (637127288, 't54_calib_637127288_2x.png', '16.2x18.2, неясно'),
    (637127289, 't54_calib_637127289_2x.png', '13.5x39.7, контроль: частный?'),
    (637127295, 't54_crop_637127295_2x.png', '36.7x40.6, lv2, 4 крыльца'),
    (496463519, 't54_audit_496463519_2x.png', '12.8x20.3, 1 антенна, конёк'),
    (759801042, 't54_audit_759801042_2x.png', '10.7x15.5, 1 антенна, плоская'),
    (759801043, 't54_audit_759801043_2x.png', '14.6x10.6, 2 антенны, конёк'),
]

ref = Image.open(REF)
print('эталон:', ref.size)

W = 760  # ширина каждой панели
for bid, fname, note in SUSPECTS:
    p = FIGS / fname
    if not p.exists():
        print(f'{bid}: нет файла {fname}')
        continue
    sus = Image.open(p)
    # нормируем высоту панелей до 560
    H = 560

    def fit(im):
        k = H / im.height
        w = int(im.width * k)
        if w > W:
            k = W / im.width
            w = W
            h = int(im.height * k)
            return im.resize((w, h), Image.LANCZOS)
        return im.resize((w, int(im.height * k)), Image.LANCZOS)

    a, b = fit(ref), fit(sus)
    canvas = Image.new('RGB', (W * 2 + 30, H + 70), (255, 255, 255))
    canvas.paste(a, (10, 50))
    canvas.paste(b, (W + 20, 50))
    d = ImageDraw.Draw(canvas)
    d.text((10, 10), 'A: ЭТАЛОН — жилой барак (квартиры, 8 ТВ-антенн)', fill=(180, 0, 0))
    d.text((W + 20, 10), f'B: здание {bid} ({note})', fill=(0, 0, 180))
    d.line([(W + 10, 0), (W + 10, H + 70)], fill=(0, 0, 0), width=3)
    out = FIGS / f't54_pair_{bid}.png'
    canvas.save(out)
    print(f'{bid}: {out.name} {canvas.size}')
