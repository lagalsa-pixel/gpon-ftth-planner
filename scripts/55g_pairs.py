#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55g: пары «фрагмент заказчика (4x) | кроп карты с ID» для VLM."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DIR = Path('/home/z/my-project/work/altay2')
FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)

PAIRS = {
    'img_9': ('img_9_4x.png', 'region2_img_9.jpg'),
    'img_10': ('img_10_4x.png', 'region2_img_10.jpg'),
    'img_11': ('img_11_4x.png', 'region2_img_11.jpg'),
    'img_12': ('img_12_4x.png', 'region2_img_12.jpg'),
}

for name, (fig_f, map_f) in PAIRS.items():
    fig = Image.open(DIR / fig_f).convert('RGB')
    mp = Image.open(DIR / map_f).convert('RGB')
    # нормируем высоты к 700
    H = 700
    fig = fig.resize((int(fig.width * H / fig.height), H), Image.LANCZOS)
    mp = mp.resize((int(mp.width * H / mp.height), H), Image.LANCZOS)
    W = fig.width + mp.width + 60
    canvas = Image.new('RGB', (W, H + 90), (24, 24, 24))
    canvas.paste(fig, (10, 80))
    canvas.paste(mp, (fig.width + 50, 80))
    dr = ImageDraw.Draw(canvas)
    dr.text((10, 12), 'A: фрагмент заказчика', font=FONT, fill=(255, 220, 80))
    dr.text((fig.width + 50, 12), 'B: карта с ID (посл. 3 цифры)',
            font=FONT, fill=(120, 220, 255))
    out = DIR / f'pair_{name}.jpg'
    canvas.save(out, quality=92)
    print(f'{name}: {out.name} {canvas.size}')
