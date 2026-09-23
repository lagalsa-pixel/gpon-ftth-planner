#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка тайлов в полноразмерный PNG по каждому СНП.
Кроп по застройке (bbox из OSM зданий + буфер 300 м), если задан extent-файл;
иначе полный охват. Выход: download/snp_vko/<NN>_<имя>.png + work/geo/<имя>_final.json"""
import json, os, sys, math
import numpy as np
import cv2

WORK = '/home/z/my-project/work'
OUT_DIR = '/home/z/my-project/work/full'
os.makedirs(OUT_DIR, exist_ok=True)

BUFFER_M = 300.0

ORDER_NUM = {}

def load_geo(name):
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        return json.load(f)

def build(name, extent=None):
    geo = load_geo(name)
    z, tx0, ty0 = geo['zoom'], geo['tx0'], geo['ty0']
    cache = f'{WORK}/tiles/{name}'

    # полный охват в пикселях результата
    W_full, H_full = geo['W'], geo['H']

    # кроп в пикселях
    if extent is not None:
        # extent = (lat_min, lat_max, lon_min, lon_max) локальной застройки
        lat_min_e, lat_max_e, lon_min_e, lon_max_e = extent
        # переведём через углы изображения
        lat_max_img, lon_min_img = geo['lat_max'], geo['lon_min']
        lat_min_img, lon_max_img = geo['lat_min'], geo['lon_max']
        # Web Mercator линейна по lon, нелинейна по lat — используем mercator y
        def lat_to_y(lat):
            n = 2 ** z
            yr = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0
            return (yr * n - ty0) * 256 - geo['px_y0']
        def lon_to_x(lon):
            n = 2 ** z
            xr = (lon + 180.0) / 360.0 * n
            return (xr * n - tx0) * 256 - geo['px_x0']
        x0 = max(0, int(math.floor(lon_to_x(lon_min_e))))
        x1 = min(W_full, int(math.ceil(lon_to_x(lon_max_e))))
        y0 = max(0, int(math.floor(lat_to_y(lat_max_e))))
        y1 = min(H_full, int(math.ceil(lat_to_y(lat_min_e))))
    else:
        x0, y0, x1, y1 = 0, 0, W_full, H_full

    Wc, Hc = x1 - x0, y1 - y0
    print(f"  {name}: кроп {Wc}x{Hc} px из {W_full}x{H_full}", flush=True)

    canvas = np.zeros((Hc, Wc, 3), dtype=np.uint8)
    # глобальные пиксели (в тайловой системе) начала канвы
    gx0 = geo['tx0'] * 256 + geo['px_x0'] + x0
    gy0 = geo['ty0'] * 256 + geo['px_y0'] + y0
    tx_first, ty_first = gx0 // 256, gy0 // 256
    tx_last, ty_last = (gx0 + Wc - 1) // 256, (gy0 + Hc - 1) // 256

    missing = 0
    for ty in range(ty_first, ty_last + 1):
        for tx in range(tx_first, tx_last + 1):
            p = f'{cache}/{z}_{tx}_{ty}.jpg'
            gx_tile, gy_tile = tx * 256, ty * 256
            dst_x0 = gx_tile - gx0; dst_y0 = gy_tile - gy0
            if not os.path.exists(p):
                missing += 1
                continue
            img = cv2.imread(p, cv2.IMREAD_COLOR)
            if img is None:
                missing += 1
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # пересечение тайла с канвой
            sx0 = max(0, -dst_x0); sy0 = max(0, -dst_y0)
            dx0 = max(0, dst_x0); dy0 = max(0, dst_y0)
            w = min(256 - sx0, Wc - dx0); h = min(256 - sy0, Hc - dy0)
            if w <= 0 or h <= 0:
                continue
            canvas[dy0:dy0+h, dx0:dx0+w] = img[sy0:sy0+h, sx0:sx0+w]
    if missing:
        print(f"  ! пропущено тайлов: {missing}", flush=True)

    # точные геограницы кропа
    def x_to_lon(x):
        n = 2 ** z
        return ((gx0 + x) / 256.0 + tx0 * 0) / n * 360.0 - 180.0 if False else \
               (((x + gx0) / 256.0) / n * 360.0 - 180.0)
    def y_to_lat(y):
        n = 2 ** z
        yr = ((y + gy0) / 256.0) / n
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yr))))

    lat_max_c = y_to_lat(0)
    lat_min_c = y_to_lat(Hc)
    lon_min_c = x_to_lon(0)
    lon_max_c = x_to_lon(Wc)

    num = ORDER_NUM.get(name, 99)
    fname = f"{num:02d}_{name.replace(' ', '_')}.png"
    out_path = f'{OUT_DIR}/{fname}'
    cv2.imwrite(out_path, cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 6])
    sz = os.path.getsize(out_path) / 1e6
    print(f"  => {out_path} ({sz:.1f} МБ)", flush=True)

    final_geo = dict(geo)
    final_geo.update({'W': Wc, 'H': Hc, 'lat_max': lat_max_c, 'lat_min': lat_min_c,
                      'lon_min': lon_min_c, 'lon_max': lon_max_c, 'file': fname})
    with open(f'{WORK}/geo/{name}_final.json', 'w', encoding='utf-8') as f:
        json.dump(final_geo, f, ensure_ascii=False, indent=1)
    return out_path

if __name__ == '__main__':
    with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
        snps = json.load(f)
    # порядок как в Excel: назначаем номера по снп
    order = {s['name']: i + 1 for i, s in enumerate(snps)}
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for i, s in enumerate(snps):
        ORDER_NUM[s['name']] = i + 1
    for s in snps:
        n = s['name']
        if only and n not in only:
            continue
        ext = None
        ef = f'{WORK}/extent/{n}.json'
        if os.path.exists(ef):
            with open(ef, encoding='utf-8') as f:
                ext = json.load(f)
            ext = (ext['lat_min'], ext['lat_max'], ext['lon_min'], ext['lon_max'])
        # временно: очистим нумерацию — файлы уже могут быть
        build(n, ext)
    print("ГОТОВО")
