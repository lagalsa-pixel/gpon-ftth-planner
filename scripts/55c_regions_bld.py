#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55c: здания в сматченных регионах altay2 + template-матчинг img_10.

1) map px -> frame (y-300) -> mosaic (M_full) -> здания OSM в регионе
2) img_10 (SIFT не сматчился): template matching (TM_CCOEFF_NORMED)
   против map_half на масштабах апскейла 2..6
3) img_11 (NCC 0.594): перекрёстная проверка template matching'ом
Выход: work/altay2/regions_bld.json
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_full = tr['M_full']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def m2f(x, y):
    return (M_full[0][0] * x + M_full[0][1] * y + M_full[0][2],
            M_full[1][0] * x + M_full[1][1] * y + M_full[1][2])


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

net = json.load(open(BASE / f'work/{KEY}/network_hh2.json'))
drops = net['drops']
DROP_TOL = 14.0


def drops_at(bid, tol=DROP_TOL):
    b = BLD[bid]
    return [d for d in drops
            if b['poly'].distance(Point(d['poly'][-1])) <= tol]


def bld_info(bid):
    b = BLD[bid]
    xs = [p[0] for p in b['pts']]
    ys = [p[1] for p in b['pts']]
    w = (max(xs) - min(xs)) * mpp
    h = (max(ys) - min(ys)) * mpp
    dd = drops_at(bid)
    return dict(id=bid, size=f'{w:.1f}x{h:.1f}', area=round(w * h, 1),
                drops=len(dd), cx=b['cx'], cy=b['cy'],
                tags=BLD[bid].get('tags', {}))


def region_map_to_mosaic(x0, y0, x1, y1):
    # map -> frame (шапка 300 px сверху) -> mosaic
    pts_f = [(x0, y0 - 300), (x1, y1 - 300)]
    mos = [m2f(x, y) for x, y in pts_f]
    return mos  # [(mx0,my0),(mx1,my1)]


def bld_in_region(reg):
    (mx0, my0), (mx1, my1) = region_map_to_mosaic(*reg)
    box = Polygon([(mx0, my0), (mx1, my0), (mx1, my1), (mx0, my1)])
    out = []
    for bid, b in BLD.items():
        if b['poly'].intersects(box):
            info = bld_info(bid)
            info['center_in'] = bool(box.contains(Point(b['cx'], b['cy'])))
            out.append(info)
    out.sort(key=lambda r: (not r['center_in'], -r['area']))
    return out


def template_match(name, scales=(2.0, 3.0, 4.0, 6.0)):
    """TM_CCOEFF_NORMED по map_half, возврат лучшего региона (map px)."""
    MAP = str(DIR / 'map06_v4.jpg')
    map_full = cv2.imread(MAP, cv2.IMREAD_GRAYSCALE)
    Hf, Wf = map_full.shape
    map_half = cv2.resize(map_full, (Wf // 2, Hf // 2),
                          interpolation=cv2.INTER_AREA)
    fig0 = cv2.imread(str(DIR / name), cv2.IMREAD_GRAYSCALE)
    best = None
    for s in scales:
        h0, w0 = fig0.shape
        tpl = cv2.resize(fig0, (int(w0 * s / 2), int(h0 * s / 2)),
                         interpolation=cv2.INTER_CUBIC)
        if min(tpl.shape) < 20 or tpl.shape[0] >= map_half.shape[0] \
                or tpl.shape[1] >= map_half.shape[1]:
            continue
        r = cv2.matchTemplate(map_half, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        x0h, y0h = loc
        region = [x0h * 2, y0h * 2, (x0h + tpl.shape[1]) * 2,
                  (y0h + tpl.shape[0]) * 2]
        if best is None or mx > best[0]:
            best = (float(mx), s, region)
        print(f'  {name} tpl s={s}: peak={mx:.3f} region={region}')
    return best


def main():
    figs = json.load(open(DIR / 'fig_match.json'))
    results = {}
    for name, m in figs.items():
        if m is None:
            print(f'{name}: нет SITF-матча — template matching')
            tm = template_match(name)
            if tm and tm[0] >= 0.45:
                m = dict(variant='tpl', scale=tm[1], inliers=0, good=0,
                         ncc=round(tm[0], 3), region=tm[2])
                print(f'{name}: TPL MATCH peak={tm[0]:.3f} s={tm[1]} '
                      f'region={tm[2]}')
            else:
                print(f'{name}: template тоже не сматчился')
        else:
            # перекрёстная проверка низкодостоверных
            if m['ncc'] < 0.8:
                print(f'{name}: SIFT NCC {m["ncc"]} < 0.8 — cross-check')
                tm = template_match(name, scales=(2.0, 3.0, 4.0))
                if tm:
                    print(f'  tpl peak={tm[0]:.3f} region={tm[2]} '
                          f'(SIFT: {m["region"]})')
                    dx = abs(tm[2][0] - m['region'][0])
                    dy = abs(tm[2][1] - m['region'][1])
                    if dx < 40 and dy < 40 and tm[0] >= 0.45:
                        print('  -> регионы согласованы, беру SIFT')
                    elif tm[0] >= 0.55:
                        m = dict(variant='tpl', scale=tm[1], inliers=0,
                                 good=0, ncc=round(tm[0], 3), region=tm[2])
                        print('  -> беру template (сильнее)')
        if m is None:
            results[name] = None
            continue
        bl = bld_in_region(m['region'])
        results[name] = dict(match=m, buildings=bl)
        print(f'{name}: region={m["region"]} ncc={m["ncc"]}')
        for b in bl[:14]:
            print(f'   {b["id"]} {b["size"]}м drops={b["drops"]} '
                  f'center_in={b["center_in"]}')
        print()

    json.dump(results, open(DIR / 'regions_bld.json', 'w'),
              ensure_ascii=False, indent=1)
    print('saved regions_bld.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
