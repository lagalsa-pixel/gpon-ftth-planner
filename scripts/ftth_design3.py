#!/usr/bin/env python3
"""Перепроектирование FTTH-сетей v3 — коррекция размещения ОРШ/РОР и оптимизация
дроповых трасс.

Отличия от v2:
1. ОРШ размещаются в точной 1-медиане дорожного графа кластера (минимум суммы
   дорожных расстояний до снапов абонентов; ранее — лучший из 8 узлов у центроида).
   Среди узлов в пределах 2% от оптимума приоритет отдан перекрёсткам (deg>=3) —
   шкаф физически ставится на пересечении улиц/обочине, а не в произвольной точке.
2. Дропы привязываются к ФАСАДУ главного жилого дома: ищется ближайшая пара
   (точка на ребре дорожного графа, точка на контуре постройки) с точным
   сегмент-сегмент уточнением — вместо линии к центроиду постройки.
3. Ввод в здание 10 м (вместо 15 м).
4. 4 итерации переназначения абонентов (порог выигрыша 3 м) + перепозиционирование
   изменённых ОРШ по 1-медиане после каждой итерации.

Выход: {key}_design3.json."""
import json, math, os, sys, heapq
from collections import defaultdict
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
OSM_DIR = os.path.join(BASE, 'osm_ftth')
HH_DIR = os.path.join(BASE, 'ftth_out')
OUT_DIR = os.path.join(BASE, 'ftth_out')

from ftth_design import (local_frame, to_xy, build_graph, merge_components,
                         dijkstra, path_to, kmeans, merge_small, tree_polylines,
                         SPLITTER_MAX, SPLITTER_TARGET, CLUSTER_MIN, TRUNK_SLACK,
                         FIBER_SERIES, DIST_FIBER_SERIES)
from ftth_design2 import balance_clusters, compact_labels

OPT_ITERS = 4            # итераций переназначения абонентов между ОРШ
MOVE_GAIN_MIN = 3.0      # м: минимальный выигрыш для переназначения
CONSOL_MAX_D = 350.0     # м: дорожная дистанция между ОРШ для слияния
DROP_ENTRY_M = 10.0      # м: ввод от фасада до розетки ONT
MEDIAN_CUTOFF_M = 2200.0 # м: отсечка Дейкстры при поиске 1-медианы
MEDIAN_TOL = 1.02        # допуск (2%) для предпочтения узлов-перекрёстков
TOP_EDGES_REFINE = 3     # рёбер для точного сегмент-сегмент уточнения фасада
SPUR_TRIGGER_M = 70.0    # м: дроп длиннее — строится выноска распределения
SPUR_MAX_D = 500.0       # м: макс. длина выноски от фасада дома до якоря
DAISY_MAX_D = 60.0       # м: цепочка до уже подключённой выноски соседа


# ---------------------------------------------------------------- граф ----
def dijkstra_cut(adj, src, cutoff):
    """Кратчайшие пути от src с отсечкой по дистанции (для аккумуляции сумм)."""
    dist = {src: 0.0}
    seen = set()
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        for v, w in adj[u]:
            nd = d + w
            if nd <= cutoff and nd < dist.get(v, 1e18):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def place_splitter_median(adj, vids, node_xy, centroid_xy):
    """Точная 1-медиана дорожного графа: узел с минимальной суммой дорожных
    расстояний до снапов абонентов кластера. В пределах MEDIAN_TOL от оптимума
    приоритет узлам-перекрёсткам (deg>=3), затем выше степень, затем ближе
    к центроиду кластера."""
    n = len(node_xy)
    sum_d = np.zeros(n)
    cnt = np.zeros(n, dtype=np.int32)
    for v in vids:
        for node, dd in dijkstra_cut(adj, v, MEDIAN_CUTOFF_M).items():
            sum_d[node] += dd
            cnt[node] += 1
    need = len(vids)
    mask = cnt == need
    if not mask.any():
        mask = cnt >= (need * 3) // 4
    if not mask.any():
        mask = cnt > 0
    if not mask.any():
        return int(np.argmin(((node_xy - centroid_xy) ** 2).sum(1)))
    sums = np.where(mask, sum_d, np.inf)
    best = float(sums.min())
    cand = np.where(sums <= best * MEDIAN_TOL)[0]
    if len(cand) > 4096:                      # защита от вырожденных графов
        cand = cand[:4096]
    deg = np.array([len(adj.get(int(c), ())) for c in cand], dtype=float)
    inter = 1 - (deg >= 2.5).astype(int)       # 0 = перекрёсток (идёт первым)
    cd = np.sqrt(((node_xy[cand] - centroid_xy) ** 2).sum(1))
    order = np.lexsort((cd, -deg, inter))
    return int(cand[order[0]])


# ------------------------------------------------------------- геометрия ----
def seg_seg_closest(p1, p2, p3, p4):
    """Ближайшая пара точек отрезков p1p2 и p3p4 -> (dist, c1, c2)."""
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3
    rx, ry = x1 - x3, y1 - y3
    a = dx1 * dx1 + dy1 * dy1
    e = dx2 * dx2 + dy2 * dy2
    f = dx2 * rx + dy2 * ry
    EPS = 1e-12
    if a <= EPS and e <= EPS:
        return math.hypot(rx, ry), (x1, y1), (x3, y3)
    if a <= EPS:
        s, t = 0.0, min(1.0, max(0.0, f / e))
    else:
        c = dx1 * rx + dy1 * ry
        if e <= EPS:
            t, s = 0.0, min(1.0, max(0.0, -c / a))
        else:
            b = dx1 * dx2 + dy1 * dy2
            den = a * e - b * b
            s = min(1.0, max(0.0, (b * f - c * e) / den)) if den > EPS else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(1.0, max(0.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, min(1.0, max(0.0, (b - c) / a))
    c1 = (x1 + dx1 * s, y1 + dy1 * s)
    c2 = (x3 + dx2 * t, y3 + dy2 * t)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1]), c1, c2


def pick_main_polygon(h):
    """Главный (жилой) полигон ДХ: его центроид совпадает с координатами ДХ."""
    best, bd = None, 1e18
    for poly in h.get('polygons', []):
        cx = sum(p[1] for p in poly) / len(poly)
        cy = sum(p[0] for p in poly) / len(poly)
        d = (cy - h['lat']) ** 2 + (cx - h['lon']) ** 2
        if d < bd:
            bd, best = d, poly
    return best


def snap_to_edges_facade(nodes, adj, ky, kx, hh_list):
    """Привязка абонентов к дорожному графу с дропом к ФАСАДУ: ближайшая пара
    (точка на ребре графа, точка на контуре главного жилого дома). Для доп.
    абонентов без полигонов — перпендикуляр к ближайшему ребру от точки.
    Возвращает (snaps, drops); drop = (snap_lat, snap_lon, to_lat, to_lon, м)."""
    edges = []
    seen_e = set()
    for u in adj:
        for v, w in adj[u]:
            e = (min(u, v), max(u, v))
            if e in seen_e:
                continue
            seen_e.add(e)
            edges.append((u, v))
    if not edges:
        return {}, []
    EA = np.array([to_xy(*nodes[u], ky, kx) for u, v in edges])
    EB = np.array([to_xy(*nodes[v], ky, kx) for u, v in edges])
    D = EB - EA
    DD = (D * D).sum(1)
    DD[DD == 0] = 1e-9
    snaps = {}
    drops = []
    for i, h in enumerate(hh_list):
        main_poly = pick_main_polygon(h) if h.get('polygons') else None
        if main_poly is None:
            P = np.array(to_xy(h['lat'], h['lon'], ky, kx))
            t = ((P - EA) * D).sum(1) / DD
            tc = np.clip(t, 0.0, 1.0)
            Proj = EA + tc[:, None] * D
            dd = np.sqrt(((P - Proj) ** 2).sum(1))
            j = int(np.argmin(dd))
            d_len = float(dd[j])
            foot = Proj[j].copy()
            to_pt = (h['lat'], h['lon'])
        else:
            ring = list(main_poly) + [main_poly[0]]
            cands = []
            for a, b in zip(ring[:-1], ring[1:]):
                cands.append((a[0], a[1]))
                cands.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
            Pc = np.array([to_xy(la, lo, ky, kx) for la, lo in cands])
            t = ((Pc[:, None, :] - EA[None, :, :]) * D[None, :, :]).sum(-1) / DD[None, :]
            tc = np.clip(t, 0.0, 1.0)
            Proj = EA[None, :, :] + tc[:, :, None] * D[None, :, :]
            dd = np.sqrt(((Pc[:, None, :] - Proj) ** 2).sum(-1))
            flat = int(dd.argmin())
            pi, j = divmod(flat, dd.shape[1])
            best = (float(dd[pi, j]), Proj[pi, j].copy(), Pc[pi].copy(), j)
            for jj in np.argsort(dd[pi])[:TOP_EDGES_REFINE]:
                jj = int(jj)
                A3 = (EA[jj][0], EA[jj][1])
                B3 = (EB[jj][0], EB[jj][1])
                for a, b in zip(ring[:-1], ring[1:]):
                    P1 = to_xy(a[0], a[1], ky, kx)
                    P2 = to_xy(b[0], b[1], ky, kx)
                    dseg, c1, c2 = seg_seg_closest(P1, P2, A3, B3)
                    if dseg < best[0]:
                        best = (dseg, np.array(c2), np.array(c1), jj)
            d_len, foot, fpt, j = best
            to_pt = (fpt[0] / ky, fpt[1] / kx)
        u, v = edges[j]
        plat, plon = foot[0] / ky, foot[1] / kx
        vid = len(nodes)
        nodes.append((plat, plon))
        du = math.hypot(*(foot - EA[j]))
        dv = math.hypot(*(EB[j] - foot))
        if du > 0.5:
            adj[u].append((vid, du))
            adj[vid].append((u, du))
        if dv > 0.5:
            adj[v].append((vid, dv))
            adj[vid].append((v, dv))
        snaps[i] = dict(vid=vid, snap_lat=plat, snap_lon=plon, drop_m=float(d_len))
        drops.append((plat, plon, to_pt[0], to_pt[1], float(d_len)))
    return snaps, drops


# ------------------------------------------------------- топология v3 ----
def add_spurs(nodes, adj, ky, kx, hh_list, snaps, drops):
    """Выноски распределительного кабеля к удалённым от дорог ДХ: дроп длиннее
    SPUR_TRIGGER_M заменяется ребром графа «фасад дома -> якорь» (ближайший узел
    дорожного графа, собственный снап или уже подключённый сосед в пределах
    DAISY_MAX_D). Удалённые дома объединяются цепочками — один общий стояк вместо
    нескольких длинных дропов; дроп дома становится нулевым.
    Возвращает (house_node: i -> vid, spur_edges: [(vid, anchor, метры)])."""
    node_xy = np.array([to_xy(*nodes[i], ky, kx) for i in range(len(nodes))])
    house_node = {}
    spur_edges = []
    far = [i for i in range(len(hh_list)) if drops[i][4] > SPUR_TRIGGER_M]
    far.sort(key=lambda i: -drops[i][4])
    for i in far:
        # точка дома — фасад (конец дропа)
        P = np.array(to_xy(drops[i][2], drops[i][3], ky, kx))
        best = None                      # (d, anchor_vid)
        # 1) ближайший узел графа (включая снапы и выноски)
        dd = np.sqrt(((node_xy - P) ** 2).sum(1))
        j = int(np.argmin(dd))
        if dd[j] <= SPUR_MAX_D:
            best = (float(dd[j]), j)
        # 2) уже подключённая выноска соседней ДХ
        for k2, vid2 in house_node.items():
            q = to_xy(drops[k2][2], drops[k2][3], ky, kx)
            dq = math.hypot(P[0] - q[0], P[1] - q[1])
            if dq <= DAISY_MAX_D and (best is None or dq < best[0]):
                best = (dq, vid2)
        # 3) собственный снап на дороге (перенос дропа в распределение)
        d_foot = float(drops[i][4])
        if d_foot <= SPUR_MAX_D and (best is None or d_foot < best[0]):
            best = (d_foot, snaps[i]['vid'])
        if best is None:
            continue                      # дальше SPUR_MAX_D — оставить дроп
        d_spur, anchor = best
        vid = len(nodes)
        nodes.append((drops[i][2], drops[i][3]))
        adj[vid].append((anchor, d_spur))
        adj[anchor].append((vid, d_spur))
        house_node[i] = vid
        node_xy = np.append(node_xy, [P], axis=0)
        spur_edges.append((vid, anchor, d_spur))
        # дроп обнуляется: дом теперь узел графа
        snaps[i] = dict(vid=vid, snap_lat=drops[i][2], snap_lon=drops[i][3],
                        drop_m=0.0)
        drops[i] = (drops[i][0], drops[i][1], drops[i][2], drops[i][3], 0.0)
    return house_node, spur_edges


def consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl):
    """Слияние близких ОРШ с суммарной загрузкой <= 32 портов."""
    n_consol = 0
    rejected = set()
    for _round in range(30):
        loads = [int((lab == j).sum()) for j in range(n_cl)]
        act = [j for j in range(n_cl) if loads[j] > 0]
        if len(act) <= 1:
            break
        best = None
        for ii in range(len(act)):
            for jj in range(ii + 1, len(act)):
                a, b = act[ii], act[jj]
                if (min(a, b), max(a, b)) in rejected:
                    continue
                if loads[a] + loads[b] > SPLITTER_MAX:
                    continue
                pa = to_xy(*nodes[spl_node[a]], ky, kx)
                pb = to_xy(*nodes[spl_node[b]], ky, kx)
                de = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                if de > CONSOL_MAX_D:
                    continue
                if best is None or de < best[0]:
                    best = (de, a, b)
        if best is None:
            break
        _de, a, b = best
        dm_ab, _ = dijkstra(adj, spl_node[a], targets={spl_node[b]})
        if dm_ab.get(spl_node[b], 1e9) > CONSOL_MAX_D:
            rejected.add((min(a, b), max(a, b)))
            continue
        lab[lab == b] = a
        idx = np.where(lab == a)[0]
        cc = pts[idx].mean(0)
        spl_node[a] = place_splitter_median(adj, [vids_all[int(i)] for i in idx],
                                            node_xy, cc)
        n_consol += 1
    return n_consol


def reassign_iteration(nodes, adj, lab, spl_node, vids_all, n_hh, n_cl):
    """Переназначение абонентов к ближайшим по дорожному графу ОРШ (ёмкость <= 32)."""
    dist_maps = []
    for j in range(n_cl):
        dm, _ = dijkstra(adj, spl_node[j], targets=set(vids_all))
        dist_maps.append(dm)
    loads = [int((lab == j).sum()) for j in range(n_cl)]
    moves = []
    for i in range(n_hh):
        v = vids_all[i]
        cur = int(lab[i])
        dcur = dist_maps[cur].get(v, 1e9)
        if dcur >= 1e9:
            continue
        best, bestd = cur, dcur
        for j in range(n_cl):
            if j == cur or loads[j] >= SPLITTER_MAX:
                continue
            dj = dist_maps[j].get(v, 1e9)
            if dj < bestd - MOVE_GAIN_MIN:
                bestd, best = dj, j
        if best != cur:
            moves.append((dcur - bestd, i, best))
    if not moves:
        return 0
    moves.sort(key=lambda x: -x[0])
    applied = []
    for gain, i, j in moves:
        if loads[j] >= SPLITTER_MAX:
            continue
        old = int(lab[i])
        applied.append((i, old, j))
        loads[old] -= 1
        loads[j] += 1
        lab[i] = j
    if not applied:
        return 0
    changed = set()
    for _i, old, j in applied:
        changed.add(old)
        changed.add(j)
    return len(applied), changed


def refine_placement_tree(adj, spl_node, lab, snaps, n_cl, max_hops=2):
    """Локальное уточнение узла ОРШ по ФАКТИЧЕСКОЙ длине распределительного
    дерева кластера (объединение кратчайших путей кандидат -> снапы): кандидаты —
    сам узел-медиана и его соседы по графу в пределах 2 рёбер по <=120 м.
    """
    for j in range(n_cl):
        idx = np.where(lab == j)[0]
        vids = [snaps[int(i)]['vid'] for i in idx]
        if not vids:
            continue
        vset = set(vids)
        base = spl_node[j]
        cands = {base}
        frontier = {base}
        for _hop in range(max_hops):
            nxt = set()
            for u in frontier:
                for v, w in adj[u]:
                    if w > 120.0 or v in cands:
                        continue
                    nxt.add(v)
            cands |= nxt
            frontier = nxt
        if len(cands) <= 1:
            continue
        best_node, best_len = base, None
        for c in cands:
            dist_c, prev_c = dijkstra(adj, c, targets=vset)
            if any(v not in dist_c for v in vids):
                continue
            used = set()
            m = 0.0
            for v in vids:
                p = path_to(prev_c, v)
                for a, b in zip(p[:-1], p[1:]):
                    e = (min(a, b), max(a, b))
                    if e not in used:
                        used.add(e)
                        w = dict(adj[a]).get(b)
                        m += w if w else 0.0
            if best_len is None or m < best_len - 0.5:
                best_len, best_node = m, c
        spl_node[j] = best_node


def route_distribution(adj, spl_node, lab, snaps, n_cl):
    """Объединение кратчайших путей ОРШ -> снапы абонентов."""
    used = set()
    m = 0.0
    unreachable = []
    for j in range(n_cl):
        vids = [snaps[int(i)]['vid'] for i in np.where(lab == j)[0]]
        if not vids:
            continue
        dist_s, prev_s = dijkstra(adj, spl_node[j], targets=set(vids))
        for v in vids:
            if v in dist_s:
                p = path_to(prev_s, v)
                for a, b in zip(p[:-1], p[1:]):
                    e = (min(a, b), max(a, b))
                    if e not in used:
                        used.add(e)
                        w = dict(adj[a]).get(b)
                        m += w if w else 0.0
            else:
                unreachable.append(v)
    return used, m, unreachable


def reposition_changed(adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl):
    for j in sorted(changed):
        idx = np.where(lab == j)[0]
        if len(idx) == 0:
            continue
        cc = pts[idx].mean(0)
        spl_node[j] = place_splitter_median(adj, [vids_all[int(i)] for i in idx],
                                            node_xy, cc)


def round_series(x, series):
    for s in series:
        if x <= s:
            return s
    return series[-1]


def design_village3(hhj, osm_data):
    key = hhj['key']
    hh_list = hhj['households']
    n_hh = len(hh_list)
    n_id = sum(1 for h in hh_list if not h.get('extra'))
    n_add = n_hh - n_id
    anchor = hhj['anchor']
    ky, kx = local_frame(anchor[0])
    lat_min, lon_min, lat_max, lon_max = hhj['bbox']

    nodes, adj, n_ways = build_graph(osm_data, ky, kx, lat_min, lon_min, lat_max, lon_max)
    aerials = merge_components(nodes, adj, ky, kx)
    snaps, drops = snap_to_edges_facade(nodes, adj, ky, kx, hh_list)
    house_node, spur_edges = add_spurs(nodes, adj, ky, kx, hh_list, snaps, drops)
    if spur_edges:
        print(f'      выноски распределения: {len(spur_edges)} шт, '
              f'{sum(e[2] for e in spur_edges) / 1000:.2f} км', flush=True)
    pts = np.array([to_xy(h['lat'], h['lon'], ky, kx) for h in hh_list])
    node_xy = np.array([to_xy(*nodes[i], ky, kx) for i in range(len(nodes))])
    vids_all = [snaps[i]['vid'] for i in range(n_hh)]

    # ---- POP: узел графа, ближайший к центроиду всех абонентов ----
    centroid = pts.mean(0)
    d_pop = np.sqrt(((node_xy - centroid) ** 2).sum(1))
    order = np.argsort(d_pop)
    pop_id = int(order[0])
    for c in order:
        if int(c) in adj:
            pop_id = int(c)
            break

    # ---- исходная кластеризация (евклидова, сбалансированная <= 32) ----
    k = max(1, math.ceil(n_hh / SPLITTER_TARGET))
    lab, _ = kmeans(pts, k, seed=42)
    lab = balance_clusters(pts, lab, SPLITTER_MAX)
    lab = merge_small(pts, lab, CLUSTER_MIN, SPLITTER_MAX)
    lab = compact_labels(lab)
    n_cl = int(lab.max()) + 1

    # ---- исходное размещение ОРШ: точная 1-медиана ----
    spl_node = []
    for j in range(n_cl):
        idx = np.where(lab == j)[0]
        cc = pts[idx].mean(0)
        spl_node.append(place_splitter_median(adj, [vids_all[int(i)] for i in idx],
                                              node_xy, cc))

    # ---- оптимизация топологии ----
    n_consol = consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl)
    _, dist_m_before, _ = route_distribution(adj, spl_node, lab, snaps, n_cl)
    n_moves_total = 0
    for it in range(OPT_ITERS):
        res = reassign_iteration(nodes, adj, lab, spl_node, vids_all, n_hh, n_cl)
        if not res or not res[0]:
            break
        n_mov, changed = res
        n_moves_total += n_mov
        reposition_changed(adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl)
        print(f'      итерация {it + 1}: переназначено {n_mov}, '
              f'перепозиционировано ОРШ {len(changed)}', flush=True)
    n_consol2 = consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl)
    n_consol += n_consol2
    if n_consol2:
        res = reassign_iteration(nodes, adj, lab, spl_node, vids_all, n_hh, n_cl)
        if res and res[0]:
            n_mov, changed = res
            n_moves_total += n_mov
            reposition_changed(adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl)
            print(f'      финальная итерация после консолидации: переназначено {n_mov}', flush=True)
    # последнее перепозиционирование всех непустых кластеров + уточнение по дереву
    reposition_changed(adj, lab, spl_node, pts, vids_all, node_xy,
                       set(range(n_cl)), n_cl)
    refine_placement_tree(adj, spl_node, lab, snaps, n_cl)
    print(f'      итог: консолидаций {n_consol}, переназначений {n_moves_total}', flush=True)

    # удаление опустевших кластеров
    keep = [j for j in range(n_cl) if (lab == j).any()]
    remap = {j: nn for nn, j in enumerate(keep)}
    lab = np.array([remap[int(l)] for l in lab], dtype=int)
    spl_node = [spl_node[j] for j in keep]
    n_cl = len(keep)

    # ---- финальная маршрутизация распределительного уровня ----
    used_dist, dist_m_after, unreach = route_distribution(adj, spl_node, lab, snaps, n_cl)

    # ---- магистраль: POP -> ОРШ ----
    dist_t, prev_t = dijkstra(adj, pop_id)
    used_trunk = set()
    trunk_m = 0.0
    for j in range(n_cl):
        if spl_node[j] in dist_t:
            p = path_to(prev_t, spl_node[j])
            for a, b in zip(p[:-1], p[1:]):
                e = (min(a, b), max(a, b))
                if e not in used_trunk:
                    used_trunk.add(e)
                    wa = dict(adj[a]).get(b)
                    trunk_m += wa if wa else 0.0
    aerial_set = {(min(u, v), max(u, v)) for u, v, _ in aerials}

    # воздушные линии напрямую для недостижимых абонентов (до фасада)
    aerial_fallback = []
    for i in range(n_hh):
        if snaps[i]['vid'] in unreach:
            j = int(lab[i])
            aerial_fallback.append([nodes[spl_node[j]],
                                    (drops[i][2], drops[i][3])])

    # ---- дропы ----
    drop_arr = np.array([d[4] for d in drops]) if drops else np.zeros(1)
    drop_km = drop_arr.sum() / 1000.0 + n_hh * DROP_ENTRY_M / 1000.0

    # ---- полилинии ----
    trunk_polys = tree_polylines(nodes, used_trunk)
    dist_polys = tree_polylines(nodes, used_dist - used_trunk)
    aerial_polys = []
    for (u, v) in (used_trunk | used_dist):
        if (u, v) in aerial_set:
            aerial_polys.append([nodes[u], nodes[v]])
    # выноски, вошедшие в дерево распределения — отдельным слоем
    spur_polys = []
    for (vid_s, anch_s, _d) in spur_edges:
        e = (min(vid_s, anch_s), max(vid_s, anch_s))
        if e in used_dist or e in used_trunk:
            spur_polys.append([nodes[vid_s], nodes[anch_s]])

    trunk_len = trunk_m / 1000.0 * TRUNK_SLACK
    dist_len = dist_m_after / 1000.0 * TRUNK_SLACK
    dist_len_before = dist_m_before / 1000.0 * TRUNK_SLACK

    # ---- нумерация: ОРШ запад->восток; абоненты внутри ОРШ запад->восток ----
    spl_order = sorted(range(n_cl), key=lambda j: (nodes[spl_node[j]][1], nodes[spl_node[j]][0]))
    num_of = {j: nn for nn, j in enumerate(spl_order, 1)}
    port_of = {}
    for j in spl_order:
        idx = sorted(np.where(lab == j)[0],
                     key=lambda i: (hh_list[int(i)]['lon'], hh_list[int(i)]['lat']))
        for p, i in enumerate(idx, 1):
            port_of[int(i)] = p

    households_out = []
    for i, h in enumerate(hh_list):
        j = int(lab[i])
        ho = dict(h)
        ho['spl'] = num_of[j]
        ho['port'] = port_of[i]
        ho['label'] = f"{num_of[j]}.{port_of[i]}"
        households_out.append(ho)

    spl_out = []
    for j in spl_order:
        n_mem = int((lab == j).sum())
        spl_out.append(dict(id=f"ОРШ {num_of[j]}", num=num_of[j],
                            lat=nodes[spl_node[j]][0], lon=nodes[spl_node[j]][1],
                            hh=n_mem,
                            fibers=round_series(int(math.ceil(n_mem * 1.2)), DIST_FIBER_SERIES)))

    trunk_fibers = round_series(int(math.ceil(n_cl * 1.3)), FIBER_SERIES)

    # евклидовы дистанции ОРШ -> абоненты (диагностическая метрика)
    spl_xy = {num_of[j]: to_xy(*nodes[spl_node[j]], ky, kx) for j in range(n_cl)}
    d_spl = [math.hypot(*(pts[i] - spl_xy[households_out[i]['spl']])) for i in range(n_hh)]

    stats = dict(
        n_hh=n_hh, n_identified=n_id, n_added=n_add, expected=hhj['expected'],
        splitters=n_cl, avg_hh_per_splitter=round(n_hh / n_cl, 1),
        trunk_km=round(trunk_len, 2), dist_km=round(dist_len, 2),
        dist_km_before_opt=round(dist_len_before, 2),
        opt_gain_pct=round((1.0 - dist_m_after / dist_m_before) * 100.0, 1) if dist_m_before > 0 else 0.0,
        opt_moves=n_moves_total, opt_merges=n_consol,
        drops_km=round(drop_km, 2), total_km=round(trunk_len + dist_len + drop_km, 2),
        trunk_fibers=trunk_fibers,
        drop_avg_m=round(float(drop_arr.mean()), 1),
        drop_med_m=round(float(np.median(drop_arr)), 1),
        drop_p90_m=round(float(np.percentile(drop_arr, 90)), 1),
        drop_max_m=round(float(drop_arr.max()), 1),
        drop_gt60=int((drop_arr > 60).sum()),
        spur_hh=len(spur_edges),
        spur_km=round(sum(e[2] for e in spur_edges) / 1000.0, 2),
        spl_dist_avg_m=round(float(np.mean(d_spl)), 1),
        spl_dist_max_m=round(float(np.max(d_spl)), 1),
        entry_m=DROP_ENTRY_M,
        road_ways=n_ways, road_nodes=len(nodes),
        aerial_edges=len(aerial_polys) + len(aerial_fallback),
    )
    return dict(
        key=key, name=hhj['name'], district=hhj['district'], okrug=hhj['okrug'],
        expected=hhj['expected'], anchor=anchor, bbox=hhj['bbox'],
        n_hh=n_hh, n_identified=n_id, n_added=n_add,
        pop=dict(lat=nodes[pop_id][0], lon=nodes[pop_id][1]),
        splitters=spl_out,
        households=households_out,
        trunk_polylines=trunk_polys,
        dist_polylines=dist_polys,
        drops=[dict(n=hh_list[int(i)]['n'], label=households_out[i]['label'],
                    snap=[snaps[int(i)]['snap_lat'], snaps[int(i)]['snap_lon']],
                    to=[drops[int(i)][2], drops[int(i)][3]],
                    drop_m=round(float(drops[int(i)][4]), 1))
               for i in range(n_hh)],
        aerial=[[[a[0], a[1]], [b[0], b[1]]] for a, b in aerial_fallback] + aerial_polys
        + spur_polys,
        stats=stats,
    )


def main():
    from ftth_households import VILLAGES
    keys = sys.argv[1:] or [v['key'] for v in VILLAGES]
    summary = []
    for key in keys:
        hhj = json.load(open(os.path.join(HH_DIR, f'{key}_hh_full.json')))
        osm = json.load(open(os.path.join(OSM_DIR, f'{key}.json')))
        print(f"[{key}] абонентов {len(hhj['households'])} "
              f"(выявлено {hhj['n_identified']} + добавлено {hhj['n_added']})...", flush=True)
        d = design_village3(hhj, osm)
        with open(os.path.join(OUT_DIR, f'{key}_design3.json'), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        s = d['stats']
        print(f"    ОРШ {s['splitters']}, магистраль {s['trunk_km']} км, распределение "
              f"{s['dist_km']} км, дропы {s['drops_km']} км (ср. {s['drop_avg_m']} м, "
              f"макс {s['drop_max_m']} м), всего {s['total_km']} км", flush=True)
        summary.append((d['name'], s))
    print('\n================ СВОДКА v3 ================')
    print(f"{'Село':<20}{'Абон.':>6}{'ОРШ':>5}{'Маг.,км':>9}{'Распр.,км':>10}"
          f"{'Дропы,км':>9}{'Всего,км':>9}{'Дроп ср.':>9}{'Дроп макс':>10}{'ОРШ->аб ср':>11}")
    for name, s in summary:
        print(f"{name:<20}{s['n_hh']:>6}{s['splitters']:>5}{s['trunk_km']:>9}{s['dist_km']:>10}"
              f"{s['drops_km']:>9}{s['total_km']:>9}{s['drop_avg_m']:>9}{s['drop_max_m']:>10}"
              f"{s['spl_dist_avg_m']:>11}")
    # сравнение с v2, если файлы на месте
    try:
        print('\n------------- сравнение v2 -> v3 -------------')
        print(f"{'Село':<20}{'дропы v2':>9}{'дропы v3':>9}{'выигр.%':>9}"
              f"{'распр v2':>9}{'распр v3':>9}{'ОРШ v2':>7}{'ОРШ v3':>7}")
        for name, s in summary:
            p2 = os.path.join(OUT_DIR, f"{s.get('key', '')}_design2.json")
            key = [nm for nm, ss in summary if nm == name][0]
            # найдём key по имени
            key = next(v['key'] for v in VILLAGES if v['name'] == name)
            p2 = os.path.join(OUT_DIR, f'{key}_design2.json')
            s2 = json.load(open(p2))['stats']
            print(f"{name:<20}{s2['drops_km']:>9}{s['drops_km']:>9}"
                  f"{(1 - s['drops_km'] / s2['drops_km']) * 100:>8.1f}%"
                  f"{s2['dist_km']:>9}{s['dist_km']:>9}{s2['splitters']:>7}{s['splitters']:>7}")
    except Exception as ex:
        print(f'(сравнение с v2 недоступно: {ex})')


if __name__ == '__main__':
    main()
