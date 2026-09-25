#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60g: фактический цвет квадрата каждого дропа Алтайского — прямо
с карты 06 v8 (пиксель в позиции конца дропа + сдвиг шапки +300).
Это ground truth зон: никакой репликации логики. Далее — фильтр по
отпечатку скриншота altay3 (квадрат ЗОНЫ-1 синий, муфта севернее,
дроп ~8-24 м, терминальная муфта, здание рядом)."""
import json, math
import cv2
import numpy as np

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
HH = 300
PALETTE = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
           (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
           (160, 90, 44)]
CU = (224, 49, 49)

tr = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
Mi = tr['M_inv']
M_fwd = tr['M_full']


def m2map(x, y):
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2] + HH)


def map2m(x, y):
    yy = y - HH
    return (M_fwd[0][0] * x + M_fwd[0][1] * yy + M_fwd[0][2],
            M_fwd[1][0] * x + M_fwd[1][1] * yy + M_fwd[1][2])


net = json.load(open(f'{BASE}/work/{KEY}/network_hh3.json'))
img = cv2.imread(MAP)

# МЖД-скрытые
hidden = set()
mg = json.load(open(f'{BASE}/work/{KEY}/mzd_groups.json'))
for g in mg:
    if g.get('kind') == 'apartment':
        hidden.update(g['hh_ids'])

res = {}
for d in net['drops']:
    ex, ey = d['poly'][-1]
    mx, my = m2map(ex, ey)
    mx, my = int(round(mx)), int(round(my))
    if not (2 <= mx < img.shape[1] - 2 and 2 <= my < img.shape[0] - 2):
        res[d['hh_id']] = 'OUT'
        continue
    patch = img[my - 2:my + 3, mx - 2:mx + 3].reshape(-1, 3).astype(int)
    # медиана устойчивее
    med = np.median(patch, axis=0).astype(int)
    rgb = (int(med[2]), int(med[1]), int(med[0]))
    best_i, best_d = None, 999999
    for i, pc in enumerate(PALETTE + [CU]):
        dd = sum((a - b) ** 2 for a, b in zip(rgb, pc))
        if dd < best_d:
            best_d, best_i = dd, i
    name = 'CU' if best_i == len(PALETTE) else f'P{best_i}'
    res[d['hh_id']] = dict(rgb=rgb, zone=name, d=best_d,
                           hidden=d['hh_id'] in hidden,
                           map=(mx, my), sq_m=(round(ex), round(ey)))

# статистика
from collections import Counter
cnt = Counter(r['zone'] for r in res.values() if not r['hidden'])
print('зоны по цветам квадратов (не скрытые):', dict(cnt))
z1 = [hh for hh, r in res.items() if r['zone'] == 'P0' and not r['hidden']]
print(f'\nдропов с КВАДРАТОМ ЗОНЫ-1 (синий P0): {len(z1)}')

# отпечаток скриншота: муфта севернее, |dx|<6м, дроп 8-24м
cbn = {c['node']: c for c in net['couplers']}
mpp = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]['mpp']
geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
blds = []
for b in osm['buildings']:
    pts = [((lo - geo['west']) * 111320 * math.cos(math.radians(la)) / mpp,
            (geo['north'] - la) * 111320 / mpp) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    blds.append(dict(bid=b['id'], x0=min(xs), x1=max(xs), y0=min(ys),
                     y1=max(ys), area=b.get('area', 0),
                     lv=b.get('tags', {}).get('building:levels')))
# граф фидера для терминальности
from collections import defaultdict
adj = defaultdict(set)
for e in net['feeder_edges']:
    a = (round(e[0][0], 1), round(e[0][1], 1))
    b2 = (round(e[1][0], 1), round(e[1][1], 1))
    adj[a].add(b2)
    adj[b2].add(a)

drop_by_id = {d['hh_id']: d for d in net['drops']}
print('\n== зона-1 дропы: геометрия (муфта относительно квадрата) ==')
rows = []
for hh in z1:
    d = drop_by_id[hh]
    ex, ey = d['poly'][-1]
    c = cbn[d['coupler']]
    dx, dy = ex - c['x'], ey - c['y']
    north = dy > 8
    col = abs(dx) * mpp < 6.0
    kk = (round(c['x'], 1), round(c['y'], 1))
    east = any(b3[0] > c['x'] + 6 for b3 in adj.get(kk, ()))
    best = None
    for b3 in blds:
        ddx = max(b3['x0'] - ex, ex - b3['x1'], 0)
        ddy = max(b3['y0'] - ey, ey - b3['y1'], 0)
        dd = math.hypot(ddx, ddy) * mpp
        if best is None or dd < best[0]:
            best = (dd, b3)
    dd, b3 = best
    w_m = (b3['x1'] - b3['x0']) * mpp
    h_m = (b3['y1'] - b3['y0']) * mpp
    L, Wd = max(w_m, h_m), min(w_m, h_m)
    rows.append(dict(hh=hh, sq=(round(ex), round(ey)), coup=c['label'],
                     coup_xy=(round(c['x']), round(c['y'])),
                     dx_m=round(dx * mpp, 1), dy_m=round(dy * mpp, 1),
                     len=d['length_m'], north=north, col=col, east_cont=east,
                     bld=dict(bid=b3['bid'], dist=round(dd, 1), L=round(L, 1),
                              W=round(Wd, 1), ar=round(L / Wd, 2),
                              rot='H' if w_m > h_m else 'V',
                              lv=b3['lv'], S=round(b3['area'], 1))))
    r = rows[-1]
    mark = ' <<<' if (r['north'] and r['col'] and 8 <= r['len'] <= 24) else ''
    print(f"  hh{r['hh']} sq={r['sq']} {r['coup']}{r['coup_xy']} "
          f"dx={r['dx_m']}м dy={r['dy_m']}м len={r['len']:.0f}м "
          f"{'С' if r['north'] else 'ю'}{'|верт' if r['col'] else ''}"
          f"{'|фидВ' if r['east_cont'] else ''} | bld {r['bld']['bid']} "
          f"{r['bld']['dist']}м {r['bld']['L']}x{r['bld']['W']} "
          f"{r['bld']['rot']} ar={r['bld']['ar']}{mark}")
json.dump(dict(zone_colors={str(k): v for k, v in res.items()},
               z1_rows=rows),
          open(f'{BASE}/work/altay3/t60_zone_truth.json', 'w'),
          ensure_ascii=False, indent=1)
