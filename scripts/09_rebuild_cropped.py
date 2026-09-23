# -*- coding: utf-8 -*-
"""
Шаг 9. Перенос FTTH-сети на обрезанные пользователем кадры + оптимизация топологии.
Для каждого СНП (Солнечное, Пригородное, Алтайский):
 - рамка кадра в координатах исходной мозаики (из crop_transform.json)
 - перевыбор ОРШ в кадре, если прежний за рамкой (критерии шага 5)
 - клип дорожного графа по рамке (сеть остаётся в пределах кадра)
 - ДХ только внутри кадра
 - MST/SPT-дерево от ОРШ + ОПТИМИЗАЦИЯ топологии:
   1) привязка каждого ДХ к ближайшей ПО ДОРОГАМ муфте (а не только "вверх по дереву")
   2) удаление неиспользуемых муфт, не являющихся точками ветвления
   3) промежуточные муфты для дропов > 120 м + удлинение ствола вдоль трассы дропа
   4) итерации до стабилизации
Выход: work/<key>/network_v2.json (геометрия в координатах ИСХОДНОЙ мозаики)
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json, save_json
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'net06', os.path.join(os.path.dirname(__file__), '06_network.py'))
net06 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(net06)
RoadGraph = net06.RoadGraph
yard_polyline = net06.yard_polyline
geo_to_px = net06.geo_to_px

MAX_DROP_M = 120.0
MERGE_M = 50.0
DEDUP_M = 15.0
CAND_R_M = 200.0     # радиус (по прямой) поиска муфты для привязки ДХ
SNAP_MAX_M = 90.0    # макс. привязка ДХ к дороге
EPS_PX = 2.0

TASKS = ['perevalnoe', 'prigorodnoe', 'altaiskiy']
# Принудительный ОРШ по VLM-верификации (нежилое здание у развилки, самый центральный)
FORCE_ANCHOR = {'prigorodnoe': 688327498}
MAIN_ROADS = {'primary', 'secondary', 'tertiary', 'trunk', 'unclassified', 'residential'}
BASE = '/home/z/my-project'


def pick_anchor_in_crop(d, hhs, g, rect, mpp, verbose=True):
    """Перевыбор здания-якоря в рамках кадра (критерии шага 05_anchor)."""
    x0, y0, x1, y1 = rect
    west, north = g['west'], g['north']
    clat = sum(h['lat'] for h in hhs) / max(1, len(hhs))
    clon = sum(h['lon'] for h in hhs) / max(1, len(hhs))

    main_pts = []
    for r in d['roads']:
        if r['hw'] in MAIN_ROADS:
            prev = None
            for la, lo in r['pts']:
                p = geo_to_px(la, lo, west, north, mpp)
                if prev is not None:
                    seg = math.hypot(p[0] - prev[0], p[1] - prev[1]) * mpp
                    n_sub = int(seg / 10.0)
                    for k in range(n_sub + 1):
                        main_pts.append((prev[0] + (p[0] - prev[0]) * k / max(n_sub, 1),
                                         prev[1] + (p[1] - prev[1]) * k / max(n_sub, 1)))
                prev = p
    main_arr = np.array(main_pts) if main_pts else np.zeros((0, 2))

    def road_dist(x, y):
        if len(main_arr) == 0:
            return 999.0
        return math.sqrt(((main_arr[:, 0] - x) ** 2 + (main_arr[:, 1] - y) ** 2).min()) * mpp

    cands = []
    for b in d['buildings']:
        la, lo = b['center']
        x, y = geo_to_px(la, lo, west, north, mpp)
        if not (x0 + 15 <= x <= x1 - 15 and y0 + 15 <= y <= y1 - 15):
            continue
        area = b['area']
        tags = b.get('tags', {})
        bt = tags.get('building', 'yes')
        if bt in ('garage', 'garages', 'barn', 'shed', 'greenhouse', 'roof', 'kiosk', 'hut'):
            continue
        pts = [geo_to_px(pla, plo, west, north, mpp) for pla, plo in b['poly']]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        asp = max(bw, bh) / max(1e-6, min(bw, bh))
        compact = 1.0 if asp < 2.2 else (2.2 / asp)
        dcent_m = math.hypot((la - clat) * 111320, (lo - clon) * 111320 * math.cos(math.radians(la)))
        centr = max(0.0, 1.0 - dcent_m / 1200.0)
        sz = 1.0 if 150 <= area <= 500 else (0.75 if 90 <= area < 150 else (0.5 if 500 < area <= 900 else 0.25))
        rd = road_dist(x, y)
        road_s = 1.0 if rd < 25 else (0.6 if rd < 50 else (0.3 if rd < 90 else 0.1))
        tag_bonus = 1.4 if (tags.get('amenity') or bt in ('public', 'civic', 'commercial', 'retail', 'office')) else 1.0
        score = sz * centr * road_s * compact * tag_bonus
        cands.append(dict(id=b['id'], lat=la, lon=lo, x=x, y=y, area=area, score=score, tags=tags))
    cands.sort(key=lambda c: -c['score'])
    if verbose:
        print(f"  перевыбор ОРШ в кадре, топ-3:")
        for c in cands[:3]:
            print(f"    id={c['id']} {c['area']:.0f} м² score={c['score']:.3f} "
                  f"тег={c['tags'].get('building', '?')}/{c['tags'].get('name', '')}")
    return cands[0]


def rebuild(key, verbose=True):
    g = load_json(f'{BASE}/work/mosaic_geo.json')[key]
    t = load_json(f'{vdir(key)}/crop_transform.json')
    d = load_json(f'{vdir(key)}/osm.json')
    hhs_all = load_json(f'{vdir(key)}/households.json')
    old_net = load_json(f'{vdir(key)}/network.json')
    mpp, west, north = g['mpp'], g['west'], g['north']

    assert abs(t['rot_deg']) < 0.05, 'кадр повёрнут — требуется quad-тест точек'
    q = t['quad_old']
    x0 = min(p[0] for p in q); x1 = max(p[0] for p in q)
    y0 = min(p[1] for p in q); y1 = max(p[1] for p in q)
    rect = (x0, y0, x1, y1)

    # --- 1) ДХ в кадре ---
    hhs = [h for h in hhs_all if x0 <= h['cx'] <= x1 and y0 <= h['cy'] <= y1]
    hh_idx_map = {h['id']: i for i, h in enumerate(hhs)}   # id -> локальный индекс
    if verbose:
        print(f"  ДХ в кадре: {len(hhs)} из {len(hhs_all)}")

    # --- 2) ОРШ ---
    oa = old_net['anchor']
    anchor_changed = not (x0 <= oa['x'] <= x1 and y0 <= oa['y'] <= y1)
    if key in FORCE_ANCHOR:
        b = next(b for b in d['buildings'] if b['id'] == FORCE_ANCHOR[key])
        la, lo = b['center']
        x, y = geo_to_px(la, lo, west, north, mpp)
        anchor = dict(x=x, y=y, lat=la, lon=lo, bld_id=b['id'], area=b['area'])
        anchor_changed = anchor['bld_id'] != oa.get('bld_id')
        if verbose:
            print(f"  ОРШ: FORCED id={b['id']} ({b['area']:.0f} м²) по VLM-верификации")
    elif anchor_changed:
        a = pick_anchor_in_crop(d, hhs, g, rect, mpp, verbose)
        anchor = dict(x=a['x'], y=a['y'], lat=a['lat'], lon=a['lon'], bld_id=a['id'], area=a['area'])
    else:
        anchor = oa
    ax, ay = anchor['x'], anchor['y']
    if verbose:
        print(f"  ОРШ: id={anchor['bld_id']} ({anchor['area']:.0f} м²) "
              f"{'ПЕРЕВЫБРАН (прежний за кадром)' if anchor_changed else 'сохранён'}")

    # --- 3) дорожный граф, клип по кадру ---
    G = RoadGraph()
    mstep = 4.0
    for r in d['roads']:
        pts = [geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
        if all(p[0] < x0 - 200 or p[0] > x1 + 200 or p[1] < y0 - 200 or p[1] > y1 + 200 for p in pts):
            continue
        dens = [pts[0]]
        for p in pts[1:]:
            qq = dens[-1]
            seg = math.hypot(p[0] - qq[0], p[1] - qq[1]) * mpp
            n_sub = int(seg / mstep)
            for k in range(1, n_sub + 1):
                dens.append((qq[0] + (p[0] - qq[0]) * k / max(n_sub, 1),
                             qq[1] + (p[1] - qq[1]) * k / max(n_sub, 1)))
            if seg < mstep:
                dens.append(p)
        G.add_polyline(dens, mpp)
    P_all = np.array(G.pts)
    keep = (P_all[:, 0] >= x0 - EPS_PX) & (P_all[:, 0] <= x1 + EPS_PX) & \
           (P_all[:, 1] >= y0 - EPS_PX) & (P_all[:, 1] <= y1 + EPS_PX)
    remap = -np.ones(len(P_all), dtype=np.int64)
    remap[keep] = np.arange(int(keep.sum()))
    P = P_all[keep]
    edges = [(int(remap[u]), int(remap[w]), l) for (u, w, l) in G.edges if keep[u] and keep[w]]
    n = len(P)
    if verbose:
        print(f"  граф в кадре: {n} узлов, {len(edges)} рёбер (было {len(G.pts)} узлов)")

    rows, cols, vals = [], [], []
    for (u, w, l) in edges:
        rows += [u, w]; cols += [w, u]; vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(n, n))

    # --- 4) привязка ОРШ и ДХ ---
    tree = cKDTree(P)
    root_id = int(tree.query([ax, ay])[1])
    hh_nodes, ok_mask = [], []
    for h in hhs:
        dd, ii = tree.query([h['cx'], h['cy']])
        hh_nodes.append(int(ii))
        ok_mask.append(float(dd) * mpp <= SNAP_MAX_M)
    yards = [math.hypot(h['cx'] - P[nd][0], h['cy'] - P[nd][1]) * mpp
             for h, nd in zip(hhs, hh_nodes)]
    served_ids = [i for i in range(len(hhs)) if ok_mask[i]]
    if verbose:
        bad = len(hhs) - len(served_ids)
        sd = sorted([y for y, o in zip(yards, ok_mask) if o])
        print(f"  привязка: медиана двора {sd[len(sd)//2]:.0f} м; вне дорожной сети: {bad}")

    # --- 5) MST терминалов -> объединение путей -> SPT от ОРШ ---
    terminals = list(dict.fromkeys([root_id] + [hh_nodes[i] for i in served_ids]))
    tpos = {t: i for i, t in enumerate(terminals)}
    Dm, pred_m = dijkstra(C, indices=terminals, return_predecessors=True)
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

    hh_paths = {i: path_to_root(hh_nodes[i]) for i in served_ids}
    served_ids = [i for i in served_ids if hh_paths[i] is not None]
    if verbose:
        print(f"  достижимо по дереву: {len(served_ids)} ДХ")

    # --- 6) начальное размещение муфт (как в 06: слияние + ветвления + дедуп) ---
    couplers = {}

    order = sorted(served_ids, key=lambda i: DU[hh_nodes[i]])
    for hi in order:
        pth = hh_paths[hi]
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
        couplers.setdefault(serve if serve is not None else pth[0], []).append(hi)

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

    def path_dist_nodes(a, b):
        if a == b:
            return 0.0
        pa = path_to_root(a)
        if pa is None or b not in pa:
            return 1e9
        ib = pa.index(b)
        return sum(elen.get((min(pa[i], pa[i + 1]), max(pa[i], pa[i + 1])), 0) for i in range(ib))

    changed = True
    while changed:
        changed = False
        nodes_c = sorted(couplers.keys(), key=lambda c: DU[c])
        for i in range(len(nodes_c)):
            if nodes_c[i] not in couplers:
                continue
            for j in range(i + 1, len(nodes_c)):
                a, b = nodes_c[i], nodes_c[j]
                if a not in couplers or b not in couplers:
                    continue
                if path_dist_nodes(b, a) < DEDUP_M:
                    couplers[a].extend(couplers.pop(b))
                    changed = True
                    break
            if changed:
                break

    # --- 7) ОПТИМИЗАЦИЯ: итерации привязки/очистки/наращивания ---
    def dijkstra_couplers(cnodes):
        Dc, predc = dijkstra(C, indices=cnodes, return_predecessors=True)
        return np.array(Dc), predc.astype(np.int64)

    def road_path(c, a_h, Dc, predc, cidx):
        """путь [c..a_h] по дорогам от муфты c до узла a_h."""
        if c == a_h:
            return [c]
        pth = [a_h]
        cur = a_h
        src = cidx[c]
        guard = 0
        while cur != c:
            p = int(predc[src][cur])
            if p < 0:
                return None
            pth.append(p)
            cur = p
            guard += 1
            if guard > n:
                return None
        return pth[::-1]

    assign = {}          # hi -> (coupler, road_path)
    all_tails = set()    # накопленные хвосты ствола за все итерации

    for it in range(3):
        iter_tails = set()
        cnodes = sorted(couplers.keys())
        cpos = np.array([P[c] for c in cnodes])
        ctree = cKDTree(cpos)
        Dc, predc = dijkstra_couplers(cnodes)
        cidx = {c: i for i, c in enumerate(cnodes)}
        new_assign = {}
        for hi in served_ids:
            h = hhs[hi]
            a_h = hh_nodes[hi]
            cand = ctree.query_ball_point([h['cx'], h['cy']], CAND_R_M / mpp)
            best, bestl, bestp = None, np.inf, None
            for ci in cand:
                c = cnodes[ci]
                if c == root_id:
                    continue
                l = float(Dc[ci][a_h])
                if l < bestl and l < np.inf:
                    pth = road_path(c, a_h, Dc, predc, cidx)
                    if pth is not None:
                        best, bestl, bestp = c, l, pth
            if best is None:
                # fallback: ближайшая по дорогам из всех муфт
                col = Dc[:, a_h] if len(cnodes) else np.array([])
                col = np.where(col < np.inf, col, np.inf)
                if len(col):
                    ci = int(np.argmin(col))
                    if col[ci] < np.inf and cnodes[ci] != root_id:
                        best, bestl = cnodes[ci], float(col[ci])
                        bestp = road_path(best, a_h, Dc, predc, cidx)
            if best is None or bestp is None:
                # последний шанс: обслуживающая муфта по дереву
                pth = hh_paths[hi]
                best = next((nd for nd in pth if nd in couplers), root_id)
                bestp = pth[:pth.index(best) + 1] if best != root_id else pth
                bestl = sum(elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
                            for i in range(pth.index(best))) if best != root_id else 0.0
            new_assign[hi] = (best, bestp)
        assign = new_assign

        # использованные муфты + ствол из путей к корню
        used = set(c for (c, _) in assign.values())
        trunk = set()
        for c in used:
            if c == root_id:
                continue
            pth = path_to_root(c)
            if pth is None:
                continue
            for i in range(len(pth) - 1):
                trunk.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
        trunk_nodes = set()
        tdg = {}
        for (u, w) in trunk:
            trunk_nodes.add(u); trunk_nodes.add(w)
            tdg[u] = tdg.get(u, 0) + 1
            tdg[w] = tdg.get(w, 0) + 1

        new_couplers = {}
        for c in used:
            if c != root_id:
                new_couplers[c] = [hi for hi, (cc, _) in assign.items() if cc == c]
        for node, dg in tdg.items():
            if dg >= 3:
                new_couplers.setdefault(node, [])

        # длинные дропы: промежуточные муфты + хвосты ствола
        for hi in served_ids:
            c, pth = assign[hi]
            if c == root_id:
                continue
            dl = sum(math.hypot(P[pth[i + 1]][0] - P[pth[i]][0],
                                P[pth[i + 1]][1] - P[pth[i]][1]) for i in range(len(pth) - 1)) * mpp + yards[hi]
            if dl <= MAX_DROP_M:
                continue
            # идём от дома (конец pth) назад, ставим муфты через ~95 м
            acc = yards[hi]
            place_at = []
            for i in range(len(pth) - 1, 0, -1):
                seg = math.hypot(P[pth[i]][0] - P[pth[i - 1]][0], P[pth[i]][1] - P[pth[i - 1]][1]) * mpp
                acc += seg
                if acc >= 95.0:
                    place_at.append(pth[i - 1])
                    acc = 0.0
            if not place_at:
                continue
            for pn in place_at:
                new_couplers.setdefault(pn, [])
            # хвост ствола: от последнего узла пути, уже лежащего на стволе, до дальней новой муфты
            last_tr = max(i for i, nd in enumerate(pth) if nd in trunk_nodes or nd == c)
            far = max(i for i, nd in enumerate(pth) if nd in place_at)
            for i in range(last_tr, far):
                e = (min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1]))
                trunk.add(e)
                iter_tails.add(e)

        couplers = new_couplers
        all_tails |= iter_tails
        if verbose:
            print(f"  итерация {it + 1}: муфт {len(couplers)}")

    # --- 8) финальные дропы (с расщеплением оставшихся длинных) ---
    drops = []
    extra_coup = set()
    split_tails = set()
    for hi in served_ids:
        c, pth = assign[hi]
        poly_nodes = pth[:]
        # длина по дорогам
        road_l = sum(math.hypot(P[poly_nodes[i + 1]][0] - P[poly_nodes[i]][0],
                                P[poly_nodes[i + 1]][1] - P[poly_nodes[i]][1]) for i in range(len(poly_nodes) - 1)) * mpp
        dl = road_l + yards[hi]
        # расщепление длинного дропа: муфта ~95 м от дома
        if dl > MAX_DROP_M and len(poly_nodes) > 1:
            acc = yards[hi]
            cut_i = 0
            for i in range(len(poly_nodes) - 1, 0, -1):
                seg = math.hypot(P[poly_nodes[i]][0] - P[poly_nodes[i - 1]][0],
                                 P[poly_nodes[i]][1] - P[poly_nodes[i - 1]][1]) * mpp
                acc += seg
                if acc >= 95.0:
                    cut_i = i - 1
                    break
            if cut_i > 0:
                extra_coup.add(poly_nodes[cut_i])
                # хвост ствола: от старой муфты до новой по трассе дропа
                for i in range(0, cut_i):
                    split_tails.add((min(poly_nodes[i], poly_nodes[i + 1]),
                                     max(poly_nodes[i], poly_nodes[i + 1])))
                poly_nodes = poly_nodes[cut_i:]
                c = poly_nodes[0]
                road_l = sum(math.hypot(P[poly_nodes[i + 1]][0] - P[poly_nodes[i]][0],
                                        P[poly_nodes[i + 1]][1] - P[poly_nodes[i]][1]) for i in range(len(poly_nodes) - 1)) * mpp
                dl = road_l + yards[hi]
        entry = yard_polyline(hhs[hi], P[poly_nodes[-1]], mpp)
        poly = [list(P[nd]) for nd in poly_nodes] + [list(p) for p in entry[1:]]
        drops.append(dict(hh=hi, hh_id=hhs[hi]['id'], coupler=int(c),
                          poly=poly, length_m=round(dl, 1)))

    # --- 9) магистраль: дерево ∪ хвосты; кратчайшие пути корень -> муфты ---
    A_edges = dict(elen)
    for (u, w) in all_tails | split_tails:
        if (u, w) not in A_edges:
            A_edges[(u, w)] = math.hypot(P[u][0] - P[w][0], P[u][1] - P[w][1]) * mpp
    ar, ac, av = [], [], []
    for (u, w), l in A_edges.items():
        ar += [u, w]; ac += [w, u]; av += [l, l]
    A = csr_matrix((av, (ar, ac)), shape=(n, n))
    DA, predA = dijkstra(A, indices=root_id, return_predecessors=True)
    predA = predA.astype(np.int64)

    def path_A(node):
        pth = [node]
        cur = node
        guard = 0
        while cur != root_id:
            p = int(predA[cur])
            if p < 0:
                return None
            pth.append(p)
            cur = p
            guard += 1
            if guard > n:
                return None
        return pth

    used_final = set(dd['coupler'] for dd in drops if dd['coupler'] != root_id) | extra_coup
    feeder_edges = set()
    unreachable = 0
    for c in used_final:
        pth = path_A(c)
        if pth is None:
            unreachable += 1
            continue
        for i in range(len(pth) - 1):
            feeder_edges.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
    if verbose and unreachable:
        print(f"  ! недостижимых муфт: {unreachable}")

    # муфты: обслуживающие + точки ветвления магистрали
    fdg = {}
    for (u, w) in feeder_edges:
        fdg[u] = fdg.get(u, 0) + 1
        fdg[w] = fdg.get(w, 0) + 1
    coup_set = set(used_final)
    for node, dg in fdg.items():
        if dg >= 3:
            coup_set.add(node)
    coup_set.discard(root_id)

    feeder_m = sum(A_edges.get(e, math.hypot(P[e[0]][0] - P[e[1]][0], P[e[0]][1] - P[e[1]][1]) * mpp)
                   for e in feeder_edges)
    drop_m = sum(dd['length_m'] for dd in drops)
    coup_sorted = sorted(coup_set, key=lambda c: (DA[c] if np.isfinite(DA[c]) else 1e9))
    stats = dict(households_in_crop=len(hhs), served=len(drops),
                 unserved_no_road=len(hhs) - len(served_ids),
                 couplers=len(coup_sorted),
                 feeder_km=round(feeder_m / 1000, 2), drop_km=round(drop_m / 1000, 2),
                 avg_drop_m=round(drop_m / max(1, len(drops)), 1),
                 max_drop_m=round(max((dd['length_m'] for dd in drops), default=0), 1),
                 anchor_changed=anchor_changed)

    # сравнение со старой сетью (те же ДХ)
    old_by_id = {hhs_all[dd['hh']]['id']: dd for dd in old_net['drops']}
    same = [dd for dd in drops if dd['hh_id'] in old_by_id]
    old_lens = [old_by_id[dd['hh_id']]['length_m'] for dd in same]
    new_lens = [dd['length_m'] for dd in same]
    old_c_in = [c for c in old_net['couplers'] if x0 <= c['x'] <= x1 and y0 <= c['y'] <= y1]
    stats['cmp'] = dict(
        n_same=len(same),
        old_avg=round(sum(old_lens) / max(1, len(old_lens)), 1),
        new_avg=round(sum(new_lens) / max(1, len(new_lens)), 1),
        old_max=round(max(old_lens), 1) if old_lens else 0,
        new_max=round(max(new_lens), 1) if new_lens else 0,
        old_couplers_in_crop=len(old_c_in))
    if verbose:
        print(f"  ИТОГ: обслужено {stats['served']}/{len(hhs)} ДХ в кадре, муфт {stats['couplers']}, "
              f"магистраль {stats['feeder_km']} км, дропы {stats['drop_km']} км, "
              f"ср. дроп {stats['avg_drop_m']} м, макс {stats['max_drop_m']} м")
        c = stats['cmp']
        print(f"  сравнение (те же {c['n_same']} ДХ): ср. дроп {c['old_avg']} -> {c['new_avg']} м, "
              f"макс {c['old_max']} -> {c['new_max']} м; муфт в кадре было {c['old_couplers_in_crop']} -> {stats['couplers']}")

    couplers_out = [dict(node=int(c), x=float(P[c][0]), y=float(P[c][1]), label=f"М{i+1}")
                    for i, c in enumerate(coup_sorted)]
    feeder_out = [[[float(P[e[0]][0]), float(P[e[0]][1])], [float(P[e[1]][0]), float(P[e[1]][1])]]
                  for e in sorted(feeder_edges)]
    net = dict(anchor=anchor, anchor_changed=anchor_changed, root_node=root_id,
               crop=dict(rect=[x0, y0, x1, y1], scale=t['scale']),
               couplers=couplers_out, feeder_edges=feeder_out, drops=drops, stats=stats)
    save_json(f'{vdir(key)}/network_v2.json', net)
    return net


if __name__ == '__main__':
    import sys as _sys
    keys = _sys.argv[1:] if len(_sys.argv) > 1 else TASKS
    for key in keys:
        if key not in TASKS:
            continue
        print(f"=== {key} ===")
        rebuild(key)
