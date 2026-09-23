#!/usr/bin/env python3
"""Проектирование оптической сети FTTH (GPON) для сёл ВКО.

Топология: POP (точка приседания в центре села) -> магистральный кабель вдоль дорог ->
шкафы-сплиттеры GPON 1:32 (кластеры домохозяйств <= 32) -> распределительный кабель
вдоль улиц -> дроповые линии к каждому домохозяйству.
Маршрутизация — по графу дорог OSM (кратчайшие пути), не по прямым."""
import heapq, json, math, os, sys
from collections import defaultdict, deque
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OSM_DIR = os.path.join(BASE, 'osm_ftth')
HH_DIR = os.path.join(BASE, 'ftth_out')
OUT_DIR = os.path.join(BASE, 'ftth_out')

# ---- параметры проектирования ----
SPLITTER_MAX = 32        # портов GPON 1:32
SPLITTER_TARGET = 28     # целевое ДХ на сплиттер (запас портов)
CLUSTER_MIN = 8          # мелкие кластеры объединяются
GRAPH_MARGIN = 500.0     # м: дороги вне зоны села + запас
AERIAL_MERGE_MAX = 500.0 # м: воздушные перемычки между компонентами графа
TRUNK_SLACK = 1.07       # технологический запас магистрали/распределения
DROP_ENTRY_M = 15.0      # м: ввод в здание на каждый дроп
MAX_SPLITTER_CANDIDATES = 8
FIBER_SERIES = [8, 12, 16, 24, 32, 48, 64, 72, 96, 144]
DIST_FIBER_SERIES = [8, 12, 16, 24, 32]

ROAD_OK = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
    'residential', 'living_street', 'service', 'track', 'road', 'motorway_link',
    'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
}
ROAD_BAD_SERVICE = {'parking_aisle', 'drive-through', 'driveway_marker'}


def local_frame(lat0):
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(lat0))
    return ky, kx


def to_xy(lat, lon, ky, kx):
    return (lat * ky, lon * kx)


def build_graph(osm_data, ky, kx, lat_min, lon_min, lat_max, lon_max):
    """Граф дорог: узлы (lat,lon)->id, рёбра с весами в метрах. Только в bbox+запас."""
    node_id = {}
    nodes = []
    adj = defaultdict(list)

    def get_node(lat, lon):
        key = (round(lat, 7), round(lon, 7))
        i = node_id.get(key)
        if i is None:
            i = len(nodes)
            node_id[key] = i
            nodes.append((lat, lon))
        return i

    m_lat = GRAPH_MARGIN / ky
    m_lon = GRAPH_MARGIN / kx
    lo_lat, hi_lat = lat_min - m_lat, lat_max + m_lat
    lo_lon, hi_lon = lon_min - m_lon, lon_max + m_lon

    n_ways = 0
    for el in osm_data['elements']:
        if el['type'] != 'way' or 'geometry' not in el:
            continue
        t = el.get('tags', {})
        hw = t.get('highway')
        if hw is None or hw not in ROAD_OK:
            continue
        if hw == 'service' and t.get('service') in ROAD_BAD_SERVICE:
            continue
        pts = [(p['lat'], p['lon']) for p in el['geometry']]
        # хотя бы одна точка в расширенном bbox
        if not any(lo_lat <= la <= hi_lat and lo_lon <= lo <= hi_lon for la, lo in pts):
            continue
        ids = []
        for la, lo in pts:
            if lo_lat <= la <= hi_lat and lo_lon <= lo <= hi_lon:
                ids.append(get_node(la, lo))
            else:
                ids.append(None)
        prev = None
        for cur in ids:
            if cur is not None and prev is not None:
                (pa, pb) = nodes[prev], nodes[cur]
                w = math.hypot((pa[0] - pb[0]) * ky, (pa[1] - pb[1]) * kx)
                if w > 0.5:
                    adj[prev].append((cur, w))
                    adj[cur].append((prev, w))
            if cur is not None:
                prev = cur
        n_ways += 1
    return nodes, adj, n_ways


def components(adj, n_nodes):
    comp = [-1] * n_nodes
    c = 0
    for s in range(n_nodes):
        if comp[s] != -1 or s not in adj:
            continue
        comp[s] = c
        dq = deque([s])
        while dq:
            u = dq.popleft()
            for v, _ in adj[u]:
                if comp[v] == -1:
                    comp[v] = c
                    dq.append(v)
        c += 1
    return comp, c


def merge_components(nodes, adj, ky, kx, max_d=AERIAL_MERGE_MAX):
    """Соединяет компоненты графа воздушными перемычками (< max_d)."""
    aerials = []
    guard = 0
    while guard < 60:
        guard += 1
        n = len(nodes)
        comp, nc = components(adj, n)
        if nc <= 1:
            break
        # узлы по компонентам
        by_comp = defaultdict(list)
        for i in range(n):
            if i in adj:
                by_comp[comp[i]].append(i)
        # ближайшая пара между разными компонентами
        best = None  # (d, u, v)
        comp_ids = sorted(by_comp, key=lambda c: len(by_comp[c]))
        small = by_comp[comp_ids[0]]
        small_xy = np.array([to_xy(*nodes[i], ky, kx) for i in small])
        for cj in comp_ids[1:]:
            other_xy = np.array([to_xy(*nodes[i], ky, kx) for i in by_comp[cj]])
            dd = np.sqrt(((small_xy[:, None, :] - other_xy[None, :, :]) ** 2).sum(-1))
            ii, jj = np.unravel_index(np.argmin(dd), dd.shape)
            if best is None or dd[ii, jj] < best[0]:
                best = (float(dd[ii, jj]), small[ii], by_comp[cj][jj])
        if best is None or best[0] > max_d:
            break
        d, u, v = best
        adj[u].append((v, d))
        adj[v].append((u, d))
        aerials.append((u, v, d))
    return aerials


def dijkstra(adj, src, targets=None, max_pop=None):
    """Кратчайшие пути от src. targets: множество узлов (раннее завершение)."""
    dist = {src: 0.0}
    prev = {}
    seen = set()
    heap = [(0.0, src)]
    remaining = set(targets) if targets else None
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if remaining is not None:
            remaining.discard(u)
            if not remaining:
                break
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, prev


def path_to(prev, tgt):
    path = [tgt]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def snap_to_edges(nodes, adj, ky, kx, hh_list):
    """Привязка ДХ к ближайшим рёбрам графа (виртуальные узлы)."""
    edges = []
    seen_e = set()
    for u in adj:
        for v, w in adj[u]:
            e = (min(u, v), max(u, v))
            if e in seen_e:
                continue
            seen_e.add(e)
            edges.append((u, v))
    EA = np.array([to_xy(*nodes[u], ky, kx) for u, v in edges])
    EB = np.array([to_xy(*nodes[v], ky, kx) for u, v in edges])
    if len(edges) == 0:
        return {}, []
    D = EB - EA                       # (m,2)
    DD = (D * D).sum(1)               # (m,)
    DD[DD == 0] = 1e-9
    snaps = {}
    drops = []
    for i, h in enumerate(hh_list):
        P = np.array(to_xy(h['lat'], h['lon'], ky, kx))
        t = ((P - EA) * D).sum(1) / DD
        tc = np.clip(t, 0.0, 1.0)
        Proj = EA + tc[:, None] * D
        dd = np.sqrt(((P - Proj) ** 2).sum(1))
        j = int(np.argmin(dd))
        u, v = edges[j]
        plon = Proj[j][1] / kx
        plat = Proj[j][0] / ky
        vid = len(nodes)
        nodes.append((plat, plon))   # виртуальный узел на ребре
        du = math.hypot(*(Proj[j] - EA[j]))
        dv = math.hypot(*(EB[j] - Proj[j]))
        if du > 0.5:
            adj[u].append((vid, du))
            adj[vid].append((u, du))
        if dv > 0.5:
            adj[v].append((vid, dv))
            adj[vid].append((v, dv))
        snaps[i] = dict(vid=vid, snap_lat=plat, snap_lon=plon,
                        drop_m=float(dd[j]))
        drops.append((plat, plon, h['lat'], h['lon'], float(dd[j])))
    return snaps, drops


def kmeans(points, k, seed=42, iters=80):
    n = len(points)
    if k >= n:
        return np.arange(n) % k, points.copy()
    rng = np.random.default_rng(seed)
    # k-means++ инициализация
    centers = [points[rng.integers(n)]]
    for _ in range(k - 1):
        d2 = np.min(((points[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(-1), axis=1)
        tot = d2.sum()
        if tot <= 0:
            centers.append(points[rng.integers(n)])
            continue
        centers.append(points[rng.choice(n, p=d2 / tot)])
    C = np.array(centers, dtype=float)
    lab = np.zeros(n, dtype=int)
    for _ in range(iters):
        d2 = ((points[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        lab = d2.argmin(1)
        newC = C.copy()
        for j in range(k):
            m = lab == j
            if m.any():
                newC[j] = points[m].mean(0)
        if np.allclose(newC, C, atol=0.3):
            C = newC
            break
        C = newC
    return lab, C


def split_oversized(points, lab, max_size):
    """Рекурсивное деление кластеров больше max_size (2-means)."""
    out = lab.copy()
    nxt = int(lab.max()) + 1 if len(lab) else 0
    for j in range(int(lab.max()) + 1 if len(lab) else 0):
        idx = np.where(lab == j)[0]
        if len(idx) <= max_size:
            continue
        # деление на 2 части по главной оси, затем k-means
        sub, _ = kmeans(points[idx], 2, seed=7)
        for s in (0, 1):
            m = idx[sub == s]
            out[m] = nxt if s == 1 else j
        nxt += 1
        # рекурсивно, если половина всё ещё велика
        half = idx[sub == 0]
        if len(half) > max_size:
            out2, _n2 = None, None
            # обрабатываем итеративно ниже (повторный проход)
    # повторные проходы, пока есть перегруз
    for _ in range(6):
        over = False
        for j in range(int(out.max()) + 1):
            idx = np.where(out == j)[0]
            if len(idx) > max_size:
                over = True
                sub, _ = kmeans(points[idx], 2, seed=7)
                for s in (0, 1):
                    m = idx[sub == s]
                    out[m] = nxt if s == 1 else j
                nxt += 1
        if not over:
            break
    return out


def merge_small(points, lab, min_size, max_size):
    """Слияние мелких кластеров с ближайшими."""
    lab = lab.copy()
    while True:
        ids = np.unique(lab)
        centers = {j: points[lab == j].mean(0) for j in ids}
        small = [j for j in ids if (lab == j).sum() < min_size]
        if not small:
            break
        moved = False
        for j in small:
            cj = centers[j]
            best, bestd = None, 1e18
            for k2 in ids:
                if k2 == j:
                    continue
                d = math.hypot(*(centers[k2] - cj))
                if d < bestd and (lab == k2).sum() + (lab == j).sum() <= max_size:
                    best, bestd = k2, d
            if best is not None and bestd < 600.0:
                lab[lab == j] = best
                moved = True
                break
        if not moved:
            break
    # перенумерация
    ids = np.unique(lab)
    remap = {j: i for i, j in enumerate(ids)}
    return np.array([remap[j] for j in lab])


def tree_polylines(nodes, used_edges):
    """Сшивает рёбра дерева в полилинии для отрисовки."""
    adjt = defaultdict(list)
    for (u, v) in used_edges:
        adjt[u].append(v)
        adjt[v].append(u)
    visited_e = set()
    polys = []
    # цепочки: начинаем с концов (deg 1) и ветвлений
    starts = [u for u in adjt if len(adjt[u]) != 2]
    if not starts and adjt:
        starts = [next(iter(adjt))]
    done = set()
    for s in starts:
        if s in done and len(adjt[s]) <= 2:
            continue
        for nxt in adjt[s]:
            e = (min(s, nxt), max(s, nxt))
            if e in visited_e:
                continue
            chain = [s, nxt]
            visited_e.add(e)
            cur = nxt
            prev = s
            while len(adjt[cur]) == 2 and cur not in done:
                a, b = adjt[cur]
                step = a if a != prev else b
                e2 = (min(cur, step), max(cur, step))
                if e2 in visited_e:
                    break
                visited_e.add(e2)
                chain.append(step)
                prev, cur = cur, step
            polys.append([nodes[i] for i in chain])
            done.add(s)
    # отдельные циклы
    for u in adjt:
        for nxt in adjt[u]:
            e = (min(u, nxt), max(u, nxt))
            if e not in visited_e:
                visited_e.add(e)
                polys.append([nodes[u], nodes[nxt]])
    return polys


def design_village(hhj, osm_data):
    key = hhj['key']
    hh_list = hhj['households']
    n_hh = len(hh_list)
    anchor = hhj['anchor']
    ky, kx = local_frame(anchor[0])

    lat_min, lon_min, lat_max, lon_max = hhj['bbox']
    nodes, adj, n_ways = build_graph(osm_data, ky, kx, lat_min, lon_min, lat_max, lon_max)
    aerials = merge_components(nodes, adj, ky, kx)
    snaps, drops = snap_to_edges(nodes, adj, ky, kx, hh_list)
    n_real_ways = n_ways

    # ---- кластеризация ДХ ----
    pts = np.array([to_xy(h['lat'], h['lon'], ky, kx) for h in hh_list])
    k = max(1, math.ceil(n_hh / SPLITTER_TARGET))
    lab, C = kmeans(pts, k, seed=42)
    lab = split_oversized(pts, lab, SPLITTER_MAX)
    lab = merge_small(pts, lab, CLUSTER_MIN, SPLITTER_MAX)
    n_cl = int(lab.max()) + 1

    # ---- POP: узел графа, ближайший к центроиду всех ДХ ----
    centroid = pts.mean(0)
    node_xy = np.array([to_xy(*nodes[i], ky, kx) for i in range(len(nodes))]) if nodes else np.zeros((1, 2))
    d_pop = np.sqrt(((node_xy - centroid) ** 2).sum(1))
    order = np.argsort(d_pop)
    pop_id = int(order[0])
    for c in order:            # первый узел, у которого есть рёбра
        if int(c) in adj:
            pop_id = int(c)
            break

    # ---- размещение сплиттеров: кандидатные узлы графа около центров кластеров ----
    splitters = []
    for j in range(n_cl):
        idx = np.where(lab == j)[0]
        cc = pts[idx].mean(0)
        d_node = np.sqrt(((node_xy - cc) ** 2).sum(1))
        cand_ids = np.argsort(d_node)[:MAX_SPLITTER_CANDIDATES]
        vids = [snaps[int(i)]['vid'] for i in idx]
        best_id, best_tot = None, 1e18
        for c in cand_ids:
            c = int(c)
            if c not in adj:
                continue
            dist, _ = dijkstra(adj, c, targets=set(vids))
            tot = sum(dist.get(v, 1e9) for v in vids)
            if tot < best_tot:
                best_tot, best_id = tot, c
        if best_id is None:
            best_id = int(cand_ids[0])
        splitters.append(dict(node=best_id, lat=nodes[best_id][0], lon=nodes[best_id][1],
                              hh=len(idx), members=idx.tolist()))

    # ---- магистраль: объединение кратчайших путей POP -> сплиттеры ----
    dist_t, prev_t = dijkstra(adj, pop_id)
    used_trunk = set()
    trunk_km = 0.0
    unreachable = []
    for s in splitters:
        if s['node'] in dist_t:
            p = path_to(prev_t, s['node'])
            for a, b in zip(p[:-1], p[1:]):
                e = (min(a, b), max(a, b))
                if e not in used_trunk:
                    used_trunk.add(e)
                    wa = dict(adj[a]).get(b)
                    trunk_km += wa if wa else 0.0
        else:
            unreachable.append(s)
    # воздушные перемычки графа, вошедшие в магистраль/распределение, считаем отдельно
    aerial_set = {(min(u, v), max(u, v)) for u, v, _ in aerials}

    # ---- распределение: сплиттер -> снапы ДХ кластера ----
    used_dist = set()
    dist_km = 0.0
    aerial_fallback = []
    for s in splitters:
        vids = [snaps[int(i)]['vid'] for i in s['members']]
        dist_s, prev_s = dijkstra(adj, s['node'], targets=set(vids))
        for i in s['members']:
            v = snaps[int(i)]['vid']
            if v in dist_s:
                p = path_to(prev_s, v)
                for a, b in zip(p[:-1], p[1:]):
                    e = (min(a, b), max(a, b))
                    if e not in used_dist:
                        used_dist.add(e)
                        w = dict(adj[a]).get(b)
                        dist_km += w if w else 0.0
            else:
                # воздушная линия напрямую от сплиттера
                aerial_fallback.append([nodes[s['node']], (hh_list[int(i)]['lat'], hh_list[int(i)]['lon'])])

    # ---- дропы ----
    drop_km = sum(d[4] for d in drops) / 1000.0 + n_hh * DROP_ENTRY_M / 1000.0

    # ---- полилинии для отрисовки ----
    trunk_polys = tree_polylines(nodes, used_trunk)
    dist_polys = tree_polylines(nodes, used_dist - used_trunk)
    aerial_polys = []
    for (u, v) in (used_trunk | used_dist):
        if (u, v) in aerial_set:
            aerial_polys.append([nodes[u], nodes[v]])

    # ---- длины с запасом ----
    trunk_len = trunk_km / 1000.0 * TRUNK_SLACK
    dist_len = dist_km / 1000.0 * TRUNK_SLACK

    # ---- волокна ----
    def round_series(x, series):
        for s in series:
            if x <= s:
                return s
        return series[-1]
    trunk_fibers = round_series(int(math.ceil(n_cl * 1.3)), FIBER_SERIES)
    dist_fibers = {}
    for s in splitters:
        dist_fibers[s['node']] = round_series(int(math.ceil(s['hh'] * 1.2)), DIST_FIBER_SERIES)

    # сведение сплиттеров
    spl_out = []
    for num, s in enumerate(sorted(splitters, key=lambda s: (s['lon'], s['lat'])), 1):
        spl_out.append(dict(id=f'S{num}', lat=s['lat'], lon=s['lon'], hh=s['hh'],
                            fibers=dist_fibers[s['node']]))

    stats = dict(
        n_hh=n_hh, expected=hhj['expected'], splitters=n_cl,
        avg_hh_per_splitter=round(n_hh / n_cl, 1),
        trunk_km=round(trunk_len, 2), dist_km=round(dist_len, 2),
        drops_km=round(drop_km, 2),
        total_km=round(trunk_len + dist_len + drop_km, 2),
        trunk_fibers=trunk_fibers,
        drop_max_m=round(max((d[4] for d in drops), default=0.0), 1),
        road_ways=n_real_ways, road_nodes=len(nodes),
        aerial_edges=len(aerial_polys) + len(aerial_fallback),
        coverage_pct=round(n_hh / hhj['expected'] * 100),
    )
    return dict(
        key=key, name=hhj['name'], district=hhj['district'], okrug=hhj['okrug'],
        expected=hhj['expected'], anchor=anchor, bbox=hhj['bbox'],
        n_hh=n_hh,
        pop=dict(lat=nodes[pop_id][0], lon=nodes[pop_id][1]),
        splitters=spl_out,
        households=hh_list,
        trunk_polylines=trunk_polys,
        dist_polylines=dist_polys,
        drops=[dict(n=hh_list[int(i)]['n'],
                    snap=[snaps[int(i)]['snap_lat'], snaps[int(i)]['snap_lon']],
                    to=[hh_list[int(i)]['lat'], hh_list[int(i)]['lon']])
               for i in range(n_hh)],
        aerial=[[[a[0], a[1]], [b[0], b[1]]] for a, b in aerial_fallback] + aerial_polys,
        stats=stats,
    )


def main():
    keys = sys.argv[1:] or [v['key'] for v in __import__('ftth_households').VILLAGES]
    sys.path.insert(0, BASE)
    summary = []
    for key in keys:
        hhj = json.load(open(os.path.join(HH_DIR, f'{key}_hh.json')))
        osm = json.load(open(os.path.join(OSM_DIR, f'{key}.json')))
        print(f"[{key}] ДХ {hhj['n'] if 'n' in hhj else len(hhj['households'])}...", end=' ', flush=True)
        d = design_village(hhj, osm)
        with open(os.path.join(OUT_DIR, f'{key}_design.json'), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        s = d['stats']
        print(f"сплиттеров {s['splitters']}, магистраль {s['trunk_km']} км, "
              f"распределение {s['dist_km']} км, дропы {s['drops_km']} км, всего {s['total_km']} км")
        summary.append((d['name'], s))
    print('\n================ СВОДКА ================')
    print(f"{'Село':<20}{'ДХ':>5}{'Ожид.':>6}{'Спл.':>5}{'Маг.,км':>9}{'Распр.,км':>10}{'Дропы,км':>9}{'Всего,км':>9}")
    for name, s in summary:
        print(f"{name:<20}{s['n_hh']:>5}{s['expected']:>6}{s['splitters']:>5}"
              f"{s['trunk_km']:>9}{s['dist_km']:>10}{s['drops_km']:>9}{s['total_km']:>9}")


if __name__ == '__main__':
    main()
