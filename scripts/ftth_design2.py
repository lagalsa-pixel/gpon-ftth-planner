#!/usr/bin/env python3
"""Перепроектирование FTTH-сетей v2: требуемое число абонентов (сверка с таблицей
СНП ВКО + доп. абоненты рядом с выявленными ДХ), оптимизация топологии
распределительного уровня — переназначение абонентов к ближайшим по дорожному
графу ОРШ с учётом ёмкости сплиттеров GPON 1:32, консолидация близких ОРШ и
перепозиционирование шкафов. Нумерация абонентов привязана к номеру ОРШ через
точку: «ОРШ.№» (12.7 = ОРШ 12, абонент 7)."""
import json, math, os, sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
OSM_DIR = os.path.join(BASE, 'osm_ftth')
HH_DIR = os.path.join(BASE, 'ftth_out')
OUT_DIR = os.path.join(BASE, 'ftth_out')

from ftth_design import (local_frame, to_xy, build_graph, merge_components,
                         dijkstra, path_to, snap_to_edges, kmeans,
                         split_oversized, merge_small, tree_polylines,
                         SPLITTER_MAX, SPLITTER_TARGET, CLUSTER_MIN, TRUNK_SLACK,
                         DROP_ENTRY_M, MAX_SPLITTER_CANDIDATES,
                         FIBER_SERIES, DIST_FIBER_SERIES)

OPT_ITERS = 2          # итераций оптимизации распределительного уровня
MOVE_GAIN_MIN = 5.0    # м: минимальный выигрыш для переназначения абонента
CONSOL_MAX_D = 350.0   # м: дорожная дистанция между ОРШ для слияния


def balance_clusters(points, lab, max_size):
    """Балансировка евклидовых кластеров: абоненты из перегруженных кластеров
    (самые дальние от центроида) переносятся в ближайшие недогруженные. Число
    кластеров не растёт (в отличие от каскадного деления) — выше загрузка
    портов сплиттеров."""
    n_cl = int(lab.max()) + 1
    for _step in range(4000):
        sizes = np.bincount(lab, minlength=n_cl)
        over = np.where(sizes > max_size)[0]
        if len(over) == 0:
            break
        moved = False
        centers = np.array([points[lab == jj].mean(0) if (lab == jj).any()
                            else np.zeros(2) for jj in range(n_cl)])
        for j in over:
            idx = np.where(lab == j)[0]
            c = points[idx].mean(0)
            d = np.sqrt(((points[idx] - c) ** 2).sum(1))
            order = idx[np.argsort(-d)]
            for i in order[:max(0, len(idx) - max_size)]:
                sizes = np.bincount(lab, minlength=n_cl)
                cand = [jj for jj in range(n_cl) if jj != j and sizes[jj] < max_size]
                if not cand:
                    break
                dd = [math.hypot(*(points[i] - centers[jj])) for jj in cand]
                jj = cand[int(np.argmin(dd))]
                lab[i] = jj
                moved = True
        if not moved:
            break
    return lab


def compact_labels(lab):
    ids = np.unique(lab)
    remap = {j: i for i, j in enumerate(ids)}
    return np.array([remap[j] for j in lab], dtype=int)


def place_splitter(nodes, adj, node_xy, vids, cc):
    """Кандидатные узлы графа возле центроида кластера; минимум суммы дорожных
    расстояний до абонентов кластера."""
    d_node = np.sqrt(((node_xy - cc) ** 2).sum(1))
    cand = np.argsort(d_node)[:MAX_SPLITTER_CANDIDATES]
    best_id, best_tot = None, 1e18
    for c in cand:
        c = int(c)
        if c not in adj:
            continue
        dist, _ = dijkstra(adj, c, targets=set(vids))
        tot = sum(dist.get(v, 1e9) for v in vids)
        if tot < best_tot:
            best_tot, best_id = tot, c
    if best_id is None:
        best_id = int(cand[0])
    return best_id


def consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl):
    """Слияние близких ОРШ с суммарной загрузкой <= 32 портов (дорожная
    дистанция между шкафами <= CONSOL_MAX_D). Возвращает число слияний."""
    n_consol = 0
    rejected = set()
    for _round in range(30):
        loads = [int((lab == j).sum()) for j in range(n_cl)]
        act = [j for j in range(n_cl) if loads[j] > 0]
        if len(act) <= 1:
            break
        best = None  # (d_euclid, a, b)
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
        spl_node[a] = place_splitter(nodes, adj, node_xy,
                                     [vids_all[int(i)] for i in idx], cc)
        n_consol += 1
    return n_consol


def reassign_iteration(nodes, adj, lab, spl_node, snaps, vids_all, n_hh, n_cl):
    """Одна итерация переназначения абонентов к ближайшим по дорожному графу ОРШ
    (с учётом ёмкости 32) + перепозиционирование изменённых шкафов."""
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


def route_distribution(adj, spl_node, lab, snaps, n_cl):
    """Объединение кратчайших путей ОРШ -> снапы абонентов. Возвращает
    (множество рёбер, метры, список недостижимых снапов)."""
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


def round_series(x, series):
    for s in series:
        if x <= s:
            return s
    return series[-1]


def reposition_changed(nodes, adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl):
    for j in sorted(changed):
        idx = np.where(lab == j)[0]
        if len(idx) == 0:
            continue
        cc = pts[idx].mean(0)
        spl_node[j] = place_splitter(nodes, adj, node_xy,
                                     [vids_all[int(i)] for i in idx], cc)


def design_village2(hhj, osm_data):
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
    snaps, drops = snap_to_edges(nodes, adj, ky, kx, hh_list)
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

    # ---- исходное размещение ОРШ (сплиттеров) ----
    spl_node = []
    for j in range(n_cl):
        idx = np.where(lab == j)[0]
        cc = pts[idx].mean(0)
        spl_node.append(place_splitter(nodes, adj, node_xy,
                                       [vids_all[int(i)] for i in idx], cc))

    # ---- оптимизация топологии ----
    n_consol = consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl)
    _, dist_m_before, _ = route_distribution(adj, spl_node, lab, snaps, n_cl)
    n_moves_total = 0
    for it in range(OPT_ITERS):
        res = reassign_iteration(nodes, adj, lab, spl_node, snaps, vids_all, n_hh, n_cl)
        if not res or not res[0]:
            break
        n_mov, changed = res
        n_moves_total += n_mov
        reposition_changed(nodes, adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl)
        print(f'      оптимизация, итерация {it + 1}: переназначено {n_mov} '
              f'абонентов, перепозиционировано ОРШ {len(changed)}', flush=True)
    # пост-консолидация + финальное переназначение
    n_consol2 = consolidate(nodes, adj, lab, spl_node, pts, vids_all, ky, kx, node_xy, n_cl)
    n_consol += n_consol2
    if n_consol2:
        res = reassign_iteration(nodes, adj, lab, spl_node, snaps, vids_all, n_hh, n_cl)
        if res and res[0]:
            n_mov, changed = res
            n_moves_total += n_mov
            reposition_changed(nodes, adj, lab, spl_node, pts, vids_all, node_xy, changed, n_cl)
            print(f'      финальная итерация после консолидации: переназначено {n_mov}', flush=True)
    print(f'      итог: консолидировано {n_consol} ОРШ, переназначений {n_moves_total}', flush=True)

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

    # воздушные линии напрямую для недостижимых абонентов
    aerial_fallback = []
    for i in range(n_hh):
        if snaps[i]['vid'] in unreach:
            j = int(lab[i])
            aerial_fallback.append([nodes[spl_node[j]],
                                    (hh_list[i]['lat'], hh_list[i]['lon'])])

    # ---- дропы ----
    drop_km = sum(d[4] for d in drops) / 1000.0 + n_hh * DROP_ENTRY_M / 1000.0

    # ---- полилинии ----
    trunk_polys = tree_polylines(nodes, used_trunk)
    dist_polys = tree_polylines(nodes, used_dist - used_trunk)
    aerial_polys = []
    for (u, v) in (used_trunk | used_dist):
        if (u, v) in aerial_set:
            aerial_polys.append([nodes[u], nodes[v]])

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

    stats = dict(
        n_hh=n_hh, n_identified=n_id, n_added=n_add, expected=hhj['expected'],
        splitters=n_cl, avg_hh_per_splitter=round(n_hh / n_cl, 1),
        trunk_km=round(trunk_len, 2), dist_km=round(dist_len, 2),
        dist_km_before_opt=round(dist_len_before, 2),
        opt_gain_pct=round((1.0 - dist_m_after / dist_m_before) * 100.0, 1) if dist_m_before > 0 else 0.0,
        opt_moves=n_moves_total, opt_merges=n_consol,
        drops_km=round(drop_km, 2), total_km=round(trunk_len + dist_len + drop_km, 2),
        trunk_fibers=trunk_fibers,
        drop_max_m=round(max((d[4] for d in drops), default=0.0), 1),
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
                    to=[hh_list[int(i)]['lat'], hh_list[int(i)]['lon']])
               for i in range(n_hh)],
        aerial=[[[a[0], a[1]], [b[0], b[1]]] for a, b in aerial_fallback] + aerial_polys,
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
        d = design_village2(hhj, osm)
        with open(os.path.join(OUT_DIR, f'{key}_design2.json'), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        s = d['stats']
        print(f"    ОРШ {s['splitters']}, магистраль {s['trunk_km']} км, распределение "
              f"{s['dist_km']} км (было {s['dist_km_before_opt']}, оптимизация -{s['opt_gain_pct']}%), "
              f"дропы {s['drops_km']} км, всего {s['total_km']} км, ср. загрузка портов "
              f"{s['n_hh'] / s['splitters'] / 32 * 100:.0f}%", flush=True)
        summary.append((d['name'], s))
    print('\n================ СВОДКА v2 ================')
    print(f"{'Село':<20}{'Абон.':>6}{'выявл.':>8}{'доб.':>6}{'ОРШ':>5}{'Маг.,км':>9}"
          f"{'Распр.,км':>10}{'Дропы,км':>9}{'Всего,км':>9}{'Опт.,%':>8}{'Загр.%':>7}")
    for name, s in summary:
        print(f"{name:<20}{s['n_hh']:>6}{s['n_identified']:>8}{s['n_added']:>6}{s['splitters']:>5}"
              f"{s['trunk_km']:>9}{s['dist_km']:>10}{s['drops_km']:>9}{s['total_km']:>9}"
              f"{s['opt_gain_pct']:>8}{s['n_hh'] / s['splitters'] / 32 * 100:>7.0f}")


if __name__ == '__main__':
    main()
