#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 52 (диагностика трасс, ч.2). Симуляция детур-гарда.

Гипотеза: дерево Штейнера (Мелхорн) даёт отдельным маршрутам обходы до 2x.
Фикс: добавить в граф объединения кратчайшие пути терминалов с ratio>1+eps
(один проход достаточен: после добавления d_U[t] <= d_C[t] для них,
остальные только улучшаются).

Симуляция на реальных данных: рост длины дерева vs остаточные detour ratio
для eps in {0.30, 0.20, 0.10, 0.05}.

Использование: python3 52b_simulate_guard.py <village_dir> <net_file> [key]
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
import ftth_pipeline as fp  # noqa: E402


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def build_env(vdir, key):
    osm = load(f'{vdir}/osm.json')
    if os.path.exists(f'{vdir}/geo.json'):
        geo = load(f'{vdir}/geo.json')
    else:
        geo = load(f'{BASE}/work/mosaic_geo.json')[key]
    mpp = geo['mpp']
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
            n_sub = int(seg / 4.0)
            for k in range(1, n_sub + 1):
                dens.append((q[0] + (p[0] - q[0]) * k / max(n_sub, 1),
                             q[1] + (p[1] - q[1]) * k / max(n_sub, 1)))
            if seg < 4.0:
                dens.append(p)
        G.add_polyline(dens, mpp)
    P = np.array(G.pts)
    rows, cols, vals = [], [], []
    for (u, w, l) in G.edges:
        rows += [u, w]
        cols += [w, u]
        vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(len(P), len(P)))
    return P, C, mpp


def elen_of(P, mpp, u, w):
    return math.hypot(P[u][0] - P[w][0], P[u][1] - P[w][1]) * mpp


def simulate(vdir, net_file, key=None):
    if key is None:
        key = os.path.basename(vdir.rstrip('/'))
    P, C, mpp = build_env(vdir, key)
    net = load(f'{vdir}/{net_file}')
    kdt = cKDTree(P)

    ax, ay = net['anchor']['x'], net['anchor']['y']
    root = int(kdt.query([ax, ay])[1])

    def node_of(x, y):
        return int(kdt.query([x, y])[1])

    # базовое дерево сети
    union = set()
    base_len = 0.0
    for e in net['feeder_edges']:
        (x1, y1), (x2, y2) = e
        u, w = node_of(x1, y1), node_of(x2, y2)
        if u == w:
            continue
        k = (min(u, w), max(u, w))
        if k in union:
            continue
        union.add(k)
        base_len += elen_of(P, mpp, u, w)

    # терминалы: узлы муфт (прокси терминалов-ДХ; дерево уже включает их пути)
    terms = [node_of(c['x'], c['y']) for c in net['couplers']]

    dC, predC = dijkstra(C, indices=root, return_predecessors=True)
    predC = predC.astype(np.int64)

    def union_matrix(union):
        rows, cols, vals = [], [], []
        for (u, w) in union:
            l = elen_of(P, mpp, u, w)
            rows += [u, w]
            cols += [w, u]
            vals += [l, l]
        return csr_matrix((vals, (rows, cols)), shape=(len(P), len(P)))

    U0 = union_matrix(union)
    dU0 = dijkstra(U0, indices=root)

    print(f'{key} [{net_file}]: дерево {base_len / 1000:.2f} км, '
          f'муфт {len(terms)}, граф {len(P)} узлов')

    def stats(dU, tag, extra_len):
        rs = []
        for t in terms:
            if np.isfinite(dC[t]) and dC[t] > 1 and np.isfinite(dU[t]):
                rs.append(dU[t] / dC[t])
        rs.sort()
        n = len(rs)
        med = rs[n // 2]
        p90 = rs[int(0.9 * n)]
        mx = rs[-1]
        print(f'  {tag:<14} длина +{extra_len / 1000:5.2f} км '
              f'({100 * extra_len / base_len:4.1f}%)  '
              f'| ratio med {med:.3f} p90 {p90:.3f} max {mx:.3f} | >1.2: '
              f'{sum(1 for r in rs if r > 1.2):3d} >1.5: '
              f'{sum(1 for r in rs if r > 1.5):3d}')

    stats(dU0, 'как есть', 0.0)

    for eps, xmin in ((0.50, 0), (0.30, 0), (0.20, 0), (0.20, 150), (0.20, 100),
                      (0.15, 100), (0.10, 100), (0.10, 50)):
        u2 = set(union)
        add_len = 0.0
        # один проход: все нарушители получают свой кратчайший путь.
        # критерий: ratio > 1+eps И абсолютный перерасход > xmin метров
        bad = [t for t in terms
               if np.isfinite(dC[t]) and dC[t] > 1
               and dU0[t] > (1 + eps) * dC[t] + 1e-9
               and dU0[t] - dC[t] > xmin]
        for t in bad:
            cur = t
            g = 0
            while cur != root and predC[cur] >= 0 and g < 10 ** 6:
                p = int(predC[cur])
                k = (min(p, cur), max(p, cur))
                if k not in u2:
                    u2.add(k)
                    add_len += elen_of(P, mpp, p, cur)
                cur = p
                g += 1
        U2 = union_matrix(u2)
        dU2 = dijkstra(U2, indices=root)
        # путевое дерево (pred) на расширенном графе — длина СТВОЛА после
        # пересчёта путей (рёбра, реально лежащие на путях муфта->корень)
        _, predU2 = dijkstra(U2, indices=root, return_predecessors=True)
        used = set()
        for t in terms:
            cur = t
            g = 0
            while cur != root and predU2[cur] >= 0 and g < 10 ** 6:
                p = int(predU2[cur])
                used.add((min(p, cur), max(p, cur)))
                cur = p
                g += 1
        trunk_len = sum(elen_of(P, mpp, u, w) for (u, w) in used)
        stats(dU2, f'eps={eps:.2f},>{xmin}м,n={len(bad)}', trunk_len - base_len)


if __name__ == '__main__':
    vdir = sys.argv[1]
    net_file = sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else None
    simulate(vdir, net_file, key)
