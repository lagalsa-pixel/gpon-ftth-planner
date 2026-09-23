# -*- coding: utf-8 -*-
"""Анализ: кластеризация OSM-зданий в усадьбы с разными eps; выбор оптимального."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json

def yards_count(blds, eps_m):
    eps = eps_m
    used = [False] * len(blds)
    yards = 0
    for i in range(len(blds)):
        if used[i]:
            continue
        yards += 1
        queue = [i]; used[i] = True
        while queue:
            j = queue.pop()
            for k in range(len(blds)):
                if used[k]:
                    continue
                dx = (blds[k][0] - blds[j][0]) * 111320
                dy = (blds[k][1] - blds[j][1]) * 111320 * math.cos(math.radians(blds[j][0]))
                if dx * dx + dy * dy < eps * eps:
                    used[k] = True
                    queue.append(k)
    return yards

print(f"{'село':<18} {'Excel':>6} {'bld':>5} | усадьбы при eps=12/15/18/22/28 м")
for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    fb = load_json('/home/z/my-project/work/bboxes_final.json')[key]['bbox']
    # Пригородное: ограничение радиусом 1100 м от центра (не bbox!)
    if key == 'prigorodnoe':
        R = 1100.0
        blds = [b['center'] for b in d['buildings']
                if math.hypot((b['center'][0]-v['lat'])*111320,
                              (b['center'][1]-v['lon'])*111320*math.cos(math.radians(v['lat']))) < R]
    else:
        blds = [b['center'] for b in d['buildings']
                if fb[0] <= b['center'][1] <= fb[2] and fb[1] <= b['center'][0] <= fb[3]]
    counts = [yards_count(blds, e) for e in (12, 15, 18, 22, 28)]
    print(f"{v['name']:<18} {v['hh']:>6} {len(blds):>5} |  " + " / ".join(f"{c}" for c in counts))
