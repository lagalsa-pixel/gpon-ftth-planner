#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59c: поиск кандидатов «вытянутое здание с ровно 1 ДХ» по всем 6 сёлам.
Критерии по скриншоту altay3: вытянутое ~3:1-4:1, длина ~30-130 м, 1 ДХ-дроп,
квадрат зоны 1 (крупнейшая зона села)."""
import json
import math
from pathlib import Path

BASE = Path('/home/z/my-project')
KEYS = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe',
        'prigorodnoe', 'altaiskiy']
RU = {'verhneberezovka': 'Верхнеберезовка', 'solnechnoe': 'Солнечное',
      'perevalnoe': 'Перевальное', 'vinnoe': 'Винное',
      'prigorodnoe': 'Пригородное', 'altaiskiy': 'Алтайский'}


def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)


def main():
    geo = json.load(open(BASE / 'work/mosaic_geo.json'))
    out = {}
    for key in KEYS:
        g = geo[key]
        mpp = g['mpp']
        osm = json.load(open(BASE / f'work/{key}/osm.json'))
        net = json.load(open(BASE / f'work/{key}/network_hh2.json'))
        drops = net['drops']
        # зоны: топ-зона по числу дропов (без ЦУ) — квадрат какой зоны искать
        # (зона 1 = крупнейшая, цвет PALETTE[0])
        # здания в px
        cands = []
        for b in osm['buildings']:
            pts = [geo_to_px(la, lo, g['west'], g['north'], mpp)
                   for la, lo in b['poly']]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            w_px, h_px = x1 - x0, y1 - y0
            w_m, h_m = w_px * mpp, h_px * mpp
            L, Wd = max(w_m, h_m), min(w_m, h_m)
            if Wd < 6 or L < 25 or L > 140:
                continue
            ar = L / Wd
            if ar < 2.0:
                continue
            # дропы с концом в bbox+допуск 8 м
            tol = 8.0 / mpp
            near = []
            for d in drops:
                ex, ey = d['poly'][-1]
                if x0 - tol <= ex <= x1 + tol and y0 - tol <= ey <= y1 + tol:
                    # точнее: расстояние до полигона (по центру-диагонали)
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    dx = max(x0 - ex, ex - x1, 0)
                    dy = max(y0 - ey, ey - y1, 0)
                    if math.hypot(dx, dy) <= tol:
                        near.append(d['hh_id'])
            if len(near) != 1:
                continue
            cands.append(dict(bid=b['id'], cx=round((x0 + x1) / 2),
                              cy=round((y0 + y1) / 2),
                              L=round(L, 1), W=round(Wd, 1), ar=round(ar, 2),
                              area=round(b.get('area', 0), 1),
                              lv=b.get('tags', {}).get('building:levels'),
                              hh_id=near[0], rot='H' if w_m > h_m else 'V'))
        out[key] = cands
        print(f'{key} ({RU[key]}): {len(cands)} кандидатов')
        for c in sorted(cands, key=lambda c: -c['L']):
            print(f'   bid={c["bid"]} {c["L"]}x{c["W"]} м ar={c["ar"]} '
                  f'lv={c["lv"]} S={c["area"]} hh={c["hh_id"]} '
                  f'center=({c["cx"]},{c["cy"]}) {c["rot"]}')
    json.dump(out, open(BASE / 'work/altay3/candidates.json', 'w'),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
