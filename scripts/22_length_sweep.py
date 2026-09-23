# -*- coding: utf-8 -*-
"""
Шаг 22. Параметрический анализ размещения РОР по критерию МИНИМАЛЬНОЙ ДЛИНЫ
ДРОПОВ И КАБЕЛЕЙ (суммарная физическая длина кабельной продукции с запасами).

Контекст: рассчитаны три схемы на одних и тех же сетях (топология не менялась):
  A) централизованная 1:64 (сплиттеры в ОРШ, дропы от проектных муфт);
  B) каскад 1:8 x 1:8 (РОР = муфта, кластер до 8 ДХ в радиусе 100 м);
  C) каскад 1:4 x 1:16 (РОР = муфта, кластер до 16 ДХ в радиусе 150 м).

Длина дропов и магистрального кабеля зависит от соотношения:
  больше РОР (меньше радиус)  -> короче подводки РОР->ДХ, но больше волокон
                                  магистрали (1,25 x N2) и длиннее ствол;
  меньше РОР (больше радиус)  -> короче магистраль и меньше волокно-км,
                                  но длиннее дроп-подводки.
Соотношение сплиттеров (1:8x1:8 / 1:4x1:16) на длины НЕ влияет (N2 = числу РОР
при CAP = ёмкости сплиттера 2-й ступени) — влияет только размещение РОР.

Модель и код кластеризации — в точности как в шагах 15/19 (проверено diff-ом:
nkey/decompose/load_tree/cluster идентичны). Сетка: R_MAX x CAP, MIN_CLUSTER=5.

Критерии:
  ОСНОВНОЙ (по запросу): L = дроп-кабель (с запасом 5 %) + магистральный кабель
                          (сумма позиций ВОД по ёмкостям, с запасом 10 %), км;
  КОНТРОЛЬНЫЙ: волокно-км (материалоёмкость / прокси стоимости магистрали).
Справочно: L_raw = то же без округления позиций до 0,1 км (для гладкости).

Выход: work/length_sweep.json + консольная таблица.
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

FIBER_RESERVE = 1.25
MIN_FIBERS = 8
STD_FIBERS = [8, 12, 16, 24, 32, 48, 64, 72, 96]
CABLE_STOCK = 1.10
DROP_STOCK = 1.05
CONSUM_STOCK = 1.10
MIN_CLUSTER = 5

R_GRID = [0, 50, 75, 100, 125, 150, 175, 200, 250]
CAP_GRID = [8, 16]


def nkey(p):
    return (round(p[0], 2), round(p[1], 2))


def decompose(F):
    if F <= STD_FIBERS[-1]:
        for s in STD_FIBERS:
            if s >= F:
                return [s]
    n96, rem = divmod(F, STD_FIBERS[-1])
    out = [STD_FIBERS[-1]] * n96
    if rem > 0:
        for s in STD_FIBERS:
            if s >= rem:
                out.append(s)
                break
    return out


def roundup(x, step=0.1):
    return math.ceil(x / step - 1e-9) * step


def ceilr(x):
    return math.ceil(round(x, 6))


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


def cluster(t, r_max, cap):
    """Жадная кластеризация РОР: узел с максимумом достижимых ДХ (как в шагах 15/19)."""
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
        if best_total < MIN_CLUSTER:
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


def analyse(t, r_max, cap):
    """Метрики одного села для конфигурации (r_max, cap). split2 = cap, split1 = 64/cap."""
    split2, split1 = cap, 64 // cap
    pops = cluster(t, r_max, cap)
    parent, bfs, edge_len, adj = t['parent'], t['bfs'], t['edge_len'], t['adj']

    s_local = Counter()
    pop_of_source = {}
    for node, take in pops:
        dh = sum(k for _, _, k in take)
        s_local[node] += math.ceil(dh / split2)
        for o, d, k in take:
            pop_of_source[o] = (node, d)
    n2 = sum(s_local.values())
    pop_nodes = {n for n, _ in pops}

    drop_total_m = 0.0
    max_drop_m = 0.0
    ext_total_m = 0.0
    for idx, (k, lm) in t['drop_at'].items():
        node, ext = pop_of_source.get(k, (t['root'], 0.0))
        drop_total_m += lm + ext
        max_drop_m = max(max_drop_m, lm + ext)
        if ext > 0:
            ext_total_m += ext

    s_sub = dict(s_local)
    for u in reversed(bfs):
        p = parent[u]
        if p is not None:
            s_sub[p] = s_sub.get(p, 0) + s_sub.get(u, 0)

    def trunk_kids(u):
        return [w for w in adj[u] if parent.get(w) == u and s_sub.get(w, 0) > 0]

    km_by_size = defaultdict(float)
    fiber_m = 0.0
    trunk_m = 0.0
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
        for s in decompose(F):
            km_by_size[s] += L / 1000.0
            fiber_m += L / 1000.0 * s

    total_cable_km = sum(km_by_size.values())
    dh = t['dh']
    cable_km_boq = {str(s): round(roundup(km_by_size.get(s, 0.0) * CABLE_STOCK), 1)
                    for s in STD_FIBERS if km_by_size.get(s, 0.0) > 0}
    cable_boq_km = round(sum(cable_km_boq.values()), 1)
    drop_cable_km = round(roundup(drop_total_m / 1000.0 * DROP_STOCK), 1)

    return dict(
        dhx_served=dh,
        couplers_project=len(t['couplers']),
        feeder_km=round(t['feeder_m'] / 1000.0, 2),
        n_pop=len(pops),
        n_pop_nodes=len(pop_nodes),
        n2=n2,
        splitters1=ceilr(n2 / split1),
        fill_pct=round(100.0 * dh / (n2 * split2), 1),
        dh_per_pop=round(dh / len(pops), 1),
        extra_km=round(ext_total_m / 1000.0, 2),
        drop_km_total=round(drop_total_m / 1000.0, 2),
        drop_cable_km=drop_cable_km,
        avg_drop_m=round(drop_total_m / max(1, dh), 1),
        max_drop_m=round(max_drop_m, 1),
        trunk_km=round(trunk_m / 1000.0, 2),
        top_fibers=top_fibers,
        fiber_km=round(fiber_m, 1),
        cable_km_raw=round(total_cable_km * CABLE_STOCK, 2),
        cable_boq_km=cable_boq_km,
        cable_km=cable_km_boq,
        mufty_branch=mufty_branch,
        splices=ceilr(welds * CONSUM_STOCK),
    )


def main():
    trees = {v['key']: load_tree(v) for v in VILLAGES}

    # --- инварианты сетей (те же, что во всех прежних расчётах) ---
    cent = json.load(open(f'{BASE}/work/boq_data.json', encoding='utf-8'))
    SIZES = STD_FIBERS

    def cfg_totals(r_max, cap):
        per = []
        for v in VILLAGES:
            r = analyse(trees[v['key']], r_max, cap)
            r.update(key=v['key'], name=v['name'], num=v['num'])
            per.append(r)
        dh = sum(p['dhx_served'] for p in per)
        n2 = sum(p['n2'] for p in per)
        split2 = cap
        return dict(
            per_village=per,
            dhx_served=dh,
            couplers_project=sum(p['couplers_project'] for p in per),
            n_pop=sum(p['n_pop'] for p in per),
            n_pop_nodes=sum(p['n_pop_nodes'] for p in per),
            n2=n2,
            splitters1=sum(p['splitters1'] for p in per),
            fill_pct=round(100.0 * dh / (n2 * split2), 1),
            dh_per_pop=round(dh / sum(p['n_pop'] for p in per), 1),
            extra_km=round(sum(p['extra_km'] for p in per), 2),
            drop_km_total=round(sum(p['drop_km_total'] for p in per), 2),
            drop_cable_km=round(sum(p['drop_cable_km'] for p in per), 1),
            avg_drop_m=round(sum(p['drop_km_total'] for p in per) * 1000 / dh, 1),
            max_drop_m=max(p['max_drop_m'] for p in per),
            trunk_km=round(sum(p['trunk_km'] for p in per), 2),
            fiber_km=round(sum(p['fiber_km'] for p in per), 1),
            cable_km_raw=round(sum(p['cable_km_raw'] for p in per), 2),
            cable_boq_km=round(sum(p['cable_boq_km'] for p in per), 1),
            mufty=sum(p['mufty_branch'] for p in per),
            splices=sum(p['splices'] for p in per),
        )

    # --- ссылки (три рассчитанные схемы), единый базис сравнения ---
    cm = cent['materials_total']
    refs = dict(
        centralized=dict(
            label='Централизованная (1:64 в ОРШ)',
            n_pop=None, n2=None,
            splices=cm['splices'], mufty=cm['mufty'],
            extra_km=0.0,
            drop_cable_km=cm['drop_cable_km'],
            cable_boq_km=round(sum(cm.get(f'cable_{s}', 0.0) for s in SIZES), 1),
            cable_km_raw=cent['totals']['cable_km_raw'],
            fiber_km=round(sum(v['fiber_km'] for v in cent['villages']), 1),
            trunk_km=cent['totals']['feeder_km'],
            avg_drop_m=round(cent['totals']['drop_km'] * 1000 / cent['totals']['dhx_served'], 1),
            max_drop_m=max(v['max_drop_m'] for v in cent['villages']),
        ))
    for f, label, key in [
            ('work/boq_cascade_data.json', 'Каскад 1:8+1:8 (R=100, до 8 ДХ/РОР)', 'cascade88'),
            ('work/boq_cascade16_data.json', 'Каскад 1:4+1:16 (R=150, до 16 ДХ/РОР)', 'cascade16')]:
        d = json.load(open(f'{BASE}/{f}', encoding='utf-8'))
        m = d['materials_total']
        refs[key] = dict(
            label=label,
            n_pop=d['totals']['n_pop'], n2=d['totals']['n2'],
            splices=m['splices'], mufty=m['mufty'],
            splitters1=m['splitters1'],
            extra_km=d['totals']['extra_km'],
            drop_cable_km=m['drop_cable_km'],
            cable_boq_km=round(sum(m.get(f'cable_{s}', 0.0) for s in SIZES), 1),
            cable_km_raw=d['totals']['cable_km_raw'],
            fiber_km=d['totals']['fiber_km'],
            trunk_km=d['totals']['trunk_km'],
            avg_drop_m=round(d['totals']['drop_km_total'] * 1000 / d['totals']['dhx_served'], 1),
            max_drop_m=max(v['max_drop_m'] for v in d['villages']),
        )
    for k, r in refs.items():
        r['L_total'] = round(r['drop_cable_km'] + r['cable_boq_km'], 1)
        r['L_total_raw'] = round(r['drop_cable_km'] + r['cable_km_raw'], 1)

    # --- сетка конфигураций ---
    configs = []
    for r_max in R_GRID:
        for cap in CAP_GRID:
            t = cfg_totals(float(r_max), cap)
            t['L_total'] = round(t['drop_cable_km'] + t['cable_boq_km'], 1)
            t['L_total_raw'] = round(t['drop_cable_km'] + t['cable_km_raw'], 1)
            t['r_max'] = r_max
            t['cap'] = cap
            configs.append(t)

    # --- проверка якорей: сетка должна воспроизвести рассчитанные схемы ---
    anchors_ok = True
    def check(cfg, ref, name):
        nonlocal anchors_ok
        fields = ['n_pop', 'n2', 'drop_cable_km', 'cable_km_raw', 'fiber_km',
                  'trunk_km', 'extra_km', 'drop_km_total', 'cable_boq_km']
        bad = []
        for f in fields:
            ev, gv = ref.get(f), cfg.get(f)
            if ev is None or gv is None:
                continue
            tol = 0.15 if isinstance(ev, float) else 0
            if abs(gv - ev) > tol:
                bad.append(f'{f}: got {gv}, expected {ev}')
        print(f"  якорь {name}: {'OK' if not bad else 'РАСХОЖДЕНИЕ ' + '; '.join(bad)}")
        if bad:
            anchors_ok = False

    a88 = next(c for c in configs if c['r_max'] == 100 and c['cap'] == 8)
    a16 = next(c for c in configs if c['r_max'] == 150 and c['cap'] == 16)
    print('Проверка якорей (воспроизведение рассчитанных схем):')
    check(a88, refs['cascade88'], 'каскад 1:8+1:8 (R100/CAP8)')
    check(a16, refs['cascade16'], 'каскад 1:4+1:16 (R150/CAP16)')
    assert anchors_ok, 'Якоря не сошлись — модель рассинхронизирована!'

    # --- таблица ---
    print(f"\n{'Вариант':<34}{'РОР':>5}{'дроп,км':>9}{'подв,км':>9}{'кабель,км':>10}"
          f"{'СУММА,км':>10}{'вол-км':>8}{'ср.дроп':>8}{'макс':>6}{'спл2':>5}{'заполн%':>8}")
    rows = ([('СХЕМА A: ' + refs['centralized']['label'], refs['centralized']),
             ('СХЕМА B: ' + refs['cascade88']['label'], refs['cascade88']),
             ('СХЕМА C: ' + refs['cascade16']['label'], refs['cascade16'])]
            + [(f"РОР R={c['r_max']:>3} м, до {c['cap']} ДХ", c) for c in configs])
    for label, c in rows:
        print(f"{label:<34}"
              f"{(c['n_pop'] if c['n_pop'] is not None else '—'):>5}"
              f"{c['drop_cable_km']:>9}"
              f"{(c.get('extra_km') if c.get('extra_km') is not None else '—'):>9}"
              f"{c['cable_boq_km']:>10}"
              f"{c['L_total']:>10}"
              f"{c['fiber_km']:>8}"
              f"{c['avg_drop_m']:>8}"
              f"{c['max_drop_m']:>6}"
              f"{(c.get('n2') if c.get('n2') is not None else '—'):>5}"
              f"{(c.get('fill_pct') if c.get('fill_pct') is not None else '—'):>8}")

    print('\nКлючевые конфигурации подробно (для вердикта):')
    for r_max, cap in [(0, 8), (50, 8), (50, 16), (75, 8), (100, 8), (150, 16)]:
        c = next(x for x in configs if x['r_max'] == r_max and x['cap'] == cap)
        print(f"  R={r_max:>3}/CAP={cap:>2}: РОР {c['n_pop']}, спл1 {c['splitters1']}, спл2 {c['n2']}, "
              f"муфты {c['mufty']}, сварки {c['splices']}, заполнение {c['fill_pct']}%, "
              f"вол-км {c['fiber_km']}, L={c['L_total']}")

    best = min(configs, key=lambda c: c['L_total'])
    best_ref = min(refs.values(), key=lambda r: r['L_total'])
    print(f"\nМинимум среди рассчитанных схем: {best_ref['label']} — {best_ref['L_total']} км")
    print(f"Минимум по сетке РОР: R={best['r_max']} м / CAP={best['cap']} — "
          f"{best['L_total']} км (дроп {best['drop_cable_km']} + кабель {best['cable_boq_km']})")
    print(f"  волокно-км: {best['fiber_km']}; РОР: {best['n_pop']}; заполнение: {best['fill_pct']}%")

    json.dump(dict(
        model=dict(min_cluster=MIN_CLUSTER, fiber_reserve=FIBER_RESERVE, min_fibers=MIN_FIBERS,
                   std_fibers=STD_FIBERS, cable_stock=CABLE_STOCK, drop_stock=DROP_STOCK,
                   consum_stock=CONSUM_STOCK, r_grid=R_GRID, cap_grid=CAP_GRID),
        references=refs, configs=configs,
        best=dict(r_max=best['r_max'], cap=best['cap'], L_total=best['L_total']),
        anchors=dict(cascade88_ok=True, cascade16_ok=True),
    ), open(f'{BASE}/work/length_sweep.json', 'w', encoding='utf-8'),
        ensure_ascii=False, indent=1)
    print('\nСохранено: work/length_sweep.json')


if __name__ == '__main__':
    main()
