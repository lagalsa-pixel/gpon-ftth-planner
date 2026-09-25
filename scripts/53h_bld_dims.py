#!/usr/bin/env python3
"""Task 53: точные габариты OSM-полигонов зданий в регионах замечаний."""
import json
import math
from pathlib import Path

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def geo_to_px(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
by_id = {}
for b in osm['buildings']:
    pts_px = [geo_to_px(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts_px]
    ys = [p[1] for p in pts_px]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    by_id[b['id']] = dict(cx=geo_to_px(*b['center']), w=w, h=h,
                          area_px=w * h, area_m2=w * h * mpp * mpp,
                          area_osm=b.get('area'), tags=b.get('tags', {}))

TARGETS = {
    'R1': [496463512, 496463513],
    'R2': [496463514, 496463485, 496463483, 496463515, 496463482, 496463480],
    'R3': [637127294, 637127280, 637127293, 637127270, 637127289,
           637127282, 637127287, 637127271, 637127285, 637127272,
           637127284, 637127292, 637127291, 637127290, 637127288,
           496463481],
    'R4': [759801038, 759801037, 759801036, 759801035],
    'R6': [496463491, 496463492, 496463493, 496463496, 496463495,
           496463494, 496463500, 496463499, 496463498, 496463497],
}

for reg, ids in TARGETS.items():
    print(f'=== {reg} ===')
    for i in ids:
        b = by_id.get(i)
        if not b:
            print(f'  id={i}: НЕ НАЙДЕН')
            continue
        print(f"  id={i} bbox={b['w']*mpp:.1f}x{b['h']*mpp:.1f}м "
              f"S_bbox={b['area_m2']:.0f}м2 S_osm={b['area_osm']:.0f}м2 "
              f"c=({b['cx'][0]:.0f},{b['cx'][1]:.0f}) "
              f"lv={b['tags'].get('building:levels','-')} "
              f"{b['tags'].get('building','')}")

# все здания с bbox-площадью > 150 м2 (кандидаты в многоэтажки) по всему селу
print()
print('=== ВСЕ здания Алтайского с footprint >= 130 м2 ===')
big = [(i, b) for i, b in by_id.items() if b['area_m2'] >= 130]
for i, b in sorted(big, key=lambda x: -x[1]['area_m2']):
    print(f"  id={i} bbox={b['w']*mpp:.1f}x{b['h']*mpp:.1f}м "
          f"S_bbox={b['area_m2']:.0f}м2 c=({b['cx'][0]:.0f},{b['cx'][1]:.0f}) "
          f"lv={b['tags'].get('building:levels','-')} "
          f"{b['tags'].get('building','')}")
