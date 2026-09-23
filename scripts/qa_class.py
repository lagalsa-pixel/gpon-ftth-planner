#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA-фрагменты с цветокодированными OSM-зданиями:
зелёный = жилые по тегам/адресу, синий = yes>=45м2, серый = yes<45м2, красный = нежилые."""
import cv2, json, math, os, sys
import numpy as np

WORK = '/home/z/my-project/work'
os.makedirs(f'{WORK}/qa', exist_ok=True)

with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
    OSM = json.load(f)
with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = {s['name']: s for s in json.load(f)}

DWELL_TAGS = {'house', 'detached', 'residential', 'semidetached_house', 'bungalow', 'apartments'}
NONRES = {'garage', 'garages', 'industrial', 'school', 'church', 'barn', 'shed', 'roof',
          'construction', 'service', 'greenhouse', 'commercial', 'kiosk', 'ruins', 'farm',
          'hangar', 'warehouse', 'civic', 'public'}

def classify(b, area):
    t = b['tags'].get('building', 'yes')
    if t in NONRES: return 'nonres'
    if t in DWELL_TAGS: return 'dwell'
    if 'addr:housenumber' in b['tags']: return 'dwell'
    return 'yes_big' if area >= 45 else 'yes_small'

for name in ['Верхнеберезовка', 'Алтайский', 'Пригородное']:
    fname = [f for f in os.listdir(f'{WORK}/full') if name in f][0]
    img = cv2.imread(f'{WORK}/full/{fname}')
    H, W = img.shape[:2]
    geo = json.load(open(f'{WORK}/geo/{name}.json'))
    n = 2 ** geo['zoom']
    gx0 = geo['tx0'] * 256 + geo['px_x0']
    gy0 = geo['ty0'] * 256 + geo['px_y0']
    lat0, lon0 = SNPS[name]['lat'], SNPS[name]['lon']
    mx = 111320 * math.cos(math.radians(lat0))

    def ll_to_px(lat, lon):
        xt = (lon + 180.0) / 360.0 * n * 256.0
        lr = math.radians(lat)
        yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256.0
        return xt - gx0, yt - gy0

    recs = []
    for b in OSM[name]['buildings']:
        lats = [p[0] for p in b['geom']]; lons = [p[1] for p in b['geom']]
        area = abs((max(lons) - min(lons)) * mx * (max(lats) - min(lats)) * 111320)
        cls = classify(b, area)
        pts = np.array([ll_to_px(la, lo) for la, lo in b['geom']], np.int32)
        recs.append((pts, cls))

    # фрагменты: центр и случайная окраина
    frags = [(W // 2 - 500, H // 2 - 500), (W // 4 - 500, 3 * H // 4 - 500)]
    for fi, (fx, fy) in enumerate(frags):
        fx, fy = max(0, min(W - 1000, fx)), max(0, min(H - 1000, fy))
        crop = img[fy:fy + 1000, fx:fx + 1000].copy()
        for pts, cls in recs:
            local = pts - [fx, fy]
            if (local[:, 0].max() < -20 or local[:, 0].min() > 1020 or
                    local[:, 1].max() < -20 or local[:, 1].min() > 1020):
                continue
            color = {'dwell': (0, 255, 0), 'yes_big': (255, 180, 0),
                     'yes_small': (160, 160, 160), 'nonres': (0, 0, 255)}[cls]
            cv2.polylines(crop, [local], True, color, 3)
        out = f'{WORK}/qa/{name}_cls_{fi}.png'
        cv2.imwrite(out, crop, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        print(name, fi, out)
