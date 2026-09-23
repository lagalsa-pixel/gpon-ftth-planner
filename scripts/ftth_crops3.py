#!/usr/bin/env python3
"""Кропы 1:1 из полноразмерных FTTH-снимков v3 для контроля качества VLM:
зона POP, самый загруженный ОРШ (проверка размещения на перекрёстке/улице),
участок с максимальной плотностью выявленных ДХ (дропы к фасадам) и зона
наибольшей плотности доп. абонентов."""
import json, math, os, sys
import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(BASE, 'ftth_out')
OUT_DIR = '/home/z/my-project/download/snp_vko_ftth_v3'
CROPS = os.path.join(OUT_DIR, 'previews', 'crops')
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


keys = sys.argv[1:] or ['verkhneberezovka', 'solnechnoe', 'perevalnoe',
                        'vinnoe', 'prigorodnoe', 'altayskiy']
for key in keys:
    d = json.load(open(os.path.join(DESIGN_DIR, f'{key}_design3.json')))
    lat_min, lon_min, lat_max, lon_max = d['bbox']
    mx0 = lon2mx(lon_min)
    my0 = lat2my(lat_max)
    ox, oy = math.floor(mx0), math.floor(my0)

    def PX(lat, lon):
        return (lon2mx(lon) - ox, lat2my(lat) - oy)

    png = [f for f in os.listdir(OUT_DIR) if f.endswith('.png') and d['name'] in f][0]
    img = Image.open(os.path.join(OUT_DIR, png))
    W, H = img.size

    # 1) зона POP
    px, py = PX(d['pop']['lat'], d['pop']['lon'])
    crop_around(img, px, py, 1600, 1000, os.path.join(CROPS, f'{key}_pop.jpg'))

    # 2) самый загруженный ОРШ
    s_best = max(d['splitters'], key=lambda s: s['hh'])
    sx, sy = PX(s_best['lat'], s_best['lon'])
    crop_around(img, sx, sy, 1600, 1000, os.path.join(CROPS, f'{key}_street.jpg'))

    # 3) максимальная плотность выявленных ДХ (дропы к фасадам)
    ident = [h for h in d['households'] if not h.get('extra')]
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(d['anchor'][0]))
    xy = np.array([[h['lat'] * ky, h['lon'] * kx] for h in ident])
    best_i, best_cnt = 0, -1
    for i in range(len(xy)):
        cnt = int((((xy - xy[i]) ** 2).sum(1) <= 120.0 ** 2).sum())
        if cnt > best_cnt:
            best_cnt, best_i = cnt, i
    fx, fy = PX(ident[best_i]['lat'], ident[best_i]['lon'])
    crop_around(img, fx, fy, 1600, 1000, os.path.join(CROPS, f'{key}_facades.jpg'))

    # 4) плотность доп. абонентов
    extras = [h for h in d['households'] if h.get('extra')]
    if extras:
        xye = np.array([[h['lat'] * ky, h['lon'] * kx] for h in extras])
        be, bcnt = 0, -1
        for i in range(len(xye)):
            cnt = int((((xye - xye[i]) ** 2).sum(1) <= 150.0 ** 2).sum())
            if cnt > bcnt:
                bcnt, be = cnt, i
        ex, ey = PX(extras[be]['lat'], extras[be]['lon'])
        crop_around(img, ex, ey, 1600, 1000, os.path.join(CROPS, f'{key}_extras.jpg'))
        print(f"{key}: POP, {s_best['id']} ({s_best['hh']} аб.), фасады ({best_cnt} ДХ/120м), "
              f"доп. абоненты ({bcnt}/150м)")
    else:
        print(f"{key}: POP, {s_best['id']} ({s_best['hh']} аб.), фасады ({best_cnt} ДХ/120м); "
              f"доп. абонентов нет")
    img.close()
print('готово:', len(os.listdir(CROPS)), 'кропов в', CROPS)
