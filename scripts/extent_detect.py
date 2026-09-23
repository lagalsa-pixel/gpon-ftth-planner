#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Определение протяжённости застройки по текстурному анализу (v2).
Выход: work/extent/<Имя>.json (bbox застройки + 300 м буфер)"""
import cv2, json, math, os
import numpy as np

WORK = '/home/z/my-project/work'
os.makedirs(f'{WORK}/extent', exist_ok=True)
BUFFER_M = 300
CELL = 48      # ячейка в даунскейле (4x) => 48*4*0.382 ≈ 73 м
K = 4

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

def grid_mask(small):
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    hue = hsv[:, :, 0].astype(np.float32)
    h, w = g.shape
    gh, gw = h // CELL, w // CELL
    mask = np.zeros((gh, gw), dtype=np.uint8)
    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3))
    for i in range(gh):
        for j in range(gw):
            y0, x0 = i * CELL, j * CELL
            lg = lap[y0:y0+CELL, x0:x0+CELL]
            gr = g[y0:y0+CELL, x0:x0+CELL]
            st = sat[y0:y0+CELL, x0:x0+CELL]
            hu = hue[y0:y0+CELL, x0:x0+CELL]
            edge_frac = (lg > 22).mean()
            std = gr.std()
            # застройка: плотные контуры + разброс яркости; поля однообразны
            # крыши дают цветовое разнообразие
            colorful = (st > 60).mean()
            if edge_frac > 0.10 and std > 20:
                mask[i, j] = 1
    return mask

for snp in SNPS:
    name = snp['name']
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        geo = json.load(f)
    fname = [f for f in os.listdir(f'{WORK}/full') if name in f][0]
    img = cv2.imread(f'{WORK}/full/{fname}')
    H, W = img.shape[:2]
    small = cv2.resize(img, (W // K, H // K), interpolation=cv2.INTER_AREA)

    mask = grid_mask(small)
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    num, lbl, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
    cx_img, cy_img = (W // K) / CELL / 2, (H // K) / CELL / 2
    keep = np.zeros_like(m)
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        ccx, ccy = cent[i]
        if math.hypot(ccx - cx_img, ccy - cy_img) < 0.45 * max(W // K, H // K) / CELL or area > 350:
            keep[lbl == i] = 1

    ys, xs = np.where(keep > 0)
    if len(xs) == 0:
        print(f"{name}: застройка не найдена!")
        continue

    # ячейки -> полные пиксели
    x0p, x1p = xs.min() * CELL * K, (xs.max() + 1) * CELL * K
    y0p, y1p = ys.min() * CELL * K, (ys.max() + 1) * CELL * K
    x0p, x1p = max(0, x0p), min(W, x1p)
    y0p, y1p = max(0, y0p), min(H, y1p)
    cov = keep.sum() / keep.size

    def px_to_lon(px):
        n = 2 ** geo['zoom']
        gxp = geo['tx0'] * 256 + geo['px_x0'] + px
        return (gxp / 256.0) / n * 360.0 - 180.0
    def px_to_lat(py):
        n = 2 ** geo['zoom']
        gyp = geo['ty0'] * 256 + geo['px_y0'] + py
        yr = (gyp / 256.0) / n
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yr))))

    lat_max_b, lat_min_b = px_to_lat(y0p), px_to_lat(y1p)
    lon_min_b, lon_max_b = px_to_lon(x0p), px_to_lon(x1p)

    dlat = BUFFER_M / 111320
    dlon = BUFFER_M / (111320 * math.cos(math.radians(snp['lat'])))
    ext = {'lat_min': lat_min_b - dlat, 'lat_max': lat_max_b + dlat,
           'lon_min': lon_min_b - dlon, 'lon_max': lon_max_b + dlon,
           'lat_min_bare': lat_min_b, 'lat_max_bare': lat_max_b,
           'lon_min_bare': lon_min_b, 'lon_max_bare': lon_max_b}

    clipped = []
    if lat_min_b <= geo['lat_min'] + 2 * dlat: clipped.append('юг')
    if lat_max_b >= geo['lat_max'] - 2 * dlat: clipped.append('север')
    if lon_min_b <= geo['lon_min'] + 2 * dlon: clipped.append('запад')
    if lon_max_b >= geo['lon_max'] - 2 * dlon: clipped.append('восток')

    ext_w = (x1p - x0p) * geo['m_per_px'] / 1000
    ext_h = (y1p - y0p) * geo['m_per_px'] / 1000
    print(f"{name}: застройка {ext_w:.1f} x {ext_h:.1f} км, покрытие {cov:.1%}, "
          f"клиппинг: {clipped if clipped else 'нет'}")
    with open(f'{WORK}/extent/{name}.json', 'w', encoding='utf-8') as f:
        json.dump(ext, f, ensure_ascii=False, indent=1)
