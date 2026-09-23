#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Определение домохозяйств (v2):
OSM-здания (теги/адрес/размер/контекст) + детекция неразмеченных крыш (tophat-блобы).
Выход: work/hh/<Имя>.json + QA-оверлеи."""
import cv2, json, math, os
import numpy as np

WORK = '/home/z/my-project/work'
os.makedirs(f'{WORK}/hh', exist_ok=True)
os.makedirs(f'{WORK}/qa', exist_ok=True)

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)
with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
    OSM = json.load(f)

DWELL_TAGS = {'house', 'detached', 'residential', 'semidetached_house', 'bungalow', 'apartments'}
# пер-поселёнческие параметры CV-детекции: (перцентиль порога, зона от дорог/зданий, м)
OVERRIDE = {'Алтайский': (30, 500, 85, 95), 'Верхнеберезовка': None}  # None = без CV
def _ov(name):
    o = OVERRIDE.get(name)
    return o if o else (25, 450, 85, 95)
NONRES_TAGS = {'garage', 'garages', 'industrial', 'school', 'church', 'barn', 'shed', 'roof',
               'construction', 'service', 'greenhouse', 'commercial', 'kiosk', 'ruins', 'farm',
               'hangar', 'warehouse', 'civic', 'public', 'hut', 'carport'}

def process(name):
    process._big_pts = None
    snp = next(s for s in SNPS if s['name'] == name)
    exp = snp['households']
    lat0, lon0 = snp['lat'], snp['lon']
    mx = 111320 * math.cos(math.radians(lat0))

    fname = [f for f in os.listdir(f'{WORK}/full') if name in f][0]
    img = cv2.imread(f'{WORK}/full/{fname}')
    H, W = img.shape[:2]
    geo = json.load(open(f'{WORK}/geo/{name}.json'))
    n = 2 ** geo['zoom']
    gx0 = geo['tx0'] * 256 + geo['px_x0']
    gy0 = geo['ty0'] * 256 + geo['px_y0']
    mpp = geo['m_per_px']

    def ll_to_px(lat, lon):
        xt = (lon + 180.0) / 360.0 * n * 256.0
        lr = math.radians(lat)
        yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256.0
        return xt - gx0, yt - gy0
    def px_to_ll(px, py):
        gxp = gx0 + px; gyp = gy0 + py
        lon = (gxp / 256.0) / n * 360.0 - 180.0
        yr = (gyp / 256.0) / n
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yr))))
        return lat, lon

    # --- 1. разбор OSM-зданий ---
    blds = []
    for b in OSM[name]['buildings']:
        lats = [p[0] for p in b['geom']]; lons = [p[1] for p in b['geom']]
        # площадь по шнэйку (shoelace) в метрах
        pts_m = [((lo - lon0) * mx, (la - lat0) * 111320) for la, lo in b['geom']]
        A = 0.0
        for i in range(len(pts_m)):
            x1, y1 = pts_m[i]; x2, y2 = pts_m[(i + 1) % len(pts_m)]
            A += x1 * y2 - x2 * y1
        area = abs(A) / 2
        cx_m = sum(p[0] for p in pts_m) / len(pts_m)
        cy_m = sum(p[1] for p in pts_m) / len(pts_m)
        px, py = ll_to_px(lats[len(lats)//2], lons[len(lons)//2])
        cx_px = sum(ll_to_px(la, lo)[0] for la, lo in b['geom']) / len(b['geom'])
        cy_px = sum(ll_to_px(la, lo)[1] for la, lo in b['geom']) / len(b['geom'])
        t = b['tags'].get('building', 'yes')
        blds.append({'id': b['id'], 'tag': t, 'area': area, 'levels': b['tags'].get('building:levels'),
                     'addr': b['tags'].get('addr:housenumber'), 'cx': cx_px, 'cy': cy_px,
                     'cx_m': cx_m, 'cy_m': cy_m, 'tag_full': b['tags']})

    # контекст жилости (пиар-правило): здания-соседи того же размерного класса
    dwells_idx = [i for i, b in enumerate(blds)
                  if b['tag'] in DWELL_TAGS or b['addr'] or b['tag'] == 'apartments']
    dpts = np.array([[blds[i]['cx_m'], blds[i]['cy_m']] for i in dwells_idx]) if dwells_idx else np.zeros((0, 2))
    peers = np.array([[b['cx_m'], b['cy_m']] for b in blds
                      if 42 <= b['area'] <= 420]) if blds else np.zeros((0, 2))

    households = []   # {x, y, lat, lon, source, units, area}
    objects = []      # нежилые значимые объекты
    for i, b in enumerate(blds):
        x, y = b['cx'], b['cy']
        la, lo = px_to_ll(x, y)
        if b['tag'] == 'apartments':
            lv = int(b['levels']) if b['levels'] and b['levels'].isdigit() else 2
            units = max(2, min(int(round(b['area'] * lv / 60)), 120))
            households.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'source': 'osm_apartments',
                               'units': units, 'area': b['area']})
        elif b['tag'] in NONRES_TAGS:
            objects.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'kind': b['tag'], 'area': b['area']})
        elif b['tag'] in DWELL_TAGS or b['addr']:
            households.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'source': 'osm_dwell',
                               'units': 1, 'area': b['area']})
        else:  # 'yes' и прочее без тега
            big_pts = getattr(process, '_big_pts', None)
            if big_pts is None:
                process._big_pts = big_pts = np.array([[bb['cx_m'], bb['cy_m']] for bb in blds
                                                       if bb['area'] > 420]) if blds else np.zeros((0, 2))
            in_farm = False
            if len(big_pts):
                d2 = (big_pts[:, 0] - b['cx_m']) ** 2 + (big_pts[:, 1] - b['cy_m']) ** 2
                in_farm = int((d2 <= 250 ** 2).sum()) >= 3
            if b['area'] > 420:
                objects.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'kind': 'big_unknown', 'area': b['area']})
            elif b['area'] >= 42:
                # контекст: >=2 соседних здания 42-420 м2 в радиусе 120 м ИЛИ жилой тег в 120 м
                ctx = False
                if len(dpts):
                    d2 = (dpts[:, 0] - b['cx_m']) ** 2 + (dpts[:, 1] - b['cy_m']) ** 2
                    ctx = bool((d2 <= 120 ** 2).any())
                if not ctx and len(peers) and not in_farm:
                    d2 = (peers[:, 0] - b['cx_m']) ** 2 + (peers[:, 1] - b['cy_m']) ** 2
                    ctx = int((d2 <= 120 ** 2).sum()) >= 3  # сам + 2 соседа
                if ctx:
                    households.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'source': 'osm_yes_ctx',
                                       'units': 1, 'area': b['area']})
                else:
                    objects.append({'x': x, 'y': y, 'lat': la, 'lon': lo, 'kind': 'yes_noctx', 'area': b['area']})
            # < 42 м2 — хозпостройка, пропускаем

    n_osm_hh = sum(h['units'] for h in households)

    # --- 2. детекция неразмеченных крыш ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (41, 41))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k)

    # маска всех OSM-зданий (расширенная на 18 м)
    allmask = np.zeros((H, W), np.uint8)
    polys = []
    for b in OSM[name]['buildings']:
        pts = np.array([ll_to_px(la, lo) for la, lo in b['geom']], np.int32)
        if len(pts) >= 3:
            polys.append(pts)
    if polys:
        cv2.fillPoly(allmask, polys, 1)
    near_mask = cv2.dilate(allmask, np.ones((int(18 / mpp) * 2, int(18 / mpp) * 2), np.uint8))

    # порог: P35 средних значений tophat внутри жилых OSM-крыш
    dm = np.zeros((H, W), np.uint8)
    dpolys = []
    for i in dwells_idx:
        b = OSM[name]['buildings']
        pass
    for b in OSM[name]['buildings']:
        t = b['tags'].get('building', 'yes')
        if t in DWELL_TAGS or b['tags'].get('addr:housenumber'):
            pts = np.array([ll_to_px(la, lo) for la, lo in b['geom']], np.int32)
            if len(pts) >= 3:
                dpolys.append(pts)
    if dpolys:
        cv2.fillPoly(dm, dpolys, 1)
    er = cv2.erode(dm, np.ones((5, 5), np.uint8))
    vals = tophat[er > 0]
    pct, zone_m, thr_min, thr_max = _ov(name)
    if OVERRIDE.get(name, 'x') is None:
        pct, zone_m, thr_min, thr_max = 25, 450, 9999, 9999  # запрет CV
    if len(vals) > 1000:
        thr = max(14, int(np.percentile(vals, pct)))
    else:
        thr = 25
    thr = max(thr_min, min(thr_max, thr))
    mask = (tophat > thr).astype(np.uint8)
    mask[near_mask > 0] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    # ограничение зоной села: 300 м от любого OSM-здания или дороги
    roadmask = np.zeros((H, W), np.uint8)
    for r in OSM[name]['roads']:
        pts = np.array([ll_to_px(la, lo) for la, lo in r['geom']], np.int32)
        cv2.polylines(roadmask, [pts], False, 1, int(max(2, 60 / mpp)))
    zone = cv2.dilate(np.maximum(allmask, roadmask), np.ones((int(zone_m / mpp) * 2, int(zone_m / mpp) * 2), np.uint8))
    mask[zone == 0] = 0

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_a, max_a = 42 / (mpp * mpp), 420 / (mpp * mpp)
    new_hh = 0
    for c in cnts:
        area_px = cv2.contourArea(c)
        if not (min_a <= area_px <= max_a):
            continue
        x, y, w, h = cv2.boundingRect(c)
        ar = max(w, h) / max(1, min(w, h))
        if ar > 4.0:
            continue
        if area_px / (w * h) < 0.5:
            continue
        hull = cv2.contourArea(cv2.convexHull(c))
        if hull == 0 or area_px / hull < 0.6:
            continue
        cx, cy = x + w / 2, y + h / 2
        la, lo = px_to_ll(cx, cy)
        households.append({'x': cx, 'y': cy, 'lat': la, 'lon': lo, 'source': 'cv_detected',
                           'units': 1, 'area': area_px * mpp * mpp})
        new_hh += 1

    # Пригородное: оставляем только основное село (без дачного массива на востоке и промзон)
    if name == 'Пригородное':
        kept = []
        for h in households:
            hx = (h['lon'] - lon0) * mx
            hy = (h['lat'] - lat0) * 111320
            if -780 <= hx <= 520 and -1550 <= hy <= 1050:
                kept.append(h)
        households[:] = kept
        objects[:] = [o for o in objects
                      if -780 <= (o['lon'] - lon0) * mx <= 520 and -1550 <= (o['lat'] - lat0) * 111320 <= 1050]

    total = sum(h['units'] for h in households)
    print(f"{name}: OSM-ДХ {n_osm_hh} + CV {new_hh} = {total} | Excel {exp} | "
          f"покрытие {total / exp * 100:.0f}% | объектов {len(objects)} | порог tophat {thr}")

    with open(f'{WORK}/hh/{name}.json', 'w', encoding='utf-8') as f:
        json.dump({'households': households, 'objects': objects, 'expected': exp,
                   'params': {'thr': thr}}, f, ensure_ascii=False)

    # QA-оверлей
    k5 = 5
    ov = cv2.resize(img, (W // k5, H // k5), interpolation=cv2.INTER_AREA)
    for h in households:
        c = {'osm_dwell': (0, 255, 0), 'osm_yes_ctx': (0, 200, 255), 'osm_apartments': (255, 0, 255),
             'cv_detected': (0, 0, 255)}[h['source']]
        cv2.circle(ov, (int(h['x'] / k5), int(h['y'] / k5)), 3, c, -1)
    cv2.imwrite(f'{WORK}/qa/{name}_hh.png', ov, [cv2.IMWRITE_PNG_COMPRESSION, 7])

for snp in SNPS:
    process(snp['name'])
