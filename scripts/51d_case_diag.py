# -*- coding: utf-8 -*-
"""
Шаг 51d. Диагностика кейса пользователя: кроп мозаики Пригородного с маркерами ДХ,
OSM-полигонами зданий и сеткой. VLM-анализ что именно склеено.
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
import cv2
import numpy as np

BASE = '/home/z/my-project'
key = 'prigorodnoe'
geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
mpp, west, north = geo['mpp'], geo['west'], geo['north']

qm = json.load(open(f'{BASE}/work/user_img_match_verified.json'))['quad_mosaic']
qm = np.array(qm)
pad = 90
x0 = int(max(0, qm[:, 0].min() - pad)); y0 = int(max(0, qm[:, 1].min() - pad))
x1 = int(qm[:, 0].max() + pad); y1 = int(qm[:, 1].max() + pad)

mos = cv2.imread(f'{BASE}/work/{key}/mosaic.jpg')
crop = mos[y0:y1, x0:x1].copy()
UP = 4  # апскейл для VLM
crop = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_LANCZOS4)

def geo_to_px(la, lo):
    return ((lo - west) * (111320 * math.cos(math.radians(la))) / mpp,
            (north - la) * 111320 / mpp)

# OSM-здания в расширенной области
osm = json.load(open(f'{BASE}/work/{key}/osm.json'))
for b in osm['buildings']:
    pts = [geo_to_px(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
        continue
    poly = np.array([[ (p[0] - x0) * UP, (p[1] - y0) * UP ] for p in pts], dtype=np.int32)
    t = b.get('tags', {})
    lv = t.get('building:levels', '')
    cv2.polylines(crop, [poly], True, (255, 255, 0), 2)  # жёлтый контур OSM
    cx, cy = int((min(xs)+max(xs))/2 - x0) * UP, int((min(ys)+max(ys))/2 - y0) * UP
    cv2.putText(crop, f"{t.get('building','?')[:6]}{'/'+str(lv) if lv else ''}",
                (cx - 30, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA)

# ДХ
hh = json.load(open(f'{BASE}/work/{key}/households.json'))
for h in hh:
    hx, hy = h['cx'], h['cy']
    if not (x0 - 20 <= hx <= x1 + 20 and y0 - 20 <= hy <= y1 + 20):
        continue
    px, py = int((hx - x0) * UP), int((hy - y0) * UP)
    cv2.circle(crop, (px, py), 8, (0, 0, 255), 3)
    cv2.putText(crop, f"hh{h['id']}", (px + 10, py + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)

# граница области снимка пользователя
box = np.array([[(p[0] - x0) * UP, (p[1] - y0) * UP] for p in qm], dtype=np.int32)
cv2.polylines(crop, [box], True, (0, 255, 255), 3)

out = f'{BASE}/work/user_case_diag.png'
cv2.imwrite(out, crop)
print(f'{out}: {crop.shape[1]}x{crop.shape[0]}')
print(f'область снимка пользователя (жёлтый прямоугольник): {qm[:,0].max()-qm[:,0].min():.0f}x{qm[:,1].max()-qm[:,1].min():.0f} px = {(qm[:,0].max()-qm[:,0].min())*mpp:.0f}x{(qm[:,1].max()-qm[:,1].min())*mpp:.0f} м')
