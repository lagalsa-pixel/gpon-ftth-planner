# -*- coding: utf-8 -*-
"""Диагностика 46: почему v3(врезы) != v2 — обрезка графа границей удлинила пути?"""
import json
import math
import importlib.util
import numpy as np

BASE = '/home/z/my-project'


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de44 = load_mod('de44', f'{BASE}/scripts/44_feeder_shortest.py')
de46 = load_mod('de46', f'{BASE}/scripts/46_topology_v3.py')

OLD = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
OLD_BY = {v['key']: v for v in OLD['villages']}

for v in de28.VILLAGES:
    key = v['key']
    V3 = de46.VillageV3(v)
    V2 = de44.VillageV2(v)
    cuts = [tuple(l['node']) for l in OLD_BY[key]['cut_log']]
    print(f'== {V3.t.name} ==')
    n_diff = 0
    for z in cuts:
        d2 = float(V2.D[V2.idx[z]])
        d3 = float(V3.D[V3.idx[z]])
        if abs(d2 - d3) > 0.01:
            n_diff += 1
            # какие рёбра пути v2 отсутствуют в обрезанном графе
            pe2 = set(V2.path_edges(z, 'short'))
            pe3 = set(V3.path_edges(z))
            lost = pe2 - pe3
            lost_m = sum(V2.L_of(*e) for e in lost)
            print(f'  врез {z}: v2 {d2:.1f} -> v3 {d3:.1f} (+{d3-d2:.1f} м), '
                  f'потеряно рёбер {len(lost)} ({lost_m:.0f} м)')
    if n_diff == 0:
        print('  все кратчайшие пути врезов совпадают')
