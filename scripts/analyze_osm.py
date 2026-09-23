#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ OSM-зданий: теги, распределение, покрытие bbox тайлов."""
import json
from collections import Counter

WORK = '/home/z/my-project/work'
with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
    data = json.load(f)
with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    snps = {s['name']: s for s in json.load(f)}

RES_TAGS = {'yes', 'house', 'residential', 'detached', 'semidetached_house', 'bungalow', 'allotment_house', 'dacha'}
for name, rec in data.items():
    exp = snps[name]['households']
    blds = rec['buildings']
    cnt = Counter(b['tags'].get('building', '?') for b in blds)
    with_addr = sum(1 for b in blds if 'addr:housenumber' in b['tags'] or 'addr:street' in b['tags'])
    res = [b for b in blds if b['tags'].get('building', 'yes') in RES_TAGS]

    # края bbox: здания в 100м полосе у границы тайлов
    with open(f'{WORK}/geo/{name}.json', encoding='utf-8') as f:
        g = json.load(f)
    dlat_edge = 100 / 111320
    dlon_edge = 100 / (111320 * 0.642)
    near_edge = 0
    for b in res:
        lats = [p[0] for p in b['geom']]; lons = [p[1] for p in b['geom']]
        if (min(lats) < g['lat_min'] + dlat_edge or max(lats) > g['lat_max'] - dlat_edge or
                min(lons) < g['lon_min'] + dlon_edge or max(lons) > g['lon_max'] - dlon_edge):
            near_edge += 1

    print(f"=== {name}: ожид. {exp} ДХ | всего зд. {len(blds)} | жилых по тегам {len(res)} "
          f"({len(res)/exp*100:.0f}% от ожид.) | с адресом {with_addr} | у края bbox {near_edge}")
    print(f"    теги: {dict(cnt.most_common(8))}")
