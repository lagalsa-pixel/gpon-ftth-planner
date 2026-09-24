#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 52. Пост-обработка сетей ВКО (network_hh2 -> network_hh3):
кратчайшие трассы прокладки кабелей вдоль дорог.

Причина: дерево распределения (MST в метрическом замыкании, шаги 06/09)
минимизирует суммарную длину, но отдельные маршруты ЦУ->муфта оказываются
в разы длиннее кратчайшего пути по улицам (замеры 52_diag_routes: Алтайский
медиана 1.27, max 9.9; Топольное — аналогично). Заказчик: «не везде выбраны
оптимальные (кратчайшие) трассы прокладки кабелей вдоль дорог».

Правила (зеркалят фикс ftth_pipeline.build_network, Task 52):
  1) ДЕТУР-ГАРД СТВОЛА: для муфт с заметным обходом (путь по дереву
     > (1+EPS) x кратчайший И перерасход > MIN_M) в дерево добавляется
     кратчайший уличный путь ЦУ->муфта — маршрут становится точным, общие
     участки по-прежнему разделяются.
  2) ДРОПЫ — КРАТЧАЙШИМИ УЛИЧНЫМИ ПУТЯМИ от БЛИЖАЙШЕЙ ПО ДОРОГАМ муфты
     (дроп — выделенное волокно, следовать дереву не обязан). Дворовой
     заход сохраняется из исходного дропа.
  3) ДРОП > MAX_DROP_M: вдоль кратчайшей уличной трассы ставятся
     промежуточные муфты (~INTERM от ДХ), ствол продлевается по этой же
     трассе до муфты, ближайшей к ДХ.
  4) ЧИСТКА: пустые муфты, не являющиеся точками ветвления, удаляются.

Дерево/муфты/дропы сетей ВКО прошли ручные уточнения (кадры 09, перенос
Винного 11, hh2 53) — построечного пересборка НЕ делается, только
пост-обработка геометрии. Выход: work/<key>/network_hh3.json.
Запуск: python3 52d_network_hh3.py [key|all]
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
sys.path.insert(0, f'{BASE}/scripts')
from common import VILLAGES, vdir, load_json, save_json  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'net06', f'{BASE}/scripts/06_network.py')
net06 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(net06)
RoadGraph, geo_to_px = net06.RoadGraph, net06.geo_to_px

EPS = 0.30          # детур-гард: порог ratio к кратчайшему
MIN_M = 100.0       # ... и минимальный абсолютный перерасход, м
MAX_DROP_M = 120.0
INTERM = 100.0
SNAP_PX = 2.0       # допуск снапа точки дропа к узлу графа


def road_graph(key):
    """Дорожный граф в стиле 06 (densify 4 м) — узлы совпадают с исходными."""
    geo = load_json(f'{BASE}/work/mosaic_geo.json')[key]
    d = load_json(f'{vdir(key)}/osm.json')
    mpp = geo['mpp']
    G = RoadGraph()
    mstep = 4.0
    for r in d['roads']:
        pts = [geo_to_px(la, lo, geo['west'], geo['north'], mpp)
               for la, lo in r['pts']]
        if all(p[0] < -200 or p[0] > geo['W'] + 200 or p[1] < -200
               or p[1] > geo['H'] + 200 for p in pts):
            continue
        dens = [pts[0]]
        for p in pts[1:]:
            q = dens[-1]
            seg = math.hypot(p[0] - q[0], p[1] - q[1]) * mpp
            n_sub = int(seg / mstep)
            for k in range(1, n_sub + 1):
                dens.append((q[0] + (p[0] - q[0]) * k / max(n_sub, 1),
                             q[1] + (p[1] - q[1]) * k / max(n_sub, 1)))
            if seg < mstep:
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


def elen(P, mpp, u, w):
    return math.hypot(P[u][0] - P[w][0], P[u][1] - P[w][1]) * mpp


def process(key):
    print(f'== {key} ==')
    P, C, mpp = road_graph(key)
    kdt = cKDTree(P)
    n = len(P)
    node_of = lambda x, y: int(kdt.query([x, y])[1])

    net = load_json(f'{vdir(key)}/network_hh2.json')
    root = node_of(net['anchor']['x'], net['anchor']['y'])

    # --- дерево сети: множество рёбер (id узлов) ---
    edges = set()
    for e in net['feeder_edges']:
        u, w = node_of(e[0][0], e[0][1]), node_of(e[1][0], e[1][1])
        if u != w:
            edges.add((min(u, w), max(u, w)))

    dC, predC = dijkstra(C, indices=root, return_predecessors=True)
    predC = predC.astype(np.int64)

    def tree_matrix(edges):
        r, c, v = [], [], []
        for (u, w) in edges:
            l = elen(P, mpp, u, w)
            r += [u, w]; c += [w, u]; v += [l, l]
        return csr_matrix((v, (r, c)), shape=(n, n))

    dU = dijkstra(tree_matrix(edges), indices=root)

    # --- муфты: старый id -> узел нового графа ---
    coup_node = {}                     # old_id -> new node
    for c in net['couplers']:
        coup_node[c['node']] = node_of(c['x'], c['y'])

    # --- 1) детур-гард ствола ---
    n_fix = 0
    for c in net['couplers']:
        t_ = coup_node[c['node']]
        dt, ds = dU[t_], dC[t_]
        if not np.isfinite(ds) or ds <= 1e-9 or not np.isfinite(dt):
            continue
        if dt > (1.0 + EPS) * ds and (dt - ds) > MIN_M:
            cur = t_
            g = 0
            while cur != root and predC[cur] >= 0 and g < n:
                p = int(predC[cur])
                edges.add((min(p, cur), max(p, cur)))
                cur = p
                g += 1
            n_fix += 1
    dU = dijkstra(tree_matrix(edges), indices=root)
    if n_fix:
        print(f'  детур-гард: добавлены кратчайшие пути для {n_fix} муфт')

    # --- 2) переназначение ДХ + дропы кратчайшими уличными путями ---
    # разбивка исходного дропа на уличный префикс (точки на графе) и
    # дворовой суффикс; домовой узел = последний снап-узел
    drops_in = net['drops']
    house_node, yard_tail = {}, {}
    for d in drops_in:
        poly = d['poly']
        last_i = None
        for i, p in enumerate(poly):
            dist, idx = kdt.query([p[0], p[1]])
            if dist <= SNAP_PX:
                last_i = i
                house_node[d['hh_id']] = int(idx)
            else:
                break
        if last_i is None:
            dist, idx = kdt.query([poly[0][0], poly[0][1]])
            house_node[d['hh_id']] = int(idx)
            yard_tail[d['hh_id']] = poly[1:] or [poly[-1]]
        else:
            yard_tail[d['hh_id']] = poly[last_i + 1:] or []

    serv = {}                          # hh_id -> coupler old_id
    for _round in range(3):
        cand = sorted(set(list(coup_node.values()) + [root]))
        row = {c: i for i, c in enumerate(cand)}
        Dc, pc = dijkstra(C, indices=cand, return_predecessors=True)
        pc = pc.astype(np.int64)
        by_node = {v: k for k, v in coup_node.items()}    # new node -> old id
        serv = {}
        need_int = []
        for d in drops_in:
            hid = d['hh_id']
            hn = house_node[hid]
            best, bd = None, None
            for c in cand:
                dd = Dc[row[c]][hn]
                if np.isfinite(dd) and (bd is None or dd < bd - 1e-9):
                    best, bd = c, float(dd)
            serv[hid] = by_node.get(best, None) if best != root else None
            yard_l = sum(math.hypot(yard_tail[hid][k + 1][0] - yard_tail[hid][k][0],
                                    yard_tail[hid][k + 1][1] - yard_tail[hid][k][1])
                         for k in range(len(yard_tail[hid]) - 1)) * mpp \
                if len(yard_tail[hid]) >= 2 else 0.0
            if best is None or bd + yard_l > MAX_DROP_M:
                need_int.append((d, best, bd))
        if not need_int or _round == 2:
            break
        # промежуточные муфты + продление ствола вдоль кратчайшего пути
        ext = False
        next_id = (max(coup_node) + 1) if coup_node else 0
        for d, sc_node, _bd in need_int:
            if sc_node is None:
                continue
            hn = house_node[d['hh_id']]
            r = row[sc_node]
            path = [hn]
            cur = hn
            g = 0
            while cur != sc_node and pc[r][cur] >= 0 and g < n:
                cur = int(pc[r][cur])
                path.append(cur)
                g += 1
            if cur != sc_node:
                continue
            path.reverse()                       # sc -> ... -> дом
            acc = 0.0
            first_c = None
            for i in range(len(path) - 2, -1, -1):
                u, w = path[i], path[i + 1]
                acc += elen(P, mpp, u, w)
                if acc >= INTERM and w != sc_node:
                    coup_node[next_id] = w
                    next_id += 1
                    if first_c is None:
                        first_c = w
                    acc = 0.0
            if first_c is None:
                continue
            fi = path.index(first_c)
            for i in range(fi + 1):
                u, w = path[i], path[i + 1]
                k = (min(u, w), max(u, w))
                if k not in edges:
                    edges.add(k)
                    ext = True
        if ext:
            dU = dijkstra(tree_matrix(edges), indices=root)

    # --- финальные пути дропов (одна Дейкстра от всех муфт) ---
    cand = sorted(set(list(coup_node.values()) + [root]))
    row = {c: i for i, c in enumerate(cand)}
    _, pcF = dijkstra(C, indices=cand, return_predecessors=True)
    pcF = pcF.astype(np.int64)
    by_node = {v: k for k, v in coup_node.items()}

    drops_out = []
    served_by = {}                       # old_id -> [hh_id...]
    for d in drops_in:
        hid = d['hh_id']
        hn = house_node[hid]
        sc_old = serv.get(hid)
        sc_node = coup_node.get(sc_old) if sc_old is not None else root
        if sc_node not in row:
            sc_node = root
        poly = []
        if sc_node == hn:
            poly = [[float(P[hn][0]), float(P[hn][1])]]
        else:
            r = row[sc_node]
            rev = [hn]
            cur = hn
            g = 0
            while cur != sc_node and pcF[r][cur] >= 0 and g < n:
                cur = int(pcF[r][cur])
                rev.append(cur)
                g += 1
            if cur == sc_node:
                poly = [[float(P[j][0]), float(P[j][1])]
                        for j in reversed(rev)]
            else:
                poly = list(d['poly'])          # fallback: старая геометрия
        poly = poly + [list(t) for t in yard_tail[hid]]
        if len(poly) < 2:
            poly = list(d['poly'])
        L = sum(math.hypot(poly[k + 1][0] - poly[k][0],
                           poly[k + 1][1] - poly[k][1])
                for k in range(len(poly) - 1)) * mpp
        sc_final = by_node.get(sc_node, None)
        drops_out.append(dict(hh=d['hh'], hh_id=hid, coupler=sc_final,
                              poly=poly, length_m=round(L, 1)))
        if sc_final is not None:
            served_by.setdefault(sc_final, []).append(hid)

    # --- 3) чистка пустых муфт (не точек ветвления) ---
    deg = {}
    for (u, w) in edges:
        deg[u] = deg.get(u, 0) + 1
        deg[w] = deg.get(w, 0) + 1
    kept = []
    for c in net['couplers']:
        if served_by.get(c['node']) or deg.get(coup_node[c['node']], 0) >= 3:
            kept.append(c)
    for old_id, node in list(coup_node.items()):
        if old_id not in {c['node'] for c in net['couplers']}:
            if served_by.get(old_id) or deg.get(node, 0) >= 3:
                kept.append(dict(node=old_id,
                                 x=float(P[node][0]), y=float(P[node][1]),
                                 label=f'M{old_id}'))
    kept_nodes = sorted({coup_node[c['node']] for c in kept})
    # перенумерация: последовательные id по порядку узлов
    new_id = {nd: i + 1 for i, nd in enumerate(kept_nodes)}
    couplers_out = [dict(node=new_id[nd],
                         x=float(P[nd][0]), y=float(P[nd][1]),
                         label=f'M{i + 1}')
                    for i, nd in enumerate(kept_nodes)]
    node2new = {}
    for c in kept:
        nd = coup_node[c['node']]
        node2new[nd] = new_id[nd]
    for d in drops_out:
        if d['coupler'] is not None:
            d['coupler'] = node2new.get(coup_node.get(d['coupler']), d['coupler'])

    # --- финальный ствол: объединение путей муфта->ЦУ по финальному дереву ---
    _, predU = dijkstra(tree_matrix(edges), indices=root,
                        return_predecessors=True)
    predU = predU.astype(np.int64)
    used = set()
    for nd in kept_nodes:
        cur = nd
        g = 0
        while cur != root and predU[cur] >= 0 and g < n:
            p = int(predU[cur])
            used.add((min(p, cur), max(p, cur)))
            cur = p
            g += 1
    feeder_edges = [[[float(P[u][0]), float(P[u][1])],
                     [float(P[w][0]), float(P[w][1])]] for (u, w) in sorted(used)]
    feeder_m = sum(elen(P, mpp, u, w) for (u, w) in used)
    drop_m = sum(d['length_m'] for d in drops_out)

    # --- детур-контроль результата ---
    dU2 = dijkstra(tree_matrix(used), indices=root)
    rs = []
    for nd in kept_nodes:
        if np.isfinite(dC[nd]) and dC[nd] > 1 and np.isfinite(dU2[nd]):
            rs.append(dU2[nd] / dC[nd])
    rs.sort()
    if rs:
        print(f'  муфт {len(kept)}, дропов {len(drops_out)}; '
              f'detour med {rs[len(rs)//2]:.3f} p90 {rs[int(0.9*len(rs))]:.3f} '
              f'max {rs[-1]:.3f}')
    print(f'  магистраль {feeder_m/1000:.2f} км, дропы {drop_m/1000:.2f} км, '
          f'ср. {drop_m/max(1,len(drops_out)):.1f} м, '
          f'макс {max((d["length_m"] for d in drops_out), default=0):.1f} м')

    st = dict(net['stats'])
    st.update(couplers=len(kept), feeder_km=round(feeder_m / 1000, 2),
              drop_km=round(drop_m / 1000, 2),
              avg_drop_m=round(drop_m / max(1, len(drops_out)), 1),
              max_drop_m=round(max((d['length_m'] for d in drops_out),
                                   default=0), 1),
              served=len(drops_out))
    out = dict(net)
    out.update(couplers=couplers_out, feeder_edges=feeder_edges,
               drops=drops_out, stats=st)
    save_json(f'{vdir(key)}/network_hh3.json', out)


if __name__ == '__main__':
    keys = sys.argv[1:] or ['all']
    if keys == ['all']:
        keys = [v['key'] for v in VILLAGES]
    for k in keys:
        process(k)
