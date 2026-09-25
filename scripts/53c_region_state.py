#!/usr/bin/env python3
"""Task 53: состояние сети Алтайского в регионах замечаний (R1-R4, R6).

map px -> mosaic px: сначала минус шапка HH=300 (map->frame), затем M_full.
Выход: для каждого региона — дропы (ДХ) с домовой точкой внутри, муфты рядом.
"""
import json
from pathlib import Path

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M = tr['M_full']                      # frame -> mosaic
HH = 300                              # шапка карты в map px (S(150), k=2)


def map_to_mosaic(x, y):
    fx, fy = x, y - HH
    return (M[0][0] * fx + M[0][1] * fy + M[0][2],
            M[1][0] * fx + M[1][1] * fy + M[1][2])


REGIONS = {
    'R1_два_многоэтажных': (983, 2867, 2137, 3115),
    'R2_многоэтажные': (1048, 4048, 2249, 4869),
    'R3_многоэтажные': (932, 5310, 2820, 7364),
    'R4_не_идентифицированы': (1843, 2439, 2088, 2721),
    'R6_по_два_ДХ': (273, 1806, 676, 2530),
}

net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))
drops = net['drops']
couplers = net['couplers']

for name, (x0, y0, x1, y1) in REGIONS.items():
    mx0, my0 = map_to_mosaic(x0, y0)
    mx1, my1 = map_to_mosaic(x1, y1)
    print(f'=== {name}: map[{x0}..{x1}, {y0}..{y1}] -> '
          f'mosaic[{mx0:.0f}..{mx1:.0f}, {my0:.0f}..{my1:.0f}]')
    in_drops = []
    for d in drops:
        px, py = d['poly'][-1]
        if mx0 <= px <= mx1 and my0 <= py <= my1:
            in_drops.append(d)
    print(f'  дропов (ДХ) в регионе: {len(in_drops)}')
    for d in in_drops:
        p = d['poly'][-1]
        print(f"    hh_id={d['hh_id']} hh={d.get('hh')} coupler={d.get('coupler')}"
              f" L={d['length_m']}м дом=({p[0]:.0f},{p[1]:.0f})")
    cs = [c for c in couplers
          if mx0 - 80 <= c['x'] <= mx1 + 80 and my0 - 80 <= c['y'] <= my1 + 80]
    print(f'  муфт в регионе (+80px): {len(cs)}')

print()
print('итого дропов в сети:', len(drops))
