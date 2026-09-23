# -*- coding: utf-8 -*-
"""
Шаг 6v2. Проектирование FTTH-сети (централизованная древовидная архитектура):
- ОРШ на здании-якоре; дорожный граф OSM; MST терминалов -> SPT-дерево
- Муфты: слияние точек подключения (шаг ~40 м по улице), ВСЕ узлы ветвления (deg>=3),
  промежуточные при дропе > 120 м
- Дроп: от обслуживающей муфты вдоль улицы к усадьбе + по двору/фасаду (ломаная)
- Магистраль: объединение путей муфта->ОРШ
"""
import sys, os, math, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

MAX_DROP_M = 120.0
MERGE_M = 50.0          # радиус слияния точек подключения в одну муфту
DEDUP_M = 15.0          # слияние муфт ближе этого расстояния по дереву

def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)

class RoadGraph:
    def __init__(self):
        self.pts = []
        self.idx = {}
        self.edges = []

    def add_node(self, x, y):
        k = (round(x, 1), round(y, 1))
        i = self.idx.get(k)
        if i is None:
            i = len(self.pts)
            self.pts.append((x, y))
            self.idx[k] = i
        return i

    def add_polyline(self, pts_px, mpp):
        prev = None
        for p in pts_px:
            cur = self.add_node(p[0], p[1])
            if prev is not None and cur != prev:
                d = math.hypot(self.pts[cur][0] - self.pts[prev][0],
                               self.pts[cur][1] - self.pts[prev][1]) * mpp
                if d > 0.05:
                    self.edges.append((prev, cur, d))
            prev = cur

def build_network(key, verbose=True):
    v = [x for x in VILLAGES if x['key'] == key][0]
    g = load_json('/home/z/my-project/work/mosaic_geo.json')[key]
    d = load_json(f'{vdir(key)}/osm.json')
    hhs = load_json(f'{vdir(key)}/households.json')
    anchors = load_json('/home/z/my-project/work/anchor_candidates.json')[key]
    mpp, west, north = g['mpp'], g['west'], g['north']

    anchor = anchors[1] if key == 'solnechnoe' else anchors[0]
    ax, ay = anchor['x'], anchor['y']

    # --- дорожный граф ---
    G = RoadGraph()
    mstep = 4.0
    for r in d['roads']:
        pts = [geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
        if all(p[0] < -200 or p[0] > g['W'] + 200 or p[1] < -200 or p[1] > g['H'] + 200 for p in pts):
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
    n = len(P)
    if verbose:
        print(f"  граф: {n} узлов, {len(G.edges)} рёбер")

    # --- привязка ---
    tree = cKDTree(P)
    root_id = int(tree.query([ax, ay])[1])
    hh_nodes = [int(tree.query([h['cx'], h['cy']])[1]) for h in hhs]
    snap_d = [float(tree.query([h['cx'], h['cy']])[0]) * mpp for h in hhs]
    if verbose:
        sd = sorted(snap_d)
        print(f"  привязка ДХ к дорогам: медиана {sd[len(sd)//2]:.0f} м, p90 {sd[9*len(sd)//10]:.0f} м, макс {sd[-1]:.0f} м")

    terminals = list(dict.fromkeys([root_id] + hh_nodes))
    tpos = {t: i for i, t in enumerate(terminals)}

    rows, cols, vals = [], [], []
    for (u, w, l) in G.edges:
        rows += [u, w]; cols += [w, u]; vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(n, n))
    Dm, pred_m = dijkstra(C, indices=terminals, return_predecessors=True)

    # --- MST по метрике дорог ---
    K = len(terminals)
    Dt = np.array([[Dm[i][t] for t in terminals] for i in range(K)])
    in_tree = [False] * K
    best_w = [np.inf] * K
    parent = [-1] * K
    best_w[0] = 0.0
    mst_pairs = []
    for _ in range(K):
        b, bw = -1, np.inf
        for i in range(K):
            if not in_tree[i] and best_w[i] < bw:
                b, bw = i, best_w[i]
        if b < 0:
            break
        in_tree[b] = True
        if parent[b] >= 0:
            mst_pairs.append((terminals[parent[b]], terminals[b]))
        for j in range(K):
            if not in_tree[j] and Dt[b][j] < best_w[j]:
                best_w[j] = Dt[b][j]
                parent[j] = b

    # --- объединение путей -> SPT от корня ---
    union = set()
    for (u, w) in mst_pairs:
        iu = tpos[u]
        cur = w
        while cur != u and cur >= 0:
            p = int(pred_m[iu][cur])
            if p < 0:
                break
            union.add((min(p, cur), max(p, cur)))
            cur = p
    ur, uc, uv = [], [], []
    elen = {}
    for (u, w) in union:
        l = math.hypot(P[u][0] - P[w][0], P[u][1] - P[w][1]) * mpp
        elen[(u, w)] = l
        ur += [u, w]; uc += [w, u]; uv += [l, l]
    U = csr_matrix((uv, (ur, uc)), shape=(n, n))
    DU, predU = dijkstra(U, indices=root_id, return_predecessors=True)
    predU = predU.astype(np.int64)

    def path_to_root(node):
        """[node, ..., root] по дереву SPT; None если недостижим."""
        pth = [node]
        cur = node
        guard = 0
        while cur != root_id:
            p = int(predU[cur])
            if p < 0:
                return None
            pth.append(p)
            cur = p
            guard += 1
            if guard > n:
                return None
        return pth

    hh_paths = [path_to_root(nd) for nd in hh_nodes]
    n_unreach = sum(1 for p in hh_paths if p is None)
    if verbose and n_unreach:
        print(f"  ! недостижимых ДХ: {n_unreach}")

    # --- размещение муфт ---
    # 1) слияние точек подключения: обработка ДХ по возрастанию DU
    couplers = {}   # node -> [household idx]

    def add_coup(node, hi):
        couplers.setdefault(node, []).append(hi)

    order = sorted([i for i in range(len(hhs)) if hh_paths[i] is not None],
                   key=lambda i: DU[hh_nodes[i]])
    for hi in order:
        pth = hh_paths[hi]
        a_h = pth[0]
        # идём вверх по пути до MAX 40 м: ищем существующую муфту
        acc = 0.0
        serve = None
        for i in range(len(pth) - 1):
            e = (min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1]))
            if pth[i] in couplers:
                serve = pth[i]
                break
            acc += elen.get(e, 0)
            if acc > MERGE_M:
                break
        if serve is not None:
            add_coup(serve, hi)
        else:
            add_coup(a_h, hi)
    # 2) узлы ветвления ДЕРЕВА (deg>=3 по уникальным рёбрам) -> муфты
    tree_edges = set()
    for hi in order:
        pth = hh_paths[hi]
        for i in range(len(pth) - 1):
            tree_edges.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
    deg = {}
    for (u, w) in tree_edges:
        deg[u] = deg.get(u, 0) + 1
        deg[w] = deg.get(w, 0) + 1
    for node, dg in deg.items():
        if dg >= 3:
            couplers.setdefault(node, [])

    # 2b) дедупликация: муфты ближе DEDUP_M по дереву -> оставляем верхнюю (ветвление)
    def path_dist_nodes(a, b):
        """расстояние по дереву между узлами (0 если совпадают)"""
        if a == b:
            return 0.0
        pa = path_to_root(a)
        if pa is None or b not in pa:
            return 1e9
        ib = pa.index(b)   # b выше по пути
        return sum(elen.get((min(pa[i], pa[i + 1]), max(pa[i], pa[i + 1])), 0) for i in range(ib))

    changed = True
    while changed:
        changed = False
        nodes_c = sorted(couplers.keys(), key=lambda c: DU[c])
        for i in range(len(nodes_c)):
            if nodes_c[i] not in couplers:
                continue
            for j in range(i + 1, len(nodes_c)):
                a, b = nodes_c[i], nodes_c[j]   # a выше (меньше DU)
                if a not in couplers or b not in couplers:
                    continue
                dd = path_dist_nodes(b, a)
                if dd < DEDUP_M:
                    couplers[a].extend(couplers.pop(b))
                    changed = True
                    break
            if changed:
                break

    # --- обслуживающие муфты + промежуточные для длинных дропов ---
    def serving(hi):
        pth = hh_paths[hi]
        for i in range(len(pth)):
            if pth[i] in couplers:
                return pth[i]
        return root_id

    def drop_len(hi, sc):
        pth = hh_paths[hi]
        si = pth.index(sc)
        return sum(elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
                   for i in range(si))  # от муфты (si) вниз до a_h (0): рёбра (0..si-1)

    for hi in order:
        pth = hh_paths[hi]
        hh = hhs[hi]
        a_h = pth[0]
        yard = math.hypot(hh['cx'] - P[a_h][0], hh['cy'] - P[a_h][1]) * mpp
        sc = serving(hi)
        dl = drop_len(hi, sc) + yard
        while dl > MAX_DROP_M:
            # вставить муфту ~ на 100 м выше a_h
            acc = 0.0
            placed = None
            for i in range(len(pth) - 1):
                e = (min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1]))
                acc += elen.get(e, 0)
                if acc >= 100.0:
                    placed = pth[i + 1]
                    break
            if placed is None or placed in couplers or placed == sc:
                break
            couplers.setdefault(placed, [])
            sc = serving(hi)
            dl2 = drop_len(hi, sc)
            if dl2 >= dl:
                break
            dl = dl2 + yard

    # --- финальные обслуживаемые муфты и дропы ---
    # (после добавления ветвлений/промежуточных пересчитать обслуживающие)
    drops = []
    for hi, hh in enumerate(hhs):
        if hh_paths[hi] is None:
            continue
        pth = hh_paths[hi]
        sc = serving(hi)
        si = pth.index(sc)
        # полилиния: муфта -> a_h (индексы si..0)
        poly = [list(P[pth[i]]) for i in range(si, -1, -1)]
        # двор/фасад
        a_h = pth[0]
        entry = yard_polyline(hh, P[a_h], mpp)
        poly += entry
        dl = (sum(elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0) for i in range(si))
              + sum(math.hypot(entry[k + 1][0] - entry[k][0], entry[k + 1][1] - entry[k][1]) for k in range(len(entry) - 1)) * mpp)
        drops.append(dict(hh=hi, coupler=sc, poly=poly, length_m=round(dl, 1)))

    # --- магистраль: объединение путей муфта->корень ---
    feeder_edges = set()
    for c in couplers:
        pth = path_to_root(c)
        if pth is None:
            continue
        for i in range(len(pth) - 1):
            feeder_edges.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
    feeder_m = sum(elen.get(e, math.hypot(P[e[0]][0] - P[e[1]][0], P[e[0]][1] - P[e[1]][1]) * mpp)
                   for e in feeder_edges)
    drop_m = sum(dd['length_m'] for dd in drops)
    coup_list = sorted([c for c in couplers if c != root_id])
    stats = dict(households=len(hhs), served=len(drops),
                 couplers=len(coup_list),
                 feeder_km=round(feeder_m / 1000, 2), drop_km=round(drop_m / 1000, 2),
                 avg_drop_m=round(drop_m / max(1, len(drops)), 1),
                 max_drop_m=round(max((dd['length_m'] for dd in drops), default=0), 1))
    if verbose:
        print(f"  ОРШ: id={anchor['id']} ({anchor['area']:.0f} м²); обслужено {stats['served']}/{len(hhs)} ДХ")
        print(f"  муфт {stats['couplers']}, магистраль {stats['feeder_km']} км, дропы {stats['drop_km']} км, ср. дроп {stats['avg_drop_m']} м, макс {stats['max_drop_m']} м")

    couplers_out = [dict(node=int(c), x=float(P[c][0]), y=float(P[c][1]), label=f"М{i+1}")
                    for i, c in enumerate(coup_list)]
    feeder_out = [[[float(P[e[0]][0]), float(P[e[0]][1])], [float(P[e[1]][0]), float(P[e[1]][1])]]
                  for e in sorted(feeder_edges)]
    net = dict(anchor=dict(x=ax, y=ay, lat=anchor['lat'], lon=anchor['lon'],
                           bld_id=anchor['id'], area=anchor['area']),
               root_node=root_id, couplers=couplers_out,
               feeder_edges=feeder_out, drops=drops, stats=stats)
    save_json(f'{vdir(key)}/network.json', net)
    return net

def yard_polyline(hh, road_pt, mpp):
    """Дворовая прокладка: от дороги вдоль участка/забора, затем к стене дома."""
    hx, hy = hh['cx'], hh['cy']
    sx, sy = road_pt
    dx, dy = hx - sx, hy - sy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return [[sx, sy], [hx, hy]]
    hsh = int(hashlib.md5(str(hh['id']).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    f_along = 0.30 + 0.35 * hsh
    side = 1 if hsh > 0.5 else -1
    ux, uy = dx / dist, dy / dist
    px_, py_ = -uy, ux
    if dist * mpp < 10:
        m1 = [sx + dx * 0.55 + px_ * 2.5 * side, sy + dy * 0.55 + py_ * 2.5 * side]
        return [[sx, sy], m1, [hx, hy]]
    a1 = [sx + px_ * dist * f_along * 0.55 + ux * dist * 0.22,
          sy + py_ * dist * f_along * 0.55 + uy * dist * 0.22]
    a2 = [a1[0] + ux * dist * 0.5 + px_ * dist * 0.12 * side,
          a1[1] + uy * dist * 0.5 + py_ * dist * 0.12 * side]
    return [[sx, sy], a1, a2, [hx, hy]]

if __name__ == '__main__':
    for v in VILLAGES:
        print(f"=== {v['name']} ===")
        build_network(v['key'])
