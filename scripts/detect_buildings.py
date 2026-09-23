#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Детекция зданий на снимках (v1): tophat светлых крыш + цветные крыши + контуры.
Слияние с OSM, кластеризация усадеб. Выход: work/detect/<Имя>.json + QA-оверлей."""
import cv2, json, math, os
import numpy as np

WORK = '/home/z/my-project/work'
os.makedirs(f'{WORK}/detect', exist_ok=True)
os.makedirs(f'{WORK}/qa', exist_ok=True)

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)
with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
    OSM = json.load(f)

DS = 2  # даунскейл детекции

def geo_transform(geo):
    """пиксели полного изображения -> lat/lon"""
    n = 2 ** geo['zoom']
    def px_to_ll(px, py):
        gxp = geo['tx0'] * 256 + geo['px_x0'] + px
        gyp = geo['ty0'] * 256 + geo['px_y0'] + py
        lon = (gxp / 256.0) / n * 360.0 - 180.0
        yr = (gyp / 256.0) / n
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yr))))
        return lat, lon
    return px_to_ll

def detect_buildings(img, thr_scale=1.0):
    """img: BGR full-res. Возвращает список (x, y, w, h, cx, cy, area) в полных px."""
    H, W = img.shape[:2]
    small = cv2.resize(img, (W // DS, H // DS), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    hue = hsv[:, :, 0].astype(np.int16)

    # 1) светлые крыши: tophat
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k)
    # авто-порог
    th = max(12, int(np.percentile(tophat[tophat > 3], 75) * thr_scale)) if (tophat > 3).any() else 20
    bright = (tophat > th).astype(np.uint8)

    # 2) цветные крыши: насыщенные синие/красные пиксели
    blue = ((hue >= 90) & (hue <= 130) & (sat > 65) & (val > 90)).astype(np.uint8)
    red = (((hue <= 12) | (hue >= 168)) & (sat > 65) & (val > 90)).astype(np.uint8)
    colored = cv2.bitwise_or(blue, red)

    mask = cv2.bitwise_or(bright, colored)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        a_full = area * DS * DS
        if not (150 <= a_full <= 3200):
            continue
        ar = max(w, h) / max(1, min(w, h))
        if ar > 4.2:
            continue
        hull_area = cv2.contourArea(cv2.convexHull(c))
        solidity = area / max(1, hull_area)
        if solidity < 0.55:
            continue
        out.append({'x': x * DS, 'y': y * DS, 'w': w * DS, 'h': h * DS,
                    'cx': (x + w / 2) * DS, 'cy': (y + h / 2) * DS, 'area': a_full})
    return out, th

def rasterize_osm(osm_blds, geo, W, H):
    """маска зданий OSM в координатах полного изображения"""
    mask = np.zeros((H // DS, W // DS), np.uint8)
    n = 2 ** geo['zoom']
    gx0 = geo['tx0'] * 256 + geo['px_x0']
    gy0 = geo['ty0'] * 256 + geo['px_y0']
    def ll_to_px(lat, lon):
        xt = (lon + 180.0) / 360.0 * n * 256.0
        lr = math.radians(lat)
        yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256.0
        return xt - gx0, yt - gy0
    polys = []
    for b in osm_blds:
        pts = [ll_to_px(lat, lon) for lat, lon in b['geom']]
        if len(pts) < 3:
            continue
        pts_ds = np.array([[int(px / DS), int(py / DS)] for px, py in pts], np.int32)
        polys.append(pts_ds)
    cv2.fillPoly(mask, polys, 1)
    return mask

for snp in SNPS:
    name = snp['name']
    fname = [f for f in os.listdir(f'{WORK}/full') if name in f][0]
    img = cv2.imread(f'{WORK}/full/{fname}')
    H, W = img.shape[:2]
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        geo = json.load(f)

    det, th = detect_buildings(img)
    osm_mask = rasterize_osm(OSM[name]['buildings'], geo, W, H)

    # дедупликация: CV-объект, пересекающийся с OSM-зданием -> помечен
    kept, dup = [], 0
    for d in det:
        x0, y0 = int(d['x'] / DS), int(d['y'] / DS)
        x1, y1 = int((d['x'] + d['w']) / DS), int((d['y'] + d['h']) / DS)
        sub = osm_mask[max(0, y0):y1, max(0, x0):x1]
        if sub.size and sub.mean() > 0.25:
            dup += 1
            continue
        kept.append(d)

    # кластеризация усадеб: связность через расстояние <= 38 м
    R = 38 / geo['m_per_px']
    pts = np.array([[d['cx'], d['cy']] for d in kept], np.float32)
    n_b = len(kept)
    visited = [False] * n_b
    clusters = []
    for i in range(n_b):
        if visited[i]:
            continue
        stack, comp = [i], []
        visited[i] = True
        while stack:
            j = stack.pop()
            comp.append(j)
            d2 = ((pts[stack and j or j][0] - pts[:, 0]) ** 2 + (pts[j][1] - pts[:, 1]) ** 2)
            near = np.where((d2 <= R * R) & (~np.array(visited)))[0]
            for q in near:
                visited[q] = True
                stack.append(q)
        clusters.append(comp)

    # усадьба: самое большое здание = жилой дом
    households = []
    for comp in clusters:
        best = max(comp, key=lambda j: kept[j]['area'])
        households.append({'cx': kept[best]['cx'], 'cy': kept[best]['cy'],
                           'area': kept[best]['area'], 'n_bld': len(comp)})

    px_to_ll = geo_transform(geo)
    for hh in households:
        hh['lat'], hh['lon'] = px_to_ll(hh['cx'], hh['cy'])

    exp = snp['households']
    print(f"{name}: CV {len(det)} (порог {th}), дублей с OSM {dup}, новых {len(kept)}, "
          f"усадеб {len(households)} | OSM {len(OSM[name]['buildings'])} | Excel {exp}")

    with open(f'{WORK}/detect/{name}.json', 'w', encoding='utf-8') as f:
        json.dump({'detected': kept, 'households': households,
                   'params': {'thr': th, 'R_m': 38}}, f, ensure_ascii=False)

    # QA: оверлей на 5x даунскейле
    k5 = 5
    ov = cv2.resize(img, (W // k5, H // k5), interpolation=cv2.INTER_AREA)
    for d in kept:
        cv2.rectangle(ov, (int(d['x']/k5), int(d['y']/k5)),
                      (int((d['x']+d['w'])/k5), int((d['y']+d['h'])/k5)), (0, 0, 255), 1)
    for hh in households:
        cv2.circle(ov, (int(hh['cx']/k5), int(hh['cy']/k5)), 4, (0, 255, 255), -1)
    cv2.imwrite(f'{WORK}/qa/{name}_detect.png', ov, [cv2.IMWRITE_PNG_COMPRESSION, 7])
