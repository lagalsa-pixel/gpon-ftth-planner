# -*- coding: utf-8 -*-
"""
Шаг 18 (разведка). Каскадная схема FTTH с соотношением 1:4 (ОРШ) x 1:16 (РОР) = 1:64.
Подбор параметров кластеризации РОР: SPLIT2=16 -> CAP=16, сетка R_MAX x MIN_CLUSTER.

Модель идентична шагу 15 (итоговой), только параметры кластеризации варьируются:
  - РОР в проектной муфте, кластер до CAP ДХ в радиусе R_MAX по трассе;
  - N2 = сумма ceil(ДХ кластера / 16) — при CAP=16 каждый РОР = 1 сплиттер 1:16;
  - волокна магистрали = ceil(1,25 x сплиттеры 2-й ступ. ниже по потоку), мин 8;
  - сплиттеры 1-й ступени 1:4 в ОРШ: ceil(N2 / 4).
"""
import json, math, heapq
from collections import defaultdict, Counter, deque

BASE = '/home/z/my-project'

VILLAGES = [
    dict(num='01', key='verhneberezovka', name='Верхнеберезовка', net='network.json'),
    dict(num='02', key='solnechnoe', name='Солнечное', net='network_v2.json'),
    dict(num='03', key='perevalnoe', name='Перевальное', net='network_v2.json'),
    dict(num='04', key='vinnoe', name='Винное', net='network_v2.json'),
    dict(num='05', key='prigorodnoe', name='Пригородное', net='network_v2.json'),
    dict(num='06', key='altaiskiy', name='Алтайский', net='network_v2.json'),
]

SPLIT1 = 4
SPLIT2 = 16
FIBER_RESERVE = 1.25
MIN_FIBERS = 8


def nkey(p):
    return (round(p[0], 2), round(p[1], 2))


def dijkstra_from(adj, edge_len, src, r_max):
    dist = {src: 0.0}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue
        for w in adj[u]:
            nd = d + edge_len[(min(u, w), max(u, w))]
            if nd <= r_max and nd < dist.get(w, math.inf):
                dist[w] = nd
                heapq.heappush(pq, (nd, w))
    return dist


def load_tree(v):
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[v['key']]
    mpp = geo['mpp']
    net = json.load(open(f"{BASE}/work/{v['key']}/{v['net']}"))

    adj = defaultdict(set)
    edge_len = {}
    for e in net['feeder_edges']:
        k1, k2 = nkey(e[0]), nkey(e[1])
        if k1 == k2:
            continue
        L = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * mpp
        adj[k1].add(k2)
        adj[k2].add(k1)
        edge_len[(min(k1, k2), max(k1, k2))] = L

    ax, ay = net['anchor']['x'], net['anchor']['y']
    root = min(adj.keys(), key=lambda k: (k[0] - ax) ** 2 + (k[1] - ay) ** 2)

    parent = {root: None}
    order = deque([root])
    bfs = [root]
    while order:
        u = order.popleft()
        for w in adj[u]:
            if w not in parent:
                parent[w] = u
                bfs.append(w)
                order.append(w)

    ck = {}
    for c in net['couplers']:
        ck[c['node']] = nkey([c['x'], c['y']])
    homes = Counter()
    drop_at = {}
    for d in net['drops']:
        k = ck.get(d['coupler'])
        if k is None or k not in adj:
            k = root
        homes[k] += 1
        drop_at[len(drop_at)] = (k, d['length_m'])

    return dict(adj=adj, edge_len=edge_len, root=root, parent=parent, bfs=bfs,
                homes=homes, drop_at=drop_at, couplers=set(ck.values()),
                dh=len(net['drops']), feeder_m=sum(edge_len.values()))


def cluster(t, r_max, cap, min_cluster):
    adj, edge_len, homes = t['adj'], t['edge_len'], t['homes']
    cands = [n for n in t['couplers'] if homes.get(n, 0) > 0]
    cand_set = set(cands)
    dists = {}
    for c in cands:
        d = dijkstra_from(adj, edge_len, c, r_max)
        dists[c] = {o: dd for o, dd in d.items() if o in cand_set and o != c}

    unassigned = {n: homes[n] for n in cands}
    pops = []

    def reach(c):
        r = [(dd, o, unassigned[o]) for o, dd in dists[c].items() if unassigned.get(o, 0) > 0]
        if unassigned.get(c, 0) > 0:
            r.append((0.0, c, unassigned[c]))
        return r

    while any(n > 0 for n in unassigned.values()):
        best, best_total = None, -1
        for c in cands:
            r = reach(c)
            total = sum(x[2] for x in r)
            if total > best_total or (total == best_total and best is not None
                                      and homes.get(c, 0) > homes.get(best, 0)):
                best, best_total = c, total
        if best is None:
            break
        if best_total < min_cluster:
            pos = {n: i for i, n in enumerate(t['bfs'])}
            best = max((n for n in unassigned if unassigned[n] > 0),
                       key=lambda n: (unassigned[n], -pos.get(n, len(t['bfs']))))
        r = reach(best)
        r.sort(key=lambda x: x[0])
        take, cnt = [], 0
        for d, o, n in r:
            if cnt >= cap:
                break
            k = min(n, cap - cnt)
            take.append((o, d, k))
            cnt += k
        pops.append((best, take))
        for o, d, k in take:
            unassigned[o] -= k
    return pops


def evaluate(t, pops):
    """Метрики каскадной модели (как в шаге 15, без запасов — для сравнения вариантов)."""
    parent, bfs, edge_len, adj = t['parent'], t['bfs'], t['edge_len'], t['adj']

    s_local = Counter()
    pop_of_source = {}
    for node, take in pops:
        dh = sum(k for _, _, k in take)
        s_local[node] += math.ceil(dh / SPLIT2)
        for o, d, k in take:
            pop_of_source[o] = (node, d)
    n2 = sum(s_local.values())
    pop_nodes = {n for n, _ in pops}

    drop_total_m = 0.0
    ext_total_m = 0.0
    max_drop_m = 0.0
    for idx, (k, lm) in t['drop_at'].items():
        node, ext = pop_of_source.get(k, (t['root'], 0.0))
        drop_total_m += lm + ext
        ext_total_m += ext
        max_drop_m = max(max_drop_m, lm + ext)

    s_sub = dict(s_local)
    for u in reversed(bfs):
        p = parent[u]
        if p is not None:
            s_sub[p] = s_sub.get(p, 0) + s_sub.get(u, 0)

    def trunk_kids(u):
        return [w for w in adj[u] if parent.get(w) == u and s_sub.get(w, 0) > 0]

    trunk_m = 0.0
    fiber_m = 0.0
    top_fibers = 0
    mufty_branch = 0
    welds = 0

    def F_of(child):
        return max(MIN_FIBERS, math.ceil(FIBER_RESERVE * s_sub.get(child, 0)))

    welds += sum(s_sub[w] for w in trunk_kids(t['root']))

    for u in bfs:
        if u not in t['couplers'] or s_sub.get(u, 0) == 0:
            continue
        kids = trunk_kids(u)
        if u in pop_nodes:
            welds += s_local.get(u, 0)
        if not kids:
            continue
        cont = max(kids, key=lambda c: (F_of(c), s_sub.get(c, 0)))
        for c in kids:
            dF = F_of(u) - F_of(c)
            if c == cont:
                if dF > 0:
                    welds += min(s_sub.get(c, 0), dF)
            else:
                welds += s_sub.get(c, 0)
        if len(kids) >= 2 and u not in pop_nodes:
            mufty_branch += 1

    for (k1, k2), L in edge_len.items():
        child = k1 if parent.get(k1) == k2 else (k2 if parent.get(k2) == k1 else None)
        if child is None or s_sub.get(child, 0) == 0:
            continue
        trunk_m += L
        F = F_of(child)
        top_fibers = max(top_fibers, F)
        fiber_m += L * F

    dh = t['dh']
    return dict(
        dh=dh, n_pop=len(pops), n2=n2,
        splitters1=math.ceil(round(n2 / SPLIT1, 6)),
        fill=round(100.0 * dh / (n2 * SPLIT2), 1),
        dh_per_pop=round(dh / len(pops), 1),
        ext_km=round(ext_total_m / 1000.0, 2),
        drop_km=round(drop_total_m / 1000.0, 2),
        max_drop_m=round(max_drop_m, 1),
        trunk_km=round(trunk_m / 1000.0, 2),
        fiber_km=round(fiber_m / 1000.0, 1),
        top_fibers=top_fibers,
        mufty=mufty_branch,
        welds=welds,
    )


def main():
    trees = {}
    for v in VILLAGES:
        trees[v['key']] = load_tree(v)
    print('Деревья загружены. Сетка: R_MAX x MIN_CLUSTER (SPLIT2=16, CAP=16)\n')

    hdr = (f"{'R/MIN':>8}{'POP':>5}{'N2':>5}{'спл1':>5}{'заполн%':>8}{'ДХ/РОР':>7}"
           f"{'подводки':>9}{'дроп':>7}{'макс.дроп':>10}{'магистр':>8}{'вол-км':>7}{'муфты':>6}{'сварки':>7}")
    print(hdr)
    for r_max in (100, 125, 150, 175, 200):
        for min_cluster in (5, 10):
            T = dict(n_pop=0, n2=0, spl1=0, dh=0, ext=0.0, drop=0.0, trunk=0.0,
                     fiber=0.0, mufty=0, welds=0, maxdrop=0.0)
            for v in VILLAGES:
                t = trees[v['key']]
                pops = cluster(t, float(r_max), 16, min_cluster)
                r = evaluate(t, pops)
                T['n_pop'] += r['n_pop']; T['n2'] += r['n2']; T['spl1'] += r['splitters1']
                T['dh'] += r['dh']; T['ext'] += r['ext_km']; T['drop'] += r['drop_km']
                T['trunk'] += r['trunk_km']; T['fiber'] += r['fiber_km']
                T['mufty'] += r['mufty']; T['welds'] += r['welds']
                T['maxdrop'] = max(T['maxdrop'], r['max_drop_m'])
            fill = 100.0 * T['dh'] / (T['n2'] * SPLIT2)
            print(f"{r_max:>4}/{min_cluster:<3}{T['n_pop']:>5}{T['n2']:>5}{T['spl1']:>5}{fill:>8.1f}"
                  f"{T['dh']/T['n_pop']:>7.1f}{T['ext']:>9.1f}{T['drop']:>7.1f}{T['maxdrop']:>10.0f}"
                  f"{T['trunk']:>8.1f}{T['fiber']:>7.0f}{T['mufty']:>6}{T['welds']:>7}")

    print('\nСправочно, каскад 1:8x1:8 (шаг 15, R=100/CAP=8): РОР 515, спл2 515, спл1 66, '
          'заполнение 56.6%, подводки 71.4 км, дроп 162.3 км, магистраль 66.9 км, '
          'волокно-км 1256, муфты 115, сварки ~2350 (до запаса).')


if __name__ == '__main__':
    main()
