#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ признаков: OSM-здания (эталон) vs фон. Калибровка CV-детектора."""
import cv2, json, math, os
import numpy as np

WORK = '/home/z/my-project/work'

def get_geo(name):
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        return json.load(f)

def osm_mask(name, geo, W, H, dilate=0):
    with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
        osm = json.load(f)[name]
    mask = np.zeros((H, W), np.uint8)
    n = 2 ** geo['zoom']
    gx0 = geo['tx0'] * 256 + geo['px_x0']
    gy0 = geo['ty0'] * 256 + geo['px_y0']
    def ll_to_px(lat, lon):
        xt = (lon + 180.0) / 360.0 * n * 256.0
        lr = math.radians(lat)
        yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256.0
        return xt - gx0, yt - gy0
    polys = []
    for b in osm['buildings']:
        pts = [ll_to_px(lat, lon) for lat, lon in b['geom']]
        if len(pts) >= 3:
            polys.append(np.array(pts, np.int32))
    if polys:
        cv2.fillPoly(mask, polys, 1)
    if dilate:
        mask = cv2.dilate(mask, np.ones((dilate, dilate), np.uint8))
    return mask

for name in ['Верхнеберезовка', 'Алтайский', 'Пригородное']:
    fname = [f for f in os.listdir(f'{WORK}/full') if name in f][0]
    img = cv2.imread(f'{WORK}/full/{fname}')
    H, W = img.shape[:2]
    geo = get_geo(name)

    pm = osm_mask(name, geo, W, H, dilate=7) > 0
    bg = cv2.dilate(osm_mask(name, geo, W, H), np.ones((301, 301), np.uint8)) == 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat, val = hsv[:, :, 1].astype(np.float32), hsv[:, :, 2].astype(np.float32)

    feats = {}
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
    feats['tophat31'] = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k).astype(np.float32)
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (61, 61))
    feats['tophat61'] = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k2).astype(np.float32)
    feats['sat'] = sat
    feats['val'] = val

    print(f"\n=== {name} (OSM зданий: {json.load(open(f'{WORK}/osm_data.json'))[name]['buildings'].__len__()}) ===")
    print(f"{'признак':10s} | {'эталон P10/P50/P90':>24s} | {'фон P50/P90/P99':>20s}")
    for fn, fv in feats.items():
        p = fv[pm]; b = fv[bg]
        print(f"{fn:10s} | {np.percentile(p,10):6.0f} {np.percentile(p,50):6.0f} {np.percentile(p,90):6.0f} | "
              f"{np.percentile(b,50):6.0f} {np.percentile(b,90):6.0f} {np.percentile(b,99):6.0f}")
    print(f"покрытие: эталон {pm.mean():.3%}, фон {bg.mean():.3%}")
