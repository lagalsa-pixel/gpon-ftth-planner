# -*- coding: utf-8 -*-
"""
Шаг 3. Загрузка полноразмерных спутниковых мозаик ESRI z18 по финальным bbox.
Выход: download/snp_vko/<NN>_<key>_satellite.png (снимок с заголовком) + work/<key>/mosaic.jpg (для обработки).
"""
import sys, os, math, io, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, fetch_tile, lon2tx, lat2ty, tx2lon, ty2lat, load_json, save_json, DL
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

Z = 18

def mosaic_for(v, fb):
    key = v['key']
    lat_mid = (fb[1] + fb[3]) / 2
    tx0f, tx1f = lon2tx(fb[0], Z), lon2tx(fb[2], Z)
    ty0f, ty1f = lat2ty(fb[3], Z), lat2ty(fb[1], Z)   # север -> меньший y
    x0, x1 = int(math.floor(tx0f)), int(math.ceil(tx1f))
    y0, y1 = int(math.floor(ty0f)), int(math.ceil(ty1f))
    # точная привязка: левый верхний угол пикселя (x0*256, y0*256) = (tx0f-x0)*256 смещение
    offx = (tx0f - x0) * 256
    offy = (ty0f - y0) * 256
    Wpx = int(round((tx1f - tx0f) * 256))
    Hpx = int(round((ty1f - ty0f) * 256))
    tiles = [(tx, ty) for tx in range(x0, x1) for ty in range(y0, y1)]
    print(f"  {v['name']}: {x1-x0}x{y1-y0} тайлов ({len(tiles)}), мозаика {Wpx}x{Hpx}px")

    def get(t):
        tx, ty = t
        data = fetch_tile(Z, tx, ty, source='google')
        return t, data

    tilemap = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (tx, ty), data in ex.map(get, tiles):
            tilemap[(tx, ty)] = data

    canvas = np.zeros(((y1 - y0) * 256, (x1 - x0) * 256, 3), np.uint8)
    missing = 0
    for (tx, ty), data in tilemap.items():
        if data:
            im = Image.open(io.BytesIO(data)).convert('RGB')
            canvas[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = np.asarray(im)
        else:
            missing += 1
    # обрезка до точного bbox
    mos = canvas[int(offy):int(offy) + Hpx, int(offx):int(offx) + Wpx]
    if missing:
        print(f"  ! пропущено тайлов: {missing}")
    img = Image.fromarray(mos)

    # геопривязка мозаики
    mpp = 156543.03392 * math.cos(math.radians(lat_mid)) / (1 << Z)
    west = tx2lon(tx0f, Z)
    north = ty2lat(ty0f, Z)
    # заголовок с названием
    fpath = f'{vdir(key)}/mosaic.jpg'
    img.save(fpath, quality=90)

    # деливеребл: снимок с заголовочной плашкой
    HH = 96
    out = Image.new('RGB', (img.width, img.height + HH), (12, 24, 16))
    out.paste(img, (0, HH))
    dr = ImageDraw.Draw(out)
    f1 = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 40)
    f2 = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 26)
    dr.text((24, 14), f"с. {v['name']}", font=f1, fill=(235, 245, 235))
    dr.text((24, 60), f"{v['raion']} · {v['okrug']} · спутниковый снимок Google, z18, {mpp:.2f} м/px", font=f2, fill=(190, 210, 190))
    num = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altaiskiy'].index(key) + 1
    out.save(f'{DL}/{num:02d}_{key}_satellite.png')
    print(f"  сохранено: {DL}/{num:02d}_{key}_satellite.png ({img.width}x{img.height}px)")
    return dict(west=west, north=north, mpp=mpp, W=Wpx, H=Hpx, missing=missing)

if __name__ == '__main__':
    fb_all = load_json('/home/z/my-project/work/bboxes_final.json')
    geo = {}
    for v in VILLAGES:
        geo[v['key']] = mosaic_for(v, fb_all[v['key']]['bbox'])
    save_json('/home/z/my-project/work/mosaic_geo.json', geo)
    print('\nГеопривязка сохранена: work/mosaic_geo.json')
