#!/usr/bin/env python3
"""Task 53: кропы регионов замечаний из карты (с сетью) и чистого кадра."""
import json
from pathlib import Path

from PIL import Image

BASE = Path('/home/z/my-project')
FIGS = BASE / 'work/altay_remarks'

# регионы в map px (из SIFT-матчей) + название
REGIONS = {
    'R1': (983, 2867, 2137, 3115),
    'R2': (1048, 4048, 2249, 4869),
    'R3': (932, 5310, 2820, 7364),
    'R4': (1843, 2439, 2088, 2721),
    'R5': (2724, 3060, 3046, 3208),
    'R6': (273, 1806, 676, 2530),
}
MARGIN = 130
HH = 300

map_img = Image.open(BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg')
frame = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
print('map:', map_img.size, 'frame:', frame.size)

meta = {}
for name, (x0, y0, x1, y1) in REGIONS.items():
    mx0, my0 = max(0, x0 - MARGIN), max(0, y0 - MARGIN)
    mx1, my1 = x1 + MARGIN, y1 + MARGIN
    c = map_img.crop((mx0, my0, mx1, my1))
    p = FIGS / f'crop_{name}_map.png'
    c.save(p)
    # чистый кадр: те же координаты минус шапка
    fy0 = my0 - HH
    fy1 = my1 - HH
    if fy1 > 0 and fy0 < frame.height:
        c2 = frame.crop((mx0, max(0, fy0), mx1, min(frame.height, fy1)))
        c2.save(FIGS / f'crop_{name}_frame.png')
    meta[name] = dict(map_crop=[mx0, my0, mx1, my1], size=[c.width, c.height])
    print(f'{name}: map crop {c.size} -> crop_{name}_map.png '
          f'+ crop_{name}_frame.png')

json.dump(meta, open(FIGS / 'crops_meta.json', 'w'), indent=1)
