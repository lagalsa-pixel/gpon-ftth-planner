#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проектирование FTTH v2 (централизованная древовидная архитектура):
- ОРШ в геометрической медиане ДХ, привязан к улице
- сшивка разрывов уличного графа (компоненты, гэпы <= 120 м)
- кабельное дерево: MST терминалов в метрике графа (Дейкстра), объединение путей
- отсечение бесполезных листьев
- муфты: разветвления (степень >= 3) + терминальные группы (<= 70 м)
- дропы: ДХ -> ближайшая терминальная муфта (прямая x1.2)
- волоконность по числу абонентов вниз по дереву (+15%)
Выход: work/net/<Имя>.json"""
import json, math, os
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra, connected_components

WORK = '/home/z/my-project/work'
os.makedirs(f'{WORK}/net', exist_ok=True)

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

ROAD_KEEP = {'residential', 'unclassified', 'living_street', 'service', 'tertiary',
             'secondary', 'primary', 'track', 'pedestrian'}
ROAD_COST = {'residential': 1.0, 'unclassified': 1.0, 'living_street': 1.0, 'service': 1.15,
             'tertiary': 1.0, 'secondary': 1.05, 'primary': 1.1, 'track': 1.6, 'pedestrian': 1.3}
FIBER_STD = [8, 12, 16, 24, 32, 48, 64, 72, 96, 144, 192]
DROP_K = 1.2
GROUP_SPAN = 70.0
ACCESS_R = 250.0
NODE_TOL = 8.0

class Graph:
    def __init__(self):
        self.pts = []
        self._grid = {}
        self.adj = []
        self.edges = []
        self.cells = {}  # пространственный индекс рёбер (обновляется при добавлении)
    def node(self, x, y):
        # поиск существующего узла в радиусе NODE_TOL через сетку
        cx, cy = int(x // NODE_TOL), int(y // NODE_TOL)
        for i in range(cx - 1, cx + 2):
            for j in range(cy - 1, cy + 2):
                for nid in self._grid.get((i, j), []):
                    px, py = self.pts[nid]
                    if (px - x) ** 2 + (py - y) ** 2 <= NODE_TOL ** 2:
                        return nid
        nid = len(self.pts)
        self.pts.append((x, y))
        self._grid.setdefault((cx, cy), []).append(nid)
        self.adj.append([])
        return nid
    def add_edge(self, u, v, w, pts, rtype):
        eid = len(self.edges)
        self.edges.append((u, v, w, pts, rtype))
        self.adj[u].append((v, eid))
        self.adj[v].append((u, eid))
        for p in pts[::2]:
            self.cells.setdefault((int(p[0] // 200), int(p[1] // 200)), set()).add(eid)
        return eid
    def compact(self):
        keep = [i for i, e in enumerate(self.edges) if e is not None]
        remap = {old: new for new, old in enumerate(keep)}
        self.edges = [self.edges[i] for i in keep]
        for i in range(len(self.adj)):
            self.adj[i] = [(o, remap[e]) for o, e in self.adj[i] if e in remap]
    def csr(self):
        N = len(self.pts)
        rows, cols, vals = [], [], []
        for u, v, w, _, _ in self.edges:
            rows += [u, v]; cols += [v, u]; vals += [w, w]
        return csr_matrix((vals, (rows, cols)), shape=(N, N)), N
    def bridge_components(self, max_gap=120.0):
        """сшивка компонент ближайшими узлами (гэп <= max_gap)"""
        M, N = self.csr()
        ncomp, lab = connected_components(M, directed=False)
        merged = True
        while merged and ncomp > 1:
            merged = False
            comps = {}
            for i in range(N):
                comps.setdefault(lab[i], []).append(i)
            main = max(comps, key=lambda c: len(comps[c]))
            main_arr = np.array(comps[main])
            best = (max_gap, None, None)
            for c, nodes in comps.items():
                if c == main or not nodes:
                    continue
                arr = np.array(nodes)
                # ближайшая пара узлов (грубая сетка для скорости)
                if len(main_arr) * len(arr) > 4_000_000:
                    step = max(1, len(arr) // 2000)
                    arr = arr[::step]
                d = np.sqrt(((np.array([self.pts[i] for i in arr])[:, None, :] -
                              np.array([self.pts[i] for i in main_arr])[None, :, :]) ** 2).sum(-1))
                idx = np.unravel_index(np.argmin(d), d.shape)
                if d[idx] < best[0]:
                    best = (d[idx], arr[idx[0]], main_arr[idx[1]])
            if best[1] is not None:
                a, b = best[1], best[2]
                w = math.hypot(self.pts[a][0] - self.pts[b][0], self.pts[a][1] - self.pts[b][1])
                self.add_edge(a, b, w * 1.2, [self.pts[a], self.pts[b]], 'gap')
                # обновить метки
                M, N = self.csr()
                ncomp, lab = connected_components(M, directed=False)
                merged = True
        return ncomp

def weiszfeld(pts, wts, iters=80):
    x = float(np.average(pts[:, 0], weights=wts))
    y = float(np.average(pts[:, 1], weights=wts))
    for _ in range(iters):
        d = np.maximum(np.sqrt((pts[:, 0] - x) ** 2 + (pts[:, 1] - y) ** 2), 0.5)
        wx = wts / d
        nx = float(np.sum(pts[:, 0] * wx) / np.sum(wx))
        ny = float(np.sum(pts[:, 1] * wx) / np.sum(wx))
        if abs(nx - x) < 0.01 and abs(ny - y) < 0.01:
            break
        x, y = nx, ny
    return x, y

def proj_on_polyline(pt, pts):
    """проекция на полилинию: (t_доли_длины, дистанция)"""
    total = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1))
    if total == 0:
        return 0.0, math.hypot(pt[0]-pts[0][0], pt[1]-pts[0][1])
    best = (0.0, 1e18)
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        ax, ay = b[0]-a[0], b[1]-a[1]
        L2 = ax*ax + ay*ay
        if L2 == 0:
            continue
        t = max(0.0, min(1.0, ((pt[0]-a[0])*ax + (pt[1]-a[1])*ay) / L2))
        px, py = a[0]+t*ax, a[1]+t*ay
        d = math.hypot(pt[0]-px, pt[1]-py)
        if d < best[1]:
            best = (t, d, (acc + t*math.sqrt(L2)) / total)
        acc += math.sqrt(L2)
    return best[2], best[1]  # глобальная доля длины полилинии, дистанция

def split_edge_at(g, eid, t):
    """t - доля ГЕОМЕТРИЧЕСКОЙ длины. Веса новых рёбер сохраняют коэффициент стоимости."""
    u, v, w, pts, rt = g.edges[eid]
    G = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1))
    if G <= 0:
        return g.node(*pts[0])
    factor = w / G
    acc = 0.0
    seg1 = [pts[0]]; seg2 = []; ins = pts[-1]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        if seg2 == [] and acc + L >= t * G and L > 0:
            f = (t*G - acc) / L
            ins = (a[0]+f*(b[0]-a[0]), a[1]+f*(b[1]-a[1]))
            seg1.append(ins)
            seg2 = [ins] + pts[i+1:]
        acc += L
        if seg2 == []:
            seg1.append(b)
    if len(seg2) < 2:
        ins = pts[-1]
        seg2 = [ins, pts[-1]]
        seg1 = pts[:]
    ni = g.node(*ins)
    if ni in (u, v):
        return ni
    g1 = sum(math.hypot(seg1[i+1][0]-seg1[i][0], seg1[i+1][1]-seg1[i][1]) for i in range(len(seg1)-1))
    g2 = sum(math.hypot(seg2[i+1][0]-seg2[i][0], seg2[i+1][1]-seg2[i][1]) for i in range(len(seg2)-1))
    if g1 < 0.05 or g2 < 0.05:
        return ni
    g.adj[u] = [(o, e2) for o, e2 in g.adj[u] if e2 != eid]
    g.adj[v] = [(o, e2) for o, e2 in g.adj[v] if e2 != eid]
    g.edges[eid] = None
    g.add_edge(u, ni, g1 * factor, seg1, rt)
    g.add_edge(ni, v, g2 * factor, seg2, rt)
    return ni

def build_for(name):
    snp = next(s for s in SNPS if s['name'] == name)
    lat0, lon0 = snp['lat'], snp['lon']
    mx = 111320 * math.cos(math.radians(lat0)); my = 111132.0
    with open(f'{WORK}/osm_data.json', encoding='utf-8') as f:
        osm = json.load(f)[name]
    hh_all = json.load(open(f'{WORK}/hh/{name}.json'))
    households = hh_all['households']
    objects = hh_all['objects']

    hpts = np.array([[(h['lon']-lon0)*mx, (h['lat']-lat0)*my] for h in households])
    keep_idx, isolated = [], 0
    for i in range(len(households)):
        d2 = ((hpts[:, 0]-hpts[i, 0])**2 + (hpts[:, 1]-hpts[i, 1])**2)
        d2[i] = 1e18
        if d2.min() <= 500**2:
            keep_idx.append(i)
        else:
            isolated += 1
    households = [households[i] for i in keep_idx]

    # --- уличный граф ---
    g = Graph()
    for r in osm['roads']:
        rt = r['tags'].get('highway', '')
        if rt not in ROAD_KEEP:
            continue
        pts_m = [((lo-lon0)*mx, (la-lat0)*my) for la, lo in r['geom']]
        thin = [pts_m[0]]
        for p in pts_m[1:-1]:
            if math.hypot(p[0]-thin[-1][0], p[1]-thin[-1][1]) > 4:
                thin.append(p)
        thin.append(pts_m[-1])
        if len(thin) < 2:
            continue
        L = sum(math.hypot(thin[i+1][0]-thin[i][0], thin[i+1][1]-thin[i][1]) for i in range(len(thin)-1))
        if L < 1:
            continue
        u, v = g.node(*thin[0]), g.node(*thin[-1])
        if v != u:
            g.add_edge(u, v, L * ROAD_COST[rt], thin, rt)
    ncomp = int(g.bridge_components(250.0))

    # --- терминалы ---
    terms = []
    for h in households:
        terms.append(((h['lon']-lon0)*mx, (h['lat']-lat0)*my, h['units'], 'hh', h))
    for o in objects:
        if o.get('area', 0) > 120:
            terms.append(((o['lon']-lon0)*mx, (o['lat']-lat0)*my, 1, 'obj', o))

    # --- ОРШ ---
    wts = np.array([t[2] for t in terms], float)
    tpts = np.array([[t[0], t[1]] for t in terms])
    ox, oy = weiszfeld(tpts, wts)
    best = (1e18, None, None)
    for eid, e in enumerate(g.edges):
        if e is None: continue
        t, d = proj_on_polyline((ox, oy), e[3])
        if d < best[0]:
            best = (d, eid, t)
    if best[1] is None or best[0] > 400:
        orsh_node = g.node(ox, oy)
        d, nid = min((math.hypot(ox-g.pts[i][0], oy-g.pts[i][1]), i) for i in range(len(g.pts)))
        g.add_edge(orsh_node, nid, d, [(ox, oy), g.pts[nid]], 'synthetic')
    else:
        orsh_node = split_edge_at(g, best[1], best[2])

    # --- привязка терминалов ---
    CELL = 200.0
    def near_edges(pt, rad=320):
        cx, cy = int(pt[0]//CELL), int(pt[1]//CELL)
        r = int(rad//CELL) + 1
        out = set()
        for i in range(cx-r, cx+r+1):
            for j in range(cy-r, cy+r+1):
                out |= g.cells.get((i, j), set())
        return out

    term_nodes = []
    synth = 0
    for (tx, ty, units, kind, ref) in terms:
        best = (1e18, None, None)
        for eid in near_edges((tx, ty)):
            e = g.edges[eid]
            if e is None: continue
            t, d = proj_on_polyline((tx, ty), e[3])
            if d < best[0]:
                best = (d, eid, t)
        if best[1] is None or best[0] > ACCESS_R:
            d, nid = min((math.hypot(tx-g.pts[i][0], ty-g.pts[i][1]), i) for i in range(len(g.pts)))
            ni = g.node(tx, ty)
            if ni != nid:
                g.add_edge(ni, nid, d * 1.5, [(tx, ty), g.pts[nid]], 'synthetic')
            term_nodes.append((ni, units, kind, ref))
            synth += 1
        else:
            ni = split_edge_at(g, best[1], best[2])
            term_nodes.append((ni, units, kind, ref))
            if os.environ.get('NET_DEBUG') == '1':
                npx, npy = g.pts[ni]
                if math.hypot(npx-tx, npy-ty) > 300:
                    e = g.edges[best[1]] if best[1] < len(g.edges) else None
                    print(f"  [SNAP-DBG] дом ({tx:.0f},{ty:.0f}) -> узел {ni} ({npx:.0f},{npy:.0f}) "
                          f"| проекция была {best[0]:.0f} м, t={best[2]:.3f}, ребро {best[1]}: "
                          f"{('None' if e is None else (round(e[2]), e[4], len(e[3])))}")
    g.compact()

    # компонентный анализ: связываем островки с компонентой ОРШ
    M0, N0 = g.csr()
    nc0, lab0 = connected_components(M0, directed=False)
    orsh_comp = lab0[orsh_node]
    comp_grid = {}
    for i in range(N0):
        if lab0[i] == orsh_comp:
            p = g.pts[i]
            comp_grid.setdefault((int(p[0] // 100), int(p[1] // 100)), []).append(i)
    def nearest_in_orsh(p):
        best = (1e18, None)
        cx, cy = int(p[0] // 100), int(p[1] // 100)
        for r in range(0, 80):
            for i in range(cx - r, cx + r + 1):
                for j in range(cy - r, cy + r + 1):
                    for u in comp_grid.get((i, j), []):
                        q = g.pts[u]
                        d = math.hypot(q[0] - p[0], q[1] - p[1])
                        if d < best[0]:
                            best = (d, u)
            if best[1] is not None and best[0] < r * 100:
                break
        return best
    far_links = 0
    term_comps = {}
    for tn in term_nodes:
        term_comps.setdefault(lab0[tn[0]], []).append(tn[0])
    for c, nodes in term_comps.items():
        if c == orsh_comp:
            continue
        # ближайший узел островка к компоненте ОРШ
        best = (1e18, None, None)
        for n in set(nodes):
            d, u = nearest_in_orsh(g.pts[n])
            if d < best[0]:
                best = (d, n, u)
        if best[2] is not None:
            a, b = best[1], best[2]
            g.add_edge(a, b, best[0] * 1.5, [g.pts[a], g.pts[b]], 'far_link')
            far_links += 1
    if far_links:
        g.compact()

    M, N = g.csr()
    terminals = [orsh_node] + [tn[0] for tn in term_nodes]
    uniq_t = sorted(set(terminals))
    ti = {n: k for k, n in enumerate(uniq_t)}
    D, pred = dijkstra(M, directed=False, indices=uniq_t, return_predecessors=True)

    # MST терминалов (Прим) в метрике графа
    K = len(uniq_t)
    root_k = ti[orsh_node]
    DT = D[:, uniq_t]
    INF = 1e18
    dist = DT[root_k].copy(); dist[root_k] = 0
    in_t = np.zeros(K, bool); in_t[root_k] = True
    mst = []
    unreachable = 0
    for _ in range(K - 1):
        d = dist.copy(); d[in_t] = INF
        k = int(np.argmin(d))
        if d[k] >= INF or not np.isfinite(d[k]):
            # недостижимый терминал — прямая синтетическая линия к дереву
            unreachable += 1
            in_t[k] = True
            continue
        row = DT[k]
        _, par = min((row[j], j) for j in range(K) if in_t[j])
        mst.append((par, k))
        in_t[k] = True
        dist = np.minimum(dist, DT[k])

    # объединение кратчайших путей
    tree_eids = set()
    for (a, b) in mst:
        cur, target = uniq_t[b], uniq_t[a]
        pr = pred[a]
        guard = 0
        while cur != target and cur >= 0 and guard < 100000:
            nxt = pr[cur]
            for o, e2 in g.adj[cur]:
                if o == nxt:
                    tree_eids.add(e2)
                    break
            cur = nxt
            guard += 1

    # дерево: БФС от ОРШ
    adj_t = {}
    for e2 in tree_eids:
        u, v, w, pts, rt = g.edges[e2]
        adj_t.setdefault(u, []).append((v, e2))
        adj_t.setdefault(v, []).append((u, e2))
    parent = {orsh_node: (None, None)}
    order = [orsh_node]
    qq = [orsh_node]
    while qq:
        c = qq.pop(0)
        for o, e2 in adj_t.get(c, []):
            if o not in parent:
                parent[o] = (c, e2)
                order.append(o)
                qq.append(o)

    # отсечение листьев без терминалов
    term_set = set(tn[0] for tn in term_nodes)
    deg = {u: len(adj_t[u]) for u in adj_t}
    changed = True
    while changed:
        changed = False
        for u in list(deg.keys()):
            if deg.get(u, 0) == 1 and u not in term_set and u != orsh_node:
                for o, e2 in adj_t[u]:
                    if deg.get(o, 0) > 0:
                        deg[o] -= 1
                del deg[u]
                changed = True
    tree_eids = {e2 for e2 in tree_eids
                 if g.edges[e2][0] in deg and g.edges[e2][1] in deg}
    adj_t = {}
    for e2 in tree_eids:
        u, v, w, pts, rt = g.edges[e2]
        adj_t.setdefault(u, []).append((v, e2))
        adj_t.setdefault(v, []).append((u, e2))
    tree_len = sum(g.edges[e2][2] for e2 in tree_eids)

    # волоконность
    kids = {}
    for u in adj_t:
        for o, e2 in adj_t[u]:
            if parent.get(o, (None, None))[0] == u:
                kids.setdefault(u, []).append(o)
    node_units = {}
    for tn in term_nodes:
        node_units[tn[0]] = node_units.get(tn[0], 0) + tn[1]
    down = {}
    for u in reversed(order):
        s = node_units.get(u, 0)
        for o in kids.get(u, []):
            s += down.get(o, 0)
        down[u] = s
    seg_fibers = {}
    for e2 in tree_eids:
        u, v, w, pts, rt = g.edges[e2]
        lo = v if parent.get(v, (None,))[0] == u else u
        n_ab = down.get(lo, 0)
        need = max(2, math.ceil(n_ab * 1.15)) if n_ab > 0 else 8
        seg_fibers[e2] = next((f for f in FIBER_STD if f >= need), FIBER_STD[-1])

    # муфты: разветвления
    branch_nodes = [u for u in adj_t if len(adj_t[u]) >= 3]

    # терминальные группы (кластеризация по близости)
    tp = np.array([[g.pts[tn[0]][0], g.pts[tn[0]][1]] for tn in term_nodes])
    used = np.zeros(len(term_nodes), bool)
    groups = []
    for i in range(len(term_nodes)):
        if used[i]: continue
        comp = [i]; used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(len(term_nodes)):
                if used[j]: continue
                dd = np.sqrt(((tp[comp] - tp[j])**2).sum(1))
                if dd.min() <= GROUP_SPAN * 0.5:
                    comp.append(j); used[j] = True; changed = True
        groups.append(comp)

    # узлы дерева в kd-подобной сетке для быстрого поиска ближайшего
    tgrid = {}
    for u in deg:
        p = g.pts[u]
        tgrid.setdefault((int(p[0]//50), int(p[1]//50)), []).append(u)
    def nearest_tree_node(x, y):
        best = (1e18, None)
        cx, cy = int(x//50), int(y//50)
        for r in range(0, 12):
            found = False
            for i in range(cx-r, cx+r+1):
                for j in range(cy-r, cy+r+1):
                    for u in tgrid.get((i, j), []):
                        p = g.pts[u]
                        d = math.hypot(p[0]-x, p[1]-y)
                        if d < best[0]:
                            best = (d, u); found = True
            if best[1] is not None and best[0] < r * 50:
                break
        return best[1]

    muftas = []
    drop_total = 0.0
    drop_lens = []
    DEBUG = os.environ.get('NET_DEBUG') == '1'
    for comp in groups:
        gx = float(np.median([tp[j][0] for j in comp]))
        gy = float(np.median([tp[j][1] for j in comp]))
        mu = nearest_tree_node(gx, gy)
        if mu is None:
            if DEBUG:
                print(f"  [DBG] группа без муфты: медиана ({gx:.0f},{gy:.0f}), n={len(comp)}, "
                      f"терм.узлы в deg: {[term_nodes[j][0] in deg for j in comp]}")
            continue
        if DEBUG:
            dmu = math.hypot(g.pts[mu][0]-gx, g.pts[mu][1]-gy)
            if dmu > 100:
                print(f"  [DBG] группа ({gx:.0f},{gy:.0f}) n={len(comp)}: муфта в ({g.pts[mu][0]:.0f},{g.pts[mu][1]:.0f}) "
                      f"в {dmu:.0f} м! терм-узлы: {[(term_nodes[j][0], term_nodes[j][0] in deg) for j in comp[:3]]}")
        mxp, myp = g.pts[mu]
        drops = []
        for j in comp:
            tn = term_nodes[j]
            hh = tn[3]
            hx, hy = (hh['lon']-lon0)*mx, (hh['lat']-lat0)*my
            L = math.hypot(hx-mxp, hy-myp) * DROP_K
            drop_total += L
            drop_lens.append(L)
            drops.append({'len': round(L, 1), 'kind': tn[2],
                          'x': round(hx, 1), 'y': round(hy, 1),
                          'lat': hh['lat'], 'lon': hh['lon']})
        muftas.append({'x': round(mxp, 1), 'y': round(myp, 1), 'node': mu,
                       'kind': 'branch' if mu in branch_nodes else 'terminal', 'drops': drops})
    # чисто разветвительные муфты (без дропов)
    with_drops = {m['node'] for m in muftas}
    for u in branch_nodes:
        if u not in with_drops:
            muftas.append({'x': round(g.pts[u][0], 1), 'y': round(g.pts[u][1], 1), 'node': u,
                           'kind': 'branch', 'drops': []})

    n_branch = sum(1 for m in muftas if m['kind'] == 'branch')
    n_term = sum(1 for m in muftas if m['kind'] == 'terminal')
    n_hh = sum(tn[1] for tn in term_nodes if tn[2] == 'hh')
    n_obj = sum(1 for tn in term_nodes if tn[2] == 'obj')

    # распределение длин кабеля по волоконности
    fib_km = {}
    for e2 in tree_eids:
        f = seg_fibers[e2]
        fib_km[f] = fib_km.get(f, 0) + g.edges[e2][2]

    stats = {
        'households': n_hh, 'expected': snp['households'], 'objects': n_obj,
        'isolated_farms': isolated, 'graph_components': ncomp,
        'tree_len_m': round(tree_len, 1), 'fiber_km': {str(k): round(v/1000, 2) for k, v in sorted(fib_km.items())},
        'orsh_xy': [round(g.pts[orsh_node][0], 1), round(g.pts[orsh_node][1], 1)],
        'muftas_branch': n_branch, 'muftas_terminal': n_term, 'muftas_total': len(muftas),
        'drops_n': len(drop_lens), 'drops_total_m': round(drop_total, 1),
        'drop_avg_m': round(drop_total/max(1, len(drop_lens)), 1),
        'drop_max_m': round(max(drop_lens), 1) if drop_lens else 0,
        'drop_p90_m': round(float(np.percentile(drop_lens, 90)), 1) if drop_lens else 0,
        'pon_ports': math.ceil(n_hh/32), 'synth_edges': synth, 'far_links': far_links, 'unreachable': unreachable,
    }
    print(f"{name}: ДХ {n_hh} (ожид. {snp['households']}) | дерево {tree_len/1000:.2f} км | "
          f"муфт {n_branch}+{n_term} | дропов {len(drop_lens)}, ср. {stats['drop_avg_m']} м, "
          f"p90 {stats['drop_p90_m']} м, макс {stats['drop_max_m']} м | синте {synth}, связок {far_links}, недост {unreachable}")

    out = {
        'stats': stats,
        'orsh': {'x': g.pts[orsh_node][0], 'y': g.pts[orsh_node][1],
                 'lat': lat0 + g.pts[orsh_node][1]/my, 'lon': lon0 + g.pts[orsh_node][0]/mx},
        'tree_edges': [{'pts': [[round(p[0],1), round(p[1],1)] for p in g.edges[e2][3]],
                        'w': round(g.edges[e2][2], 1), 'fibers': seg_fibers[e2],
                        'rt': g.edges[e2][4]} for e2 in tree_eids],
        'muftas': muftas,
    }
    with open(f'{WORK}/net/{name}.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, default=int)

for snp in SNPS:
    build_for(snp['name'])
