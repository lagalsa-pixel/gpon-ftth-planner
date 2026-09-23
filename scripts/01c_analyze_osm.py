# -*- coding: utf-8 -*-
"""Численный анализ OSM-данных: где застройка относительно центра камеры."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json

def dist_m(la1, lo1, la2, lo2):
    dy = (la1 - la2) * 111320
    dx = (lo1 - lo2) * 111320 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dx, dy)

for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    clat, clon = v['lat'], v['lon']
    b = d['buildings']
    dists = sorted(dist_m(bc[0], bc[1], clat, clon) for bc in [x['center'] for x in b])
    print(f"\n=== {v['name']} (ожид. {v['hh']} ДХ), зданий {len(b)}, bbox {d['bbox']}")
    if dists:
        print(f"  дистанции зданий от центра: min={dists[0]:.0f} p10={dists[len(dists)//10]:.0f} медиана={dists[len(dists)//2]:.0f} p90={dists[9*len(dists)//10]:.0f} max={dists[-1]:.0f}")
        # кластеры по углу/расстоянию: гистограмма по 200-м кольцам
        rings = {}
        for dd in dists:
            rings[int(dd // 200)] = rings.get(int(dd // 200), 0) + 1
        print("  кольца по 200 м (радиус_км: зданий):", ", ".join(f"{k*0.2:.1f}:{n}" for k, n in sorted(rings.items())[:12]))
        # bbox всех зданий
        lats = [x['center'][0] for x in b]; lons = [x['center'][1] for x in b]
        w = (max(lons)-min(lons)) * 111320 * math.cos(math.radians(clat))
        h = (max(lats)-min(lats)) * 111320
        print(f"  полный разброс зданий: {w:.2f} x {h:.2f} км, центр масс ({sum(lats)/len(lats):.5f},{sum(lons)/len(lons):.5f})")
        # смещение центра масс относительно камеры
        print(f"  смещение центра масс от камеры: {dist_m(sum(lats)/len(lats), sum(lons)/len(lons), clat, clon):.0f} м")
