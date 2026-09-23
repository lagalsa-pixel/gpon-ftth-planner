# -*- coding: utf-8 -*-
"""Визуальная верификация детекции ДХ: оверлей маркеров на кропах мозаики."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json
from PIL import Image, ImageDraw

geo_all = load_json('/home/z/my-project/work/mosaic_geo.json')

for key, cx, cy in [('verhneberezovka', 3650, 3800), ('verhneberezovka', 1500, 6200),
                    ('solnechnoe', 3400, 3400), ('vinnoe', 3700, 4100),
                    ('altaiskiy', 3900, 5900), ('prigorodnoe', 3400, 3200)]:
    g = geo_all[key]
    hhs = load_json(f'{vdir(key)}/households.json')
    img = Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB')
    crop = img.crop((cx - 600, cy - 600, cx + 600, cy + 600)).copy()
    dr = ImageDraw.Draw(crop)
    n = 0
    for h in hhs:
        x, y = h['cx'] - (cx - 600), h['cy'] - (cy - 600)
        if -20 <= x <= 1220 and -20 <= y <= 1220:
            col = (255, 60, 60) if h['main_src'] == 'osm' else (60, 200, 255)
            dr.ellipse([x - 7, y - 7, x + 7, y + 7], outline=col, width=3)
            dr.line([x - 12, y, x + 12, y], fill=col, width=2)
            dr.line([x, y - 12, x, y + 12], fill=col, width=2)
            n += 1
    crop.save(f'work/verify_{key}_{cx}_{cy}.png')
    print(f'{key} @({cx},{cy}): {n} ДХ в кропе -> work/verify_{key}_{cx}_{cy}.png')
