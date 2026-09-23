# -*- coding: utf-8 -*-
"""Нарезка фрагментов мозаики Пригородного вокруг кандидатов ОРШ (с маркерами)."""
from PIL import Image, ImageDraw
BASE = '/home/z/my-project'
mos = Image.open(f'{BASE}/work/prigorodnoe/mosaic.jpg').convert('RGB')

# кандидаты: (id, x, y, площадь, подпись)
cands = [
    (688327498, 3161, 4405, 84,  'A'),
    (688327439, 2833, 4705, 106, 'B1'),
    (688327441, 2839, 4607, 106, 'B2'),
    (435768770, 2421, 3795, 335, 'C'),
]
R = 360  # полукадр 360 px = 137 м
dr = ImageDraw.Draw(mos)
for cid, x, y, area, lbl in cands:
    box = (max(0, x - R), max(0, y - R), min(mos.width, x + R), min(mos.height, y + R))
    crop = mos.crop(box)
    cd = ImageDraw.Draw(crop)
    cx, cy = x - box[0], y - box[1]
    # маркер: красное кольцо + крест
    for rr in (28, 34):
        cd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(255, 0, 0), width=6)
    cd.line([cx - 44, cy, cx + 44, cy], fill=(255, 0, 0), width=5)
    cd.line([cx, cy - 44, cx, cy + 44], fill=(255, 0, 0), width=5)
    crop.save(f'{BASE}/work/prigorodnoe/anchor_cand_{lbl}.png')
    print(f'{lbl} (id={cid}, {area} м²): work/prigorodnoe/anchor_cand_{lbl}.png {crop.size}')
