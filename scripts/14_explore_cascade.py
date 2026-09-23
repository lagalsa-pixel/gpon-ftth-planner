# -*- coding: utf-8 -*-
"""
Шаг 14 (разведка). Каскадная схема FTTH: анализ распределения ДХ по муфтам
и подбор параметров кластеризации РОР (сплиттеры 2-й ступени 1:8).

Каскад: 1:8 (ОРШ) x 1:8 (РОР) = 1:64, как и в централизованной схеме.
РОР ставится в муфте; ДХ соседних муфт в радиусе R_MAX (по сети) подключаются
к РОР, участок "муфта ДХ -> РОР" выполняется дроп-кабелем (2 волокна).
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

SPLIT2 = 8          # ёмкость сплиттера 2-й ступени
RESERVE = 1.25      # резерв волокон магистрали
MIN_FIBERS = 8


def nkey(p):
    return (round(p[0], 2), round(p[1], 2))


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
    for d in net['drops']:
        k = ck.get(d['coupler'])
        if k is None or k not in adj:
            k = root
        homes[k] += 1

    drops_km = sum(d['length_m'] for d in net['drops']) / 1000.0
    return dict(adj=adj, edge_len=edge_len, root=root, parent=parent, bfs=bfs,
                homes=homes, couplers=set(ck.values()), dh=len(net['drops']),
                drops_km=drops_km, feeder_m=sum(edge_len.values()))


def dijkstra_from(adj, edge_len, src, r_max):
    """Расстояния от src по дереву до r_max (метры)."""
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


def cluster(t, r_max, cap, min_cluster=5):
    """Жадная кластеризация: РОР в муфтах, ДХ в радиусе r_max, <= cap на РОР."""
    adj, edge_len, homes = t['adj'], t['edge_len'], t['homes']
    cands = [n for n in t['couplers'] if homes.get(n, 0) > 0]
    # расстояния кандидат -> кандидат (внутри r_max)
    cand_set = set(cands)
    dists = {}
    for c in cands:
        d = dijkstra_from(adj, edge_len, c, r_max)
        dists[c] = {o: dd for o, dd in d.items() if o in cand_set and o != c}

    unassigned = {n: homes[n] for n in cands}
    pops = []  # (узел РОР, [(узел источника, длина, число ДХ)])

    def reach(c):
        r = [(d, o, unassigned[o]) for o, d in dists[c].items() if unassigned.get(o, 0) > 0]
        r.append((0.0, c, unassigned.get(c, 0)))
        return r

    while any(n > 0 for n in unassigned.values()):
        best, best_total = None, -1
        for c in cands:
            if unassigned.get(c, 0) == 0 and not any(
                    unassigned.get(o, 0) > 0 for o in dists[c]):
                continue
            r = reach(c)
            total = sum(x[2] for x in r)
            if total > best_total or (total == best_total and best is not None
                                      and homes.get(c, 0) > homes.get(best, 0)):
                best, best_total = c, total
        if best is None:  # не должно случиться
            break
        r = reach(best)
        if best_total >= min_cluster:
            r.sort(key=lambda x: x[0])
        else:
            # остаточные мелкие группы: РОР в узле с максимумом ДХ, без ограничения радиуса выбора
            best = max((n for n in unassigned if unassigned[n] > 0),
                       key=lambda n: (unassigned[n], -t['bfs'].index(n) if n in t['bfs'] else 0))
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
    """Считает материалы каскадной схемы по кластерам РОР."""
    parent, bfs, edge_len = t['parent'], t['bfs'], t['edge_len']
    s_local = Counter()
    extra_m = 0.0
    for node, take in pops:
        dh = sum(k for _, _, k in take)
        for o, d, k in take:
            extra_m += d * k
        s_local[node] += math.ceil(dh / SPLIT2)
    n2 = sum(s_local.values())

    # сплиттеры в поддеревьях
    s_sub = dict(s_local)
    for u in reversed(bfs):
        p = parent[u]
        if p is not None:
            s_sub[p] = s_sub.get(p, 0) + s_sub.get(u, 0)

    pop_nodes = {n for n, _ in pops}
    trunk_m = 0.0
    fiber_m = 0.0
    top_fibers = 0
    branch_couplers = 0
    splices = 0
    for u in bfs:
        if u == t['root']:
            kids = [w for w in t['adj'][u] if parent[w] == u and s_sub.get(w, 0) > 0]
            splices += sum(s_sub[w] for w in kids)          # пигтейли на кроссе ОРШ
        if u in t['couplers'] and s_sub.get(u, 0) > 0:
            kids = [w for w in t['adj'][u] if parent[w] == u and s_sub.get(w, 0) > 0]
            if u in pop_nodes or len(kids) >= 2:
                splices += sum(s_sub[w] for w in kids)      # транзит через узел
            if u in pop_nodes:
                splices += s_local.get(u, 0)                # входы сплиттеров РОР
            if len(kids) >= 2 and u not in pop_nodes:
                branch_couplers += 1
    for (k1, k2), L in edge_len.items():
        child = k1 if parent.get(k1) == k2 else (k2 if parent.get(k2) == k1 else None)
        if child is None or s_sub.get(child, 0) == 0:
            continue
        trunk_m += L
        F = max(MIN_FIBERS, math.ceil(RESERVE * s_sub[child]))
        top_fibers = max(top_fibers, F)
        fiber_m += L * F

    dh = t['dh']
    fill = dh / (n2 * SPLIT2) if n2 else 0
    return dict(n_pop=len(pops), n2=n2, fill=round(fill, 3),
                extra_km=round(extra_m / 1000, 2),
                drop_total_km=round(t['drops_km'] + extra_m / 1000, 2),
                trunk_km=round(trunk_m / 1000, 2),
                fiber_km=round(fiber_m / 1000, 1),
                top_fibers=top_fibers,
                branch_couplers=branch_couplers,
                splices=splices)


def main():
    print('=== Распределение ДХ по обслуживающим муфтам ===')
    trees = {}
    for v in VILLAGES:
        t = load_tree(v)
        trees[v['key']] = t
        serving = {n: c for n, c in t['homes'].items() if c > 0}
        hist = Counter(min(c, 9) for c in serving.values())
        h = ' '.join(f'{i}x:{hist.get(i, 0)}' for i in range(1, 10))
        print(f"{v['name']:<18} ДХ {t['dh']:>4}  муфт всего {len(t['couplers']):>4}  "
              f"обслуживающих {len(serving):>4}  ср.ДХ/муфту {t['dh']/max(1,len(serving)):.1f}  [{h}] (9x=9+)")

    print('\n=== Сетка параметров: R_MAX x CAP ===')
    for r_max in (80, 100, 120):
        for cap in (8,):
            T = dict(n_pop=0, n2=0, extra=0.0, trunk=0.0, fiber=0.0, drop=0.0,
                     br=0, sp=0, dh=0)
            for v in VILLAGES:
                t = trees[v['key']]
                pops = cluster(t, r_max, cap)
                r = evaluate(t, pops)
                T['n_pop'] += r['n_pop']; T['n2'] += r['n2']; T['br'] += r['branch_couplers']
                T['sp'] += r['splices']; T['dh'] += t['dh']
                T['extra'] += r['extra_km']; T['trunk'] += r['trunk_km']
                T['fiber'] += r['fiber_km']; T['drop'] += r['drop_total_km']
            print(f"R={r_max:>3} CAP={cap:>2}: РОР {T['n_pop']:>4}  сплиттеров2 {T['n2']:>4}  "
                  f"заполнение {T['dh']/(T['n2']*8)*100:4.0f}%  доп.дроп {T['extra']:6.1f} км  "
                  f"дроп всего {T['drop']:6.1f} км  магистраль {T['trunk']:5.1f} км  "
                  f"волокно-км {T['fiber']:6.0f}  муфт(ветвл.) {T['br']:>4}  сварок {T['sp']:>5}")

    print('\n=== Детально: R_MAX=100, CAP=8 ===')
    for v in VILLAGES:
        t = trees[v['key']]
        pops = cluster(t, 100, 8)
        r = evaluate(t, pops)
        print(f"{v['name']:<18} ДХ {t['dh']:>4}  РОР {r['n_pop']:>4}  спл2 {r['n2']:>4}  "
              f"заполн. {r['fill']*100:4.0f}%  доп.дроп {r['extra_km']:6.2f} км  "
              f"дроп {r['drop_total_km']:6.2f} км  магистр {r['trunk_km']:5.2f} км  "
              f"вол-км {r['fiber_km']:6.0f}  верх {r['top_fibers']:>3}  "
              f"муфт {r['branch_couplers']:>3}  сварок {r['splices']:>5}")


if __name__ == '__main__':
    main()
