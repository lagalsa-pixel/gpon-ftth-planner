#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59e: цвет квадрата ДХ у каждого кандидата (по картам v8).
Квадрат зоны 1 = PALETTE[0] (25,113,194) — как на скриншоте altay3.
Кандидаты: вытянутые здания (ar>=2.0, L 25-140 м) с 1-3 ДХ (допуск 15 м)."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
KEYS = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe',
        'prigorodnoe', 'altaiskiy']
MAPFILE = {'verhneberezovka': 'map01_v8.jpg', 'solnechnoe': 'map02_v8.jpg',
           'perevalnoe': 'map03_half.jpg', 'vinnoe': 'map04_half.jpg',
           'prigorodnoe': 'map05_v8.jpg', 'altaiskiy': 'map06_v8.jpg'}
# для половинок — координаты тоже /2
HALF = {'perevalnoe': True, 'vinnoe': True}
PALETTE = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
           (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
           (160, 90, 44)]


def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)


def main():
    geo = json.load(open(BASE / 'work/mosaic_geo.json'))
    out = []
    for key in KEYS:
        g = geo[key]
        mpp = g['mpp']
        osm = json.load(open(BASE / f'work/{key}/osm.json'))
        net = json.load(open(BASE / f'work/{key}/network_hh3.json'))
        drops = net['drops']
        tr = None
        if key != 'verhneberezovka':
            tr = json.load(open(BASE / f'work/{key}/crop_transform.json'))
            Mi = tr['M_inv']
            sc = tr['scale']
        else:
            Mi = [[1, 0, 0], [0, 1, 0]]
            sc = 1.0
        half = HALF.get(key, False)
        div = 2.0 if half else 1.0

        def m2map(px, py):
            x = Mi[0][0] * px + Mi[0][1] * py + Mi[0][2]
            y = Mi[1][0] * px + Mi[1][1] * py + Mi[1][2]
            return x / div, y / div

        img = cv2.imread(str(BASE / 'work/altay3' / MAPFILE[key]))
        for b in osm['buildings']:
            pts = [geo_to_px(la, lo, g['west'], g['north'], mpp)
                   for la, lo in b['poly']]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            w_m, h_m = (x1 - x0) * mpp, (y1 - y0) * mpp
            L, Wd = max(w_m, h_m), min(w_m, h_m)
            if Wd < 6 or L < 25 or L > 140 or L / Wd < 2.0:
                continue
            tol = 15.0 / mpp
            near = []
            for d in drops:
                ex, ey = d['poly'][-1]
                dx = max(x0 - ex, ex - x1, 0)
                dy = max(y0 - ey, ey - y1, 0)
                if math.hypot(dx, dy) <= tol:
                    near.append(d)
            if not (1 <= len(near) <= 3):
                continue
            for d in near:
                ex, ey = d['poly'][-1]
                mx, my = m2map(ex, ey)
                mx, my = int(round(mx)), int(round(my))
                R = 26
                crop = img[max(0, my - R):my + R, max(0, mx - R):mx + R]
                if crop.size < 100:
                    continue
                # ищем компактный насыщенный синий/цветной блоб в центре
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                h2, s2, v2 = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
                m = ((s2 > 110) & (v2 > 90) &
                     (((h2 > 80) & (h2 < 145)) |
                      ((h2 < 12) | (h2 > 168)) |
                      ((h2 > 35) & (h2 < 80))))
                ys2, xs2 = np.where(m)
                if len(xs2) < 15:
                    continue
                # кластер вокруг центра кропа
                cx0, cy0 = crop.shape[1] // 2, crop.shape[0] // 2
                d2 = np.hypot(xs2 - cx0, ys2 - cy0)
                sel = d2 < 16
                if sel.sum() < 10:
                    continue
                bgr = crop[ys2[sel], xs2[sel]].mean(axis=0).astype(int)
                rgb = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
                # ближайший цвет палитры
                best_i, best_d = None, 999
                for i, pc in enumerate(PALETTE + [(224, 49, 49)]):
                    dd = sum((a - b2) ** 2 for a, b2 in zip(rgb, pc))
                    if dd < best_d:
                        best_d, best_i = dd, i
                out.append(dict(key=key, bid=b['id'], hh_id=d['hh_id'],
                                L=round(L, 1), W=round(Wd, 1),
                                ar=round(L / Wd, 2),
                                n_dh=len(near),
                                drop_len=d['length_m'],
                                rgb=rgb,
                                pal_i=best_i, pal_d=int(best_d),
                                mx=mx, my=my, half=half))
    # зона 1: pal_i == 0
    z1 = [c for c in out if c['pal_i'] == 0]
    print(f'всего кандидатов: {len(out)}, из них с квадратом зоны 1: {len(z1)}')
    for c in z1:
        print(f"  {c['key']} bid={c['bid']} hh={c['hh_id']} "
              f"{c['L']}x{c['W']} ar={c['ar']} n_dh={c['n_dh']} "
              f"drop={c['drop_len']:.0f}м rgb={c['rgb']} at({c['mx']},{c['my']})"
              f"{' HALF' if c['half'] else ''}")
    json.dump(out, open(BASE / 'work/altay3/square_colors.json', 'w'),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
