#!/usr/bin/env python3
"""Task 53: NCC-верификация R5 (fig-004-004) на кадре пользователя
+ состояние сети Алтайского по ИСПРАВЛЕННЫМ регионам (v3) + кропы для VLM.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BASE = Path('/home/z/my-project')
FIGS = BASE / 'work/altay_remarks'
KEY = 'altaiskiy'
HH = 300
DOWN = 2

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M = tr['M_full']            # frame -> mosaic


def map_to_mosaic(x, y):
    fx, fy = x, y - HH
    return (M[0][0] * fx + M[0][1] * fy + M[0][2],
            M[1][0] * fx + M[1][1] * fy + M[1][2])


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


# ---------- 1) R5 NCC-верификация на кадре ----------
print('=== R5 на кадре пользователя ===')
frame_full = cv2.imread(str(BASE / 'upload/06_Алтайский_граница.jpg'),
                        cv2.IMREAD_GRAYSCALE)
frame_half = cv2.resize(frame_full, (frame_full.shape[1] // DOWN,
                                     frame_full.shape[0] // DOWN),
                        interpolation=cv2.INTER_AREA)
fig0 = cv2.imread(str(FIGS / 'fig-004-004.png'), cv2.IMREAD_GRAYSCALE)
sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.04)
k2, d2 = sift.detectAndCompute(frame_half, None)
best = None
for vname, vimg in [('raw', fig0),
                    ('rotCW', cv2.rotate(fig0, cv2.ROTATE_90_CLOCKWISE)),
                    ('rotCCW', cv2.rotate(fig0, cv2.ROTATE_90_COUNTERCLOCKWISE))]:
    h0, w0 = vimg.shape
    for s in [2.0, 1.0, 0.5]:
        fig = vimg if s == 1.0 else cv2.resize(
            vimg, (int(w0 * s), int(h0 * s)),
            interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        if min(fig.shape) < 40:
            continue
        k1, d1 = sift.detectAndCompute(fig, None)
        if d1 is None or len(k1) < 12:
            continue
        bf = cv2.BFMatcher()
        matches = bf.knnMatch(d1, d2, k=2)
        good = [m for m, n in matches if m.distance < 0.75 * n.distance]
        if len(good) < 8:
            continue
        src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if H is None or int(msk.sum()) < 8:
            continue
        inl = int(msk.sum())
        hh, ww = fig.shape
        corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                              [0, hh]]).reshape(-1, 1, 2)
        proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) * DOWN
        x0, y0 = proj.min(axis=0)
        x1, y1 = proj.max(axis=0)
        W2, H2 = frame_half.shape[1], frame_half.shape[0]
        warped_half = cv2.warpPerspective(fig, H, (W2, H2),
                                          borderMode=cv2.BORDER_CONSTANT,
                                          borderValue=128)
        wh = warped_half[int(y0) // DOWN:int(y1) // DOWN + 1,
                         int(x0) // DOWN:int(x1) // DOWN + 1]
        if wh.size < 400:
            continue
        warped = cv2.resize(wh, (max(1, wh.shape[1] * 2),
                                 max(1, wh.shape[0] * 2)))
        crop = frame_full[int(y0):int(y0) + warped.shape[0],
                          int(x0):int(x0) + warped.shape[1]]
        if crop.shape[:2] != warped.shape[:2]:
            mn = (min(crop.shape[0], warped.shape[0]),
                  min(crop.shape[1], warped.shape[1]))
            crop, warped = crop[:mn[0], :mn[1]], warped[:mn[0], :mn[1]]
        m = (warped > 5) & (warped < 250) & (crop > 5) & (crop < 250)
        if m.sum() < 400:
            continue
        sc = ncc(warped[m], crop[m])
        print(f'  {vname} s={s}: inl={inl} ncc={sc:.3f} '
              f'region=[{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}]')
        if sc >= 0.30 and (best is None or (sc, inl) > (best['ncc'],
                                                        best['inliers'])):
            best = dict(ncc=round(sc, 3), inliers=inl, region=[
                round(float(x0)), round(float(y0)),
                round(float(x1)), round(float(y1))])

r5 = None
if best:
    r5 = best
    print('R5 ВЕРИФИЦИРОВАН:', best)
    json.dump(best, open(FIGS / 'fig_R5_verified.json', 'w'), indent=1)
else:
    print('R5: не верифицирован на кадре — нужен ручной поиск')

# ---------- 2) регионы v3 ----------
V3 = json.load(open(FIGS / 'fig_match_v3.json'))
REGIONS = {}
for cap, rec in V3.items():
    if rec:
        REGIONS[cap] = tuple(rec['region'])
if r5:
    REGIONS['R5'] = tuple(r5['region'])

# ---------- 3) OSM + сеть по регионам ----------
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def geo_to_px(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
blds = []
for b in osm['buildings']:
    px, py = geo_to_px(*b['center'])
    blds.append(dict(id=b['id'], px=(px, py), area=b.get('area', 0),
                     tags=b.get('tags', {})))

net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))
drops, couplers = net['drops'], net['couplers']

state = {}
for name in ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']:
    if name not in REGIONS:
        continue
    x0, y0, x1, y1 = REGIONS[name]
    mx0, my0 = map_to_mosaic(x0, y0)
    mx1, my1 = map_to_mosaic(x1, y1)
    inb = [b for b in blds
           if mx0 - 40 <= b['px'][0] <= mx1 + 40 and my0 - 40 <= b['px'][1] <= my1 + 40]
    ind = [d for d in drops
           if mx0 <= d['poly'][-1][0] <= mx1 and my0 <= d['poly'][-1][1] <= my1]
    print(f'=== {name}: map[{x0}..{x1},{y0}..{y1}] '
          f'mosaic[{mx0:.0f}..{mx1:.0f},{my0:.0f}..{my1:.0f}] '
          f'OSM зданий {len(inb)}, дропов {len(ind)}')
    for b in sorted(inb, key=lambda b: (b['px'][1], b['px'][0])):
        print(f"   OSM id={b['id']} px=({b['px'][0]:.0f},{b['px'][1]:.0f}) "
              f"area={b['area']:.0f} tags={json.dumps(b['tags'], ensure_ascii=False)}")
    for d in ind:
        p = d['poly'][-1]
        print(f"   DROP hh_id={d['hh_id']} hh={d.get('hh')} "
              f"coupler={d.get('coupler')} дом=({p[0]:.0f},{p[1]:.0f})")
    state[name] = dict(region_map=list(REGIONS[name]),
                       region_mosaic=[round(mx0), round(my0),
                                      round(mx1), round(my1)],
                       n_osm=len(inb), n_drops=len(ind),
                       osm=[dict(id=b['id'],
                                 px=[round(b['px'][0]), round(b['px'][1])],
                                 area=b['area'], tags=b['tags']) for b in inb],
                       drops=[dict(hh_id=d['hh_id'], hh=d.get('hh'),
                                   coupler=d.get('coupler'),
                                   pt=[round(d['poly'][-1][0]),
                                       round(d['poly'][-1][1])],
                                   length_m=d['length_m']) for d in ind])

# ---------- 4) кропы карты по исправленным регионам ----------
map_img = Image.open(BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg')
frame_img = Image.open(BASE / 'upload/06_Алтайский_граница.jpg')
for name, (x0, y0, x1, y1) in REGIONS.items():
    mg = 130
    c = map_img.crop((max(0, x0 - mg), max(0, y0 - mg), x1 + mg, y1 + mg))
    c.save(FIGS / f'crop2_{name}_map.png')
    fy0 = max(0, y0 - mg - HH)
    fy1 = min(frame_img.height, y1 + mg - HH)
    c2 = frame_img.crop((max(0, x0 - mg), fy0, x1 + mg, fy1))
    c2.save(FIGS / f'crop2_{name}_frame.png')
    print(f'{name}: кропы crop2_{name}_map.png {c.size} + frame {c2.size}')

json.dump(state, open(FIGS / 'region_state_v3.json', 'w'),
          ensure_ascii=False, indent=1)
print('saved region_state_v3.json')
