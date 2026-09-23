# -*- coding: utf-8 -*-
"""
Шаг 2. Обзорные снимки ESRI z15 (охват ~5.5 км) для каждого села + CV-детекция застройки.
Сохраняет: work/overview_<key>.png (снимок), work/overview_<key>_mask.png (маска застройки).
"""
import sys, os, math, io
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, fetch_tile, lon2tx, lat2ty, tx2lon, ty2lat, save_json
import numpy as np
from PIL import Image
import cv2

Z = 15
SIDE_M = 5600.0  # сторона обзора, м

def build_overview(v):
    key = v['key']
    lat, lon = v['lat'], v['lon']
    mpp = 156543.03392 * math.cos(math.radians(lat)) / (1 << Z)
    n_tiles = int(math.ceil(SIDE_M / mpp / 256 / 2)) + 1  # полуширина в тайлах
    ctx, cty = lon2tx(lon, Z), lat2ty(lat, Z)
    x0, x1 = int(ctx) - n_tiles, int(ctx) + n_tiles + 1
    y0, y1 = int(cty) - n_tiles, int(cty) + n_tiles + 1
    W = (x1 - x0) * 256; H = (y1 - y0) * 256
    canvas = np.zeros((H, W, 3), np.uint8)
    for tx in range(x0, x1):
        for ty in range(y0, y1):
            data = fetch_tile(Z, tx, ty)
            if data:
                im = Image.open(io.BytesIO(data)).convert('RGB')
                canvas[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = np.asarray(im)
    img = Image.fromarray(canvas)
    img.save(f'{vdir(key)}/overview.png')
    # геопривязка обзора: пиксель -> geo
    west, north = tx2lon(x0, Z), ty2lat(y0, Z)
    east, south = tx2lon(x1, Z), ty2lat(y1, Z)
    ov_mpp = (east - west) * 111320 * math.cos(math.radians(lat)) / W
    print(f"{v['name']}: обзор {W}x{H}px, {ov_mpp:.2f} м/px, гео: {west:.4f},{south:.4f} - {east:.4f},{north:.4f}")
    return dict(west=west, east=east, north=north, south=south, W=W, H=H, ov_mpp=ov_mpp)

def detect_builtup(v, geo):
    """CV-детекция застройки на обзоре: светлые крыши + серая дорожная сеть."""
    key = v['key']
    img = np.asarray(Image.open(f'{vdir(key)}/overview.png').convert('RGB'))
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    h, s, val = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    H_, W_ = img.shape[:2]
    # 1) светлые пиксели (крыши, грунт у домов) — но не слишком, чтобы не хватать голые поля
    bright = (val > 95) & (s < 130)
    # 2) серые/тёмно-серые (дороги, асфальт) — низкая насыщенность, средняя яркость
    grayish = (s < 60) & (val > 70) & (val < 200)
    # 3) цветные крыши (синие/красные/оранжевые)
    colored = (s > 90) & (val > 90) & ((h < 12) | (h > 160) | ((h > 90) & (h < 130)))
    cand = (bright & (val > 130)) | grayish | colored
    # морфологическое закрытие (склейка дворов) ~18 м
    k = max(3, int(18 / geo['ov_mpp']) | 1)
    m = cv2.morphologyEx((cand * 255).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    # сетка ~60 м; ячейка застроена если плотность cand > 0.35
    cell = max(2, int(60 / geo['ov_mpp']))
    gh, gw = H_ // cell, W_ // cell
    dens = np.zeros((gh, gw), np.float32)
    cm = (cand.astype(np.float32))
    for i in range(gh):
        for j in range(gw):
            dens[i, j] = cm[i*cell:(i+1)*cell, j*cell:(j+1)*cell].mean()
    built = dens > 0.33
    # связная компонента, содержащая центр села
    n, lab, stats, cent = cv2.connectedComponentsWithStats((built * 255).astype(np.uint8), connectivity=8)
    # центр в координатах сетки
    cxg = (v['lat'] - geo['south']) / (geo['north'] - geo['south']) * gh
    cyg = (v['lon'] - geo['west']) / (geo['east'] - geo['west']) * gw
    # ищем компоненту с максимумом (размер * близость к центру)
    best, best_score = 0, -1
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        cy, cx = cent[i]
        d = math.hypot(cx - cxg, cy - cyg)
        score = area / (1 + d / 6)
        if score > best_score:
            best_score, best = score, i
    comp = (lab == best)
    # bbox компоненты в пикселях
    ys, xs = np.where(comp)
    if len(ys) == 0:
        print(f"{v['name']}: застройка не найдена!")
        return None
    # гео-bbox + 300 м
    mpp = geo['ov_mpp']
    lat_min = geo['north'] - (ys.max() + 1) * cell * mpp / 111320 - 300 / 111320
    lat_max = geo['north'] - ys.min() * cell * mpp / 111320 + 300 / 111320
    lon_min = geo['west'] + xs.min() * cell * mpp / (111320 * math.cos(math.radians(v['lat']))) - 300 / (111320 * math.cos(math.radians(v['lat'])))
    lon_max = geo['west'] + (xs.max() + 1) * cell * mpp / (111320 * math.cos(math.radians(v['lat']))) + 300 / (111320 * math.cos(math.radians(v['lat'])))
    # визуализация маски
    vis = img.copy()
    mask_full = cv2.resize((comp * 255).astype(np.uint8), (W_, H_), interpolation=cv2.INTER_NEAREST) > 0
    overlay = np.zeros_like(img)
    overlay[mask_full] = (0, 200, 120)
    vis = cv2.addWeighted(img, 0.65, overlay, 0.35, 0)
    cv2.rectangle(vis, (xs.min()*cell, ys.min()*cell), (xs.max()*cell, ys.max()*cell), (255, 230, 0), 4)
    # OSM-здания поверх для сравнения
    Image.fromarray(vis).save(f'{vdir(key)}/overview_mask.png')
    w_km = (lon_max - lon_min) * 111320 * math.cos(math.radians(v['lat'])) / 1000
    h_km = (lat_max - lat_min) * 111320 / 1000
    print(f"  CV-bbox застройки: {lon_min:.4f},{lat_min:.4f} - {lon_max:.4f},{lat_max:.4f} ({w_km:.2f} x {h_km:.2f} км)")
    return [lon_min, lat_min, lon_max, lat_max]

if __name__ == '__main__':
    results = {}
    for v in VILLAGES:
        geo = build_overview(v)
        bbox = detect_builtup(v, geo)
        results[v['key']] = dict(geo=geo, cv_bbox=bbox)
    save_json('/home/z/my-project/work/overview_geo.json', results)
