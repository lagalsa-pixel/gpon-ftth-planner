#!/usr/bin/env python3
"""Диагностика кластерной структуры застройки вокруг якорей."""
import json, math, os, sys
from collections import defaultdict, Counter
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftth_households import (VILLAGES, parse_buildings, single_linkage, local_frame,
                             load_ridder_rings, in_ridder)

BASE = os.path.dirname(os.path.abspath(__file__))
OSM_DIR = os.path.join(BASE, 'osm_ftth')

for v in VILLAGES:
    data = json.load(open(os.path.join(OSM_DIR, f"{v['key']}.json")))
    ky, kx = local_frame(v['lat'])
    blds = parse_buildings(data, ky, kx)
    xy = np.array([[b['lat'] * ky, b['lon'] * kx] for b in blds])
    axy = np.array([v['lat'] * ky, v['lon'] * kx])
    d_anchor = np.hypot(xy[:, 0] - axy[0], xy[:, 1] - axy[1])

    # кластеры 350 м
    labels = single_linkage(xy, 350.0)
    groups = defaultdict(list)
    for i, lb in enumerate(labels):
        groups[lb].append(i)
    # якорный кластер
    ai = int(np.argmin(d_anchor))
    a_lab = labels[ai]

    print(f"=== {v['name']} (ожид. ДХ {v['expected']}): всего зданий {len(blds)}, кластеров {len(groups)}")
    # кольца плотности
    for r0, r1 in [(0, 500), (500, 1000), (1000, 1500), (1500, 2000), (2000, 3000), (3000, 5000)]:
        sel = (d_anchor >= r0) & (d_anchor < r1)
        if sel.sum() == 0:
            continue
        areas = np.array([blds[i]['area'] for i in np.where(sel)[0]])
        print(f"    кольцо {r0}-{r1} м: зданий {sel.sum()}, медиан. площадь {np.median(areas):.0f} м2")

    # крупные кластеры по близости к якорю
    cl_info = []
    for lb, idxs in groups.items():
        if len(idxs) < 5:
            continue
        cxy = xy[idxs].mean(axis=0)
        dc = math.hypot(*(cxy - axy))
        cl_info.append((dc, len(idxs), lb))
    cl_info.sort()
    print('    кластеры >=5 зданий (расст. от якоря, размер):')
    for dc, sz, lb in cl_info[:8]:
        mark = ' <== якорный' if lb == a_lab else ''
        print(f'      {dc:6.0f} м: {sz:5d} зданий{mark}')
    if v['special'] == 'ridder':
        outers, inners = load_ridder_rings()
        print(f"    якорь в границе Риддер-акимата: {in_ridder(v['lat'], v['lon'], outers, inners)}")
        in_r = sum(1 for i, b in enumerate(blds) if d_anchor[i] <= 1400)
        print(f'    зданий в радиусе 1400 м от якоря (без исключений): {in_r}')
        in_r2 = sum(1 for i, b in enumerate(blds) if d_anchor[i] <= 1700 and not in_ridder(b['lat'], b['lon'], outers, inners))
        print(f'    зданий в радиусе 1700 м вне границы Риддер-акимата: {in_r2}')
    print()
