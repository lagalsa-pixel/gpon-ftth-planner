#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 52 (диагностика трасс). Detour-анализ: путь по дереву сети (ЦУ -> муфта)
против кратчайшего пути дорожного графа.

Для каждой муфты сети:
  d_tree  — длина пути от корня (ЦУ) по рёбрам магистрали (feeder_edges);
  d_short — кратчайший путь по ПОЛНОМУ дорожному графу (Дейкстра);
  ratio   = d_tree / d_short.

Отчёт: распределение ratio, худшие случаи (координаты, длины), суммарная
длина дерева vs суммарная длина SPT-дерева кратчайших путей (оценка
стоимости перехода на «все кратчайшие»).

Использование: python3 52_diag_routes.py <village_dir> [<net_file>]
  village_dir — каталог с osm.json/geo.json/network*.json (px мозаики).
"""
import json
import math
import os
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

BASE = '/home/z/my-project'
sys.path.insert(0, f'{BASE}/download/ftth_pipeline')
import ftth_pipeline as fp  # noqa: E402  (geo_to_px, RoadGraph, CONFIG)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def road_graph(osm, geo, mpp, densify=4.0):
    """Дорожный граф (как build_road_graph пайплайна, без bounds)."""
    G = fp.RoadGraph()
    west, north = geo['west'], geo['north']
    W, H = geo['W'], geo['H']
    for r in osm['roads']:
        pts = [fp.geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
        if all(p[0] < -200 or p[0] > W + 200 or p[1] < -200 or p[1] > H + 200
               for p in pts):
            continue
        dens = [pts[0]]
        for p in pts[1:]:
            q = dens[-1]
            seg = math.hypot(p[0] - q[0], p[1] - q[1]) * mpp
            n_sub = int(seg / densify)
            for k in range(1, n_sub + 1):
                dens.append((q[0] + (p[0] - q[0]) * k / max(n_sub, 1),
                             q[1] + (p[1] - q[1]) * k / max(n_sub, 1)))
            if seg < densify:
                dens.append(p)
        G.add_polyline(dens, mpp)
    P = np.array(G.pts)
    rows, cols, vals = [], [], []
    for (u, w, l) in G.edges:
        rows += [u, w]
        cols += [w, u]
        vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(len(P), len(P)))
    return P, C


def analyse(vdir, net_file):
    osm = load(f'{vdir}/osm.json')
    geo = load(f'{vdir}/geo.json')
    net = load(f'{vdir}/{net_file}')
    mpp = geo['mpp']

    P, C = road_graph(osm, geo, mpp)
    kdt = cKDTree(P)
    print(f'{os.path.basename(vdir)} [{net_file}]: граф {len(P)} узлов, '
          f'{C.nnz // 2} рёбер; муфт {len(net["couplers"])}, '
          f'дропов {len(net["drops"])}')

    # корень: ближайший узел к якорю
    ax, ay = net['anchor']['x'], net['anchor']['y']
    root = int(kdt.query([ax, ay])[1])

    # дерево сети: рёбра feeder_edges (px) -> узлы графа
    def node_of(x, y):
        return int(kdt.query([x, y])[1])

    rows, cols, vals = [], [], []
    tree_len = 0.0
    edges_set = set()
    for e in net['feeder_edges']:
        (x1, y1), (x2, y2) = e
        u, w = node_of(x1, y1), node_of(x2, y2)
        if u == w:
            continue
        l = math.hypot(x2 - x1, y2 - y1) * mpp
        key = (min(u, w), max(u, w))
        if key in edges_set:
            continue
        edges_set.add(key)
        tree_len += l
        rows += [u, w]
        cols += [w, u]
        vals += [l, l]
    U = csr_matrix((vals, (rows, cols)), shape=(len(P), len(P)))

    dU = dijkstra(U, indices=root)
    dC = dijkstra(C, indices=root)

    # муфты -> узлы
    res = []
    for c in net['couplers']:
        i = node_of(c['x'], c['y'])
        dt, ds = dU[i], dC[i]
        if not np.isfinite(ds) or ds <= 1.0:
            continue
        res.append(dict(label=c['label'], node=i, x=c['x'], y=c['y'],
                        d_tree=float(dt), d_short=float(ds),
                        ratio=float(dt / ds) if np.isfinite(dt) else None))
    served = [r for r in res if r['ratio'] is not None]
    unreachable = len(res) - len(served)
    served.sort(key=lambda r: -(r['d_tree'] - r['d_short']))

    n = len(served)
    ratios = sorted(r['ratio'] for r in served)
    q = lambda p: ratios[min(n - 1, int(p * n))]
    print(f'  длина дерева сети: {tree_len / 1000:.2f} км')
    print(f'  муфты в анализе: {n} (недостижимых по дереву: {unreachable})')
    print(f'  detour ratio: med {q(0.5):.3f}  p75 {q(0.75):.3f}  '
          f'p90 {q(0.90):.3f}  p97 {q(0.97):.3f}  max {ratios[-1]:.3f}')
    for th in (1.05, 1.10, 1.20, 1.50):
        k = sum(1 for r in ratios if r > th)
        print(f'    муфт с ratio>{th}: {k} ({100 * k / n:.0f}%)')

    print('  худшие 12 (обход длиннее кратчайшего):')
    for r in served[:12]:
        print(f'    {r["label"]:<5} px=({r["x"]:.0f},{r["y"]:.0f}) '
              f'дерево {r["d_tree"]:7.0f} м  кратч. {r["d_short"]:7.0f} м  '
              f'ratio {r["ratio"]:.2f}')

    # SPT-дерево: объединение кратчайших путей корень->все муфты
    _, pred = dijkstra(C, indices=root, return_predecessors=True)
    spt_edges = set()
    for c in net['couplers']:
        i = node_of(c['x'], c['y'])
        cur = i
        g = 0
        while cur != root and pred[cur] >= 0 and g < 10 ** 6:
            spt_edges.add((min(cur, int(pred[cur])), max(cur, int(pred[cur]))))
            cur = int(pred[cur])
            g += 1
    spt_len = 0.0
    for (u, w) in spt_edges:
        spt_len += math.hypot(P[u][0] - P[w][0], P[u][1] - P[w][1]) * mpp
    print(f'  SPT (объединение кратчайших путей до муфт): {spt_len / 1000:.2f} км '
          f'(+{(spt_len - tree_len) / 1000:.2f} км к дереву, '
          f'{100 * (spt_len - tree_len) / max(tree_len, 1):.1f}%)')
    return res


if __name__ == '__main__':
    vdir = sys.argv[1] if len(sys.argv) > 1 else f'{BASE}/work/topolnoe_test/work/topolnoe'
    net_file = sys.argv[2] if len(sys.argv) > 2 else 'network.json'
    analyse(vdir, net_file)
