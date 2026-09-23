#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кластеризация OSM-зданий в усадьбы (connected components по дистанции)."""
import json, math
import numpy as np

WORK = '/home/z/my-project/work'

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)
with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
    OSM = json.load(f)

RES = {'yes', 'house', 'residential', 'detached', 'semidetached_house', 'bungalow', 'allotment_house', 'dacha'}

for snp in SNPS:
    name = snp['name']
    rec = OSM[name]
    lat0, lon0 = snp['lat'], snp['lon']
    mx = 111320 * math.cos(math.radians(lat0))

    blds = []
    for b in rec['buildings']:
        if b['tags'].get('building', 'yes') not in RES:
            continue
        lats = [p[0] for p in b['geom']]; lons = [p[1] for p in b['geom']]
        area = abs((max(lons)-min(lons)) * mx * (max(lats)-min(lats)) * 111320)
        cx = (sum(p[1] for p in b['geom']) / len(b['geom']) - lon0) * mx
        cy = (sum(p[0] for p in b['geom']) / len(b['geom']) - lat0) * 111320
        blds.append({'cx': cx, 'cy': cy, 'area': area, 'tags': b['tags']})

    for R in (30, 40, 50):
        pts = np.array([[b['cx'], b['cy']] for b in blds])
        n = len(blds)
        if n == 0:
            continue
        visited = [False] * n
        clusters = []
        for i in range(n):
            if visited[i]:
                continue
            stack, comp = [i], []
            visited[i] = True
            while stack:
                j = stack.pop()
                comp.append(j)
                d2 = (pts[j, 0] - pts[:, 0]) ** 2 + (pts[j, 1] - pts[:, 1]) ** 2
                for q in np.where((d2 <= R * R) & np.array([not v for v in visited]))[0]:
                    visited[q] = True
                    stack.append(q)
            clusters.append(comp)
        if R == 40:
            keep40 = len(clusters)
    print(f"{name}: жилых OSM-зданий {len(blds)} | усадеб при R=30/40/50 м: "
          f"{[0]*3 if not blds else ''}", end='')
    # повтор для всех R
    res = []
    for R in (30, 40, 50):
        pts = np.array([[b['cx'], b['cy']] for b in blds]) if blds else np.zeros((0, 2))
        n = len(blds)
        visited = [False] * n
        cnt = 0
        for i in range(n):
            if visited[i]:
                continue
            cnt += 1
            stack = [i]
            visited[i] = True
            while stack:
                j = stack.pop()
                d2 = (pts[j, 0] - pts[:, 0]) ** 2 + (pts[j, 1] - pts[:, 1]) ** 2
                for q in np.where((d2 <= R * R) & np.array([not v for v in visited]))[0]:
                    visited[q] = True
                    stack.append(q)
        res.append(cnt)
    print(f" {res} | Excel {snp['households']}")
