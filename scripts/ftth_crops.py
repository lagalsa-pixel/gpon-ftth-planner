#!/usr/bin/env python3
"""Кропы 1:1 из полноразмерных FTTH-снимков для контроля качества VLM."""
import json, math, os, sys
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(BASE, 'ftth_out')
OUT_DIR = '/home/z/my-project/download/snp_vko_ftth'
PREV = os.path.join(OUT_DIR, 'previews')
CROPS = os.path.join(PREV, 'crops')
os.makedirs(CROPS, exist_ok=True)

Z = 18
WORLD = 2 ** Z * 256


def lon2mx(lon):
    return (lon + 180.0) / 360.0 * WORLD


def lat2my(lat):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * WORLD


def crop_around(img, cx, cy, w, h, path, q=88):
    W, H = img.size
    x0 = max(0, min(W - w, int(cx - w / 2)))
    y0 = max(0, min(H - h, int(cy - h / 2)))
    img.crop((x0, y0, x0 + w, y0 + h)).save(path, 'JPEG', quality=q)


keys = sys.argv[1:] or ['verkhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altayskiy']
for key in keys:
    d = json.load(open(os.path.join(DESIGN_DIR, f'{key}_design.json')))
    lat_min, lon_min, lat_max, lon_max = d['bbox']
    mx0, mx1 = lon2mx(lon_min), lon2mx(lon_max)
    my0, my1 = lat2my(lat_max), lat2my(lat_min)
    ox, oy = math.floor(mx0), math.floor(my0)

    def PX(lat, lon):
        return (lon2mx(lon) - ox, lat2my(lat) - oy)

    files = [f for f in os.listdir(OUT_DIR) if key[:6] in f.lower() or d['name'] in f]
    png = [f for f in os.listdir(OUT_DIR) if f.endswith('.png') and d['name'] in f][0]
    img = Image.open(os.path.join(OUT_DIR, png))
    W, H = img.size

    # 1) зона POP
    px, py = PX(d['pop']['lat'], d['pop']['lon'])
    crop_around(img, px, py, 1600, 1000, os.path.join(CROPS, f'{key}_pop.jpg'))

    # 2) плотная улица: кластер с макс. числом ДХ
    s_best = max(d['splitters'], key=lambda s: s['hh'])
    sx, sy = PX(s_best['lat'], s_best['lon'])
    crop_around(img, sx, sy, 1600, 1000, os.path.join(CROPS, f'{key}_street.jpg'))
    print(f"{key}: кропы POP ({int(px)},{int(py)}) и сплиттера {s_best['id']} ({int(sx)},{int(sy)}) из {png} {W}x{H}")
    img.close()
print('готово:', os.listdir(CROPS))
