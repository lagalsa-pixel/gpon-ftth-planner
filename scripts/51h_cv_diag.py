#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""51h: диагностика CV-детекции крыш на мозаике Топольного (Task 51).

1) detect_roofs как есть -> классификация кандидатов по цветовому каналу;
2) для зелёных: круглость (circ=4πA/P²), extent, вариация яркости;
3) HSV-статистика по ОСМ-зданиям (эталонные дома) — как выглядит шифер;
4) коллаж подозрительных на деревья кандидатов + коллаж домов.
"""
import json, math, os, sys
import numpy as np
import cv2

sys.path.insert(0, '/home/z/my-project/download/ftth_pipeline')
import ftth_pipeline as fp
from PIL import Image

vd = '/home/z/my-project/work/topolnoe_test/work/topolnoe'
geo = json.load(open(f'{vd}/geo.json'))
mpp = geo['mpp']
mos = np.asarray(Image.open(f'{vd}/mosaic.jpg').convert('RGB'))

# --- 1) текущий детектор + классификация по каналу -------------------------
hsv = cv2.cvtColor(mos, cv2.COLOR_RGB2HSV)
h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
masks = {
    'blue': (h >= 90) & (h <= 132) & (s > 65) & (v > 50),
    'red': ((h <= 12) | (h >= 168)) & (s > 75) & (v > 55),
    'orange': (h >= 13) & (h <= 35) & (s > 85) & (v > 95),
    'green': (h >= 40) & (h <= 85) & (s > 65) & (v > 50),
    'gray': (s < 50) & (v > 140) & (v < 248),
}
comb = np.zeros(mos.shape[:2], np.uint8)
for k, m in masks.items():
    comb |= (m * 255).astype(np.uint8)
m = cv2.morphologyEx(comb, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

cands = []
for c in cnts:
    a = cv2.contourArea(c)
    if a < 280 or a > 2400:
        continue
    x, y, w_, h_ = cv2.boundingRect(c)
    if w_ < 10 or h_ < 10:
        continue
    if a / (w_ * h_) < 0.5 or max(w_, h_) / max(1, min(w_, h_)) > 4.0:
        continue
    # цветовой канал: какой маске принадлежит центральная часть
    cx, cy = x + w_ / 2, y + h_ / 2
    mm = masks['green'][y:y + h_, x:x + w_]
    frac_green = mm.mean()
    is_green = frac_green > 0.5
    P = cv2.arcLength(c, True)
    circ = 4 * math.pi * a / max(P * P, 1e-9)
    extent = a / (w_ * h_)
    # вариация яркости внутри контура
    mask_c = np.zeros(mos.shape[:2], np.uint8)
    cv2.drawContours(mask_c, [c], -1, 255, -1)
    vals = v[y:y + h_, x:x + w_][mm > 0] if is_green else v[y:y + h_, x:x + w_][mask_c[y:y + h_, x:x + w_] > 0]
    vstd = float(np.std(vals)) if len(vals) > 5 else -1
    cands.append(dict(cx=cx, cy=cy, w=w_, h=h_, area=a, green=is_green,
                      circ=circ, extent=extent, vstd=vstd, contour=c))
green = [c for c in cands if c['green']]
print(f'кандидатов всего: {len(cands)} | зелёных: {len(green)} | прочих: {len(cands)-len(green)}')
round_green = [c for c in green if c['circ'] > 0.82]
print(f'зелёных с круглостью > 0.82 (деревья?): {len(round_green)}')
for c in sorted(round_green, key=lambda c: -c['circ'])[:10]:
    print(f"  ({c['cx']:.0f},{c['cy']:.0f}) {c['w']}x{c['h']} circ={c['circ']:.2f} "
          f"ext={c['extent']:.2f} vstd={c['vstd']:.0f}")

# --- 2) HSV домов по OSM (что такое шифер в числах) -------------------------
osm = json.load(open(f'{vd}/osm.json'))
geo_d = geo
west, north = geo['west'], geo['north']
blds = osm['buildings']
gray_houses = []
all_h = []
for b in blds[:400]:
    pts = [fp.geo_to_px(la, lo, west, north, mpp) for la, lo in b['poly']]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1 = int(min(xs)), int(max(xs)); y0, y1 = int(min(ys)), int(max(ys))
    if x1 - x0 < 6 or y1 - y0 < 6 or x0 < 0 or y0 < 0 or x1 >= mos.shape[1] or y1 >= mos.shape[0]:
        continue
    patch_h = h[y0:y1, x0:x1]; patch_s = s[y0:y1, x0:x1]; patch_v = v[y0:y1, x0:x1]
    all_h.append((np.median(patch_h), np.median(patch_s), np.median(patch_v),
                  (x0, y0, x1, y1)))
# серые дома: s < 60
gray_houses = [t for t in all_h if t[1] < 60]
print(f'OSM-зданий в кадре мозаики: {len(all_h)} | с s<60 (серо-шиферные): {len(gray_houses)}')
if gray_houses:
    vs = [t[2] for t in gray_houses]
    ss = [t[1] for t in gray_houses]
    print(f'  шифер: v медианы {min(vs):.0f}..{max(vs):.0f} (медиана {np.median(vs):.0f}), '
          f's {min(ss):.0f}..{max(ss):.0f}')
    how_many_in_current_gray = sum(1 for t in gray_houses if t[2] > 140)
    how_many_in_extended = sum(1 for t in gray_houses if t[2] > 110)
    print(f'  попадают в текущую маску gray (v>140): {how_many_in_current_gray}/{len(gray_houses)}')
    print(f'  попадут при v>110: {how_many_in_extended}/{len(gray_houses)}')

# --- 3) коллажи --------------------------------------------------------------
QAD = '/home/z/my-project/work/qa/task51'
os.makedirs(QAD, exist_ok=True)
def collage(items, name, sz=96):
    tile = Image.new('RGB', (sz * 6, sz * 2), (20, 20, 20))
    for i, it in enumerate(items[:12]):
        x0 = int(it['cx'] - sz / 2); y0 = int(it['cy'] - sz / 2)
        x0 = max(0, min(mos.shape[1] - sz, x0)); y0 = max(0, min(mos.shape[0] - sz, y0))
        c = Image.fromarray(mos[y0:y0 + sz, x0:x0 + sz])
        tile.paste(c, ((i % 6) * sz, (i // 6) * sz))
    tile.save(f'{QAD}/{name}')
    print('коллаж:', f'{QAD}/{name}')
collage(sorted(round_green, key=lambda c: -c['circ']), 'cv_trees_suspect.png')
collage([dict(cx=(t[3][0]+t[3][2])/2, cy=(t[3][1]+t[3][3])/2) for t in gray_houses],
        'cv_slate_houses.png')
