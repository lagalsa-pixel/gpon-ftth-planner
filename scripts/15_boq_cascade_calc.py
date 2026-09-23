# -*- coding: utf-8 -*-
"""
Шаг 15. Расчёт сводной таблицы материалов FTTH по 6 СНП ВКО — КАСКАДНАЯ СХЕМА.

Архитектура: GPON, двухступенчатое каскадное деление 1:8 (ОРШ) x 1:8 (РОР) = 1:64
(та же суммарная ёмкость PON-порта, что и в централизованной схеме 1:64).

Модель (топология сетей НЕ меняется — те же трассы, те же точки подключения):
  - РОР (бокс со сплиттерами 2-й ступени 1:8) размещается в проектной муфте,
    обслуживающей группу ДХ; в кластер РОР включаются ДХ соседних муфт
    в радиусе R_MAX=100 м по трассе сети, не более CAP=8 ДХ на РОР;
  - от РОР к каждому ДХ — индивидуальный 2-волоконный дроп-кабель:
    участок «РОР -> точка подключения ДХ» выполняется дроп-кабелем по трассе
    магистрали (протяжение = сетевое расстояние РОР-муфта ДХ);
  - волокна магистрали на участке = ceil(1.25 x сплиттеры 2-й ступени ниже
    по потоку), минимум 8; разложение по ёмкостям 8..96 (параллельные кабели);
  - сплиттеры 1-й ступени 1:8 — в ОРШ: ceil(N2 / 8) на СНП;
  - муфты: только узлы ветвления магистрали и переходы ёмкости кабеля;
    транзитные волокна проходят муфты/РОР БЕЗ сращивания;
  - сварки: пигтейли кросса ОРШ (N2) + входы сплиттеров РОР (N2)
    + ответвляющиеся волокна в узлах ветвления; запас 10%;
  - запасы: магистральный кабель +10%, дроп-кабель +5% (округление до 0,1 км).
"""
import json, math, heapq
from collections import defaultdict, Counter, deque

BASE = '/home/z/my-project'

VILLAGES = [
    dict(num='01', key='verhneberezovka', name='Верхнеберезовка', raion='Глубоковский р-н', so='Верхнеберезовский с.о.',
         net='network.json', dhx_excel=940,
         orsh_bld='здание пожарной части №26 (198 м²)',
         note='полная сеть села (кадр пользователя не предоставлялся; сеть подтверждена)'),
    dict(num='02', key='solnechnoe', name='Солнечное', raion='Глубоковский р-н', so='Бобровский с.о.',
         net='network_v2.json', dhx_excel=366,
         orsh_bld='общественное здание в центре села (145,7 м²)',
         note='в границах предоставленного кадра; 4 ДХ западной окраины вне дорог OSM'),
    dict(num='03', key='perevalnoe', name='Перевальное', raion='Глубоковский р-н', so='Красноярский с.о.',
         net='network_v2.json', dhx_excel=339,
         orsh_bld='общественное здание в центре (417 м²)',
         note='в границах предоставленного кадра'),
    dict(num='04', key='vinnoe', name='Винное', raion='Глубоковский р-н', so='Тарханский с.о.',
         net='network_v2.json', dhx_excel=490,
         orsh_bld='здание у перекрёстка в центре (96 м²)',
         note='полная сеть села на кадре пользователя; 5 ДХ за верхней кромкой кадра'),
    dict(num='05', key='prigorodnoe', name='Пригородное', raion='г. Риддер', so='—',
         net='network_v2.json', dhx_excel=365,
         orsh_bld='нежилое здание у развилки дорог (84 м²)',
         note='в границах предоставленного кадра; 1 ДХ вне дорог OSM'),
    dict(num='06', key='altaiskiy', name='Алтайский', raion='Глубоковский р-н', so='Алтайский с.о.',
         net='network_v2.json', dhx_excel=716,
         orsh_bld='здание на развилке дорог (156 м²)',
         note='в границах предоставленного кадра; застройка вдоль долины, офиц. число ДХ включает весь с.о.'),
]

# --- параметры модели -------------------------------------------------------
SPLIT1 = 8                   # сплиттер 1-й ступени (в ОРШ)
SPLIT2 = 8                   # сплиттер 2-й ступени (в РОР)
R_MAX = 100.0                # радиус кластера РОР по трассе, м
CAP = 8                      # максимум ДХ на один РОР
MIN_CLUSTER = 5              # мин. размер кластера для "полноценного" РОР
FIBER_RESERVE = 1.25         # резерв волокон магистрали
MIN_FIBERS = 8               # минимальная ёмкость участка
STD_FIBERS = [8, 12, 16, 24, 32, 48, 64, 72, 96]
CABLE_STOCK = 1.10           # запас магистрального кабеля
DROP_STOCK = 1.05            # запас дроп-кабеля
SUSPEND_PER_KM = 30          # комплектов подвеса на км кабеля
DROP_ANCHORS_PER_DH = 2      # анкерных зажимов дропа на ДХ
DROP_FIX_PER_DH = 6          # точек крепления дропа на ДХ
CONSUM_STOCK = 1.10          # запас расходников/сварок
ORSH_PORTS_ROW = [144, 288, 576, 864, 1152]


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
                dh=len(net['drops']), feeder_m=sum(edge_len.values()),
                net=net)


def cluster(t):
    """Жадная кластеризация РОР: узел с максимумом достижимых ДХ."""
    adj, edge_len, homes = t['adj'], t['edge_len'], t['homes']
    cands = [n for n in t['couplers'] if homes.get(n, 0) > 0]
    cand_set = set(cands)
    dists = {}
    for c in cands:
        d = dijkstra_from(adj, edge_len, c, R_MAX)
        dists[c] = {o: dd for o, dd in d.items() if o in cand_set and o != c}

    unassigned = {n: homes[n] for n in cands}
    pops = []  # (узел РОР, [(узел источника, длина м, число ДХ)])

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
            if cnt >= CAP:
                break
            k = min(n, CAP - cnt)
            take.append((o, d, k))
            cnt += k
        pops.append((best, take))
        for o, d, k in take:
            unassigned[o] -= k
    return pops


def analyse(v):
    t = load_tree(v)
    pops = cluster(t)
    parent, bfs, edge_len, adj = t['parent'], t['bfs'], t['edge_len'], t['adj']

    # --- сплиттеры 2-й ступени и привязка ДХ к РОР ---
    s_local = Counter()
    pop_of_source = {}
    for node, take in pops:
        dh = sum(k for _, _, k in take)
        s_local[node] += math.ceil(dh / SPLIT2)
        for o, d, k in take:
            pop_of_source[o] = (node, d)
    n2 = sum(s_local.values())
    pop_nodes = {n for n, _ in pops}

    # --- суммарное/максимальное протяжение дроп-линий ДХ ---
    drop_total_m = 0.0
    max_drop_m = 0.0
    ext_total_m = 0.0
    ext_n = 0
    max_ext_m = 0.0
    for idx, (k, lm) in t['drop_at'].items():
        node, ext = pop_of_source.get(k, (t['root'], 0.0))
        drop_total_m += lm + ext
        max_drop_m = max(max_drop_m, lm + ext)
        if ext > 0:
            ext_total_m += ext
            ext_n += 1
            max_ext_m = max(max_ext_m, ext)

    # --- сплиттеры в поддеревьях ---
    s_sub = dict(s_local)
    for u in reversed(bfs):
        p = parent[u]
        if p is not None:
            s_sub[p] = s_sub.get(p, 0) + s_sub.get(u, 0)

    def trunk_kids(u):
        return [w for w in adj[u] if parent.get(w) == u and s_sub.get(w, 0) > 0]

    # --- волокна/кабель по участкам, муфты, сварки ---
    km_by_size = defaultdict(float)
    fiber_m = 0.0
    trunk_m = 0.0
    top_fibers = 0
    max_parallel = 0
    mufty_branch = 0
    welds = 0

    def F_of(child):
        return max(MIN_FIBERS, math.ceil(FIBER_RESERVE * s_sub.get(child, 0)))

    # ОРШ: все волокна, уходящие от кросса, сращиваются с пигтейлями сплиттеров
    welds += sum(s_sub[w] for w in trunk_kids(t['root']))

    for u in bfs:
        if u not in t['couplers'] or s_sub.get(u, 0) == 0:
            continue
        kids = trunk_kids(u)
        if u in pop_nodes:
            welds += s_local.get(u, 0)          # входы сплиттеров РОР
        if not kids:
            continue
        # продолжение кабеля: ребёнок с наибольшей ёмкостью (при равенстве — с наиб. потоком)
        cont = max(kids, key=lambda c: (F_of(c), s_sub.get(c, 0)))
        for c in kids:
            dF = F_of(u) - F_of(c)
            if c == cont:
                if dF > 0:                      # продолжение со сменой ёмкости кабеля
                    welds += min(s_sub.get(c, 0), dF)
            else:
                welds += s_sub.get(c, 0)        # ответвление в новый кабель
        if len(kids) >= 2 and u not in pop_nodes:
            mufty_branch += 1                   # муфта ветвления магистрали

    for (k1, k2), L in edge_len.items():
        child = k1 if parent.get(k1) == k2 else (k2 if parent.get(k2) == k1 else None)
        if child is None or s_sub.get(child, 0) == 0:
            continue
        trunk_m += L
        F = F_of(child)
        top_fibers = max(top_fibers, F)
        cables = decompose(F)
        max_parallel = max(max_parallel, len(cables))
        for s in cables:
            km_by_size[s] += L / 1000.0
            fiber_m += L / 1000.0 * s

    total_cable_km = sum(km_by_size.values())
    dh = t['dh']
    splitters1 = ceilr(n2 / SPLIT1)
    orsh_ports = next(p for p in ORSH_PORTS_ROW if p >= n2 * 1.1)
    splices = ceilr(welds * CONSUM_STOCK)

    res = dict(v)
    res.update(dict(
        dhx_served=dh,
        couplers_project=len(t['couplers']),
        feeder_km=round(t['feeder_m'] / 1000.0, 2),
        n_pop=len(pops),
        n2=n2,
        splitters1=splitters1,
        fill_pct=round(100.0 * dh / (n2 * SPLIT2), 1),
        dh_per_pop=round(dh / len(pops), 1),
        extra_km=round(ext_total_m / 1000.0, 2),
        ext_dh=ext_n,
        max_ext_m=round(max_ext_m, 1),
        drop_km=round((drop_total_m - ext_total_m) / 1000.0, 2),
        drop_km_total=round(drop_total_m / 1000.0, 2),
        avg_drop_m=round(drop_total_m / max(1, dh), 1),
        max_drop_m=round(max_drop_m, 1),
        trunk_km=round(trunk_m / 1000.0, 2),
        top_fibers=top_fibers,
        max_parallel=max_parallel,
        fiber_km=round(fiber_m, 1),
        total_cable_km=round(total_cable_km, 3),
        cable_km={str(s): round(roundup(km_by_size.get(s, 0.0) * CABLE_STOCK), 1) for s in STD_FIBERS if km_by_size.get(s, 0.0) > 0},
        cable_km_raw=round(total_cable_km * CABLE_STOCK, 2),
        drop_cable_km=round(roundup(drop_total_m / 1000.0 * DROP_STOCK), 1),
        drop_ext_suspends=math.ceil(ext_total_m / 1000.0 * SUSPEND_PER_KM),
        mufty_branch=mufty_branch,
        mufty=mufty_branch,
        welds=welds,
        splices=splices,
        orsh_ports=orsh_ports,
    ))
    # --- материалы ---
    m = dict(
        orsh=1,
        splitters1=splitters1,
        splitters2=n2,
        por_boxes=len(pops),
        pigtails=ceilr(n2 * CONSUM_STOCK),
        olt_ports=splitters1,
        drop_cable_km=res['drop_cable_km'],
        mufty=res['mufty'],
        abonent_boxes=dh,
        fast_conn=ceilr(2 * dh * CONSUM_STOCK),
        splices=splices,
        kdzs=splices,
        suspend_kits=math.ceil(total_cable_km * SUSPEND_PER_KM),
        drop_ext_suspends=res['drop_ext_suspends'],
        drop_anchors=DROP_ANCHORS_PER_DH * dh,
        drop_fix=DROP_FIX_PER_DH * dh,
    )
    m.update({f'cable_{s}': res['cable_km'].get(str(s), 0.0) for s in STD_FIBERS})
    res['materials'] = m
    return res


def main():
    # централизованный расчёт (для сравнения и сверки)
    cent = json.load(open(f'{BASE}/work/boq_data.json', encoding='utf-8'))

    out = []
    print(f"{'Село':<18}{'ДХ':>5}{'РОР':>5}{'спл2':>6}{'заполн%':>8}{'ДХ/РОР':>7}{'магистр':>8}"
          f"{'вол-км':>7}{'верх':>5}{'муфты':>6}{'сварки':>7}{'дроп':>7}{'доп.дроп':>9}{'макс.дроп':>10}")
    for v in VILLAGES:
        r = analyse(v)
        out.append(r)
        print(f"{r['name']:<18}{r['dhx_served']:>5}{r['n_pop']:>5}{r['n2']:>6}{r['fill_pct']:>8}"
              f"{r['dh_per_pop']:>7}{r['trunk_km']:>8}{r['fiber_km']:>7}{r['top_fibers']:>5}"
              f"{r['mufty']:>6}{r['splices']:>7}{r['drop_km_total']:>7}{r['extra_km']:>9}{r['max_drop_m']:>10}")
        # сверка с централизованным расчётом (те же сети!)
        cv = next(c for c in cent['villages'] if c['key'] == v['key'])
        assert r['dhx_served'] == cv['dhx_served'], f"ДХ {v['key']}: {r['dhx_served']} != {cv['dhx_served']}"
        assert r['couplers_project'] == cv['couplers'], f"муфты {v['key']}"
        assert abs(r['drop_km'] - cv['drop_km']) < 0.05, f"дроп {v['key']}: {r['drop_km']} vs {cv['drop_km']}"
        assert abs(r['feeder_km'] - cv['feeder_km']) < 0.05, f"магистраль {v['key']}"
    print('  [сверка с централизованным расчётом: ДХ/муфты/дропы/магистраль совпадают ✓]')

    tot = dict(
        dhx_served=sum(r['dhx_served'] for r in out),
        dhx_excel=sum(r['dhx_excel'] for r in out),
        couplers_project=sum(r['couplers_project'] for r in out),
        n_pop=sum(r['n_pop'] for r in out),
        n2=sum(r['n2'] for r in out),
        splitters1=sum(r['splitters1'] for r in out),
        mufty=sum(r['mufty'] for r in out),
        mufty_branch=sum(r['mufty_branch'] for r in out),
        trunk_km=round(sum(r['trunk_km'] for r in out), 2),
        fiber_km=round(sum(r['fiber_km'] for r in out), 1),
        cable_km_raw=round(sum(r['cable_km_raw'] for r in out), 2),
        drop_km=round(sum(r['drop_km'] for r in out), 2),
        extra_km=round(sum(r['extra_km'] for r in out), 2),
        drop_km_total=round(sum(r['drop_km_total'] for r in out), 2),
        drop_cable_km=round(sum(r['drop_cable_km'] for r in out), 1),
        splices=sum(r['splices'] for r in out),
    )
    mat_tot = {}
    for r in out:
        for k, val in r['materials'].items():
            mat_tot[k] = round(mat_tot.get(k, 0) + val, 1)
    print('\nИТОГО каскад:', json.dumps(tot, ensure_ascii=False))
    print('ИТОГО материалы:', json.dumps(mat_tot, ensure_ascii=False))

    print('\nЁмкости кабеля, км (с запасом):')
    for r in out:
        print(f"  {r['name']:<18} {r['cable_km']}  верхний участок {r['top_fibers']} волок., "
              f"параллельных кабелей до {r['max_parallel']}")

    json.dump(dict(model=dict(
                    split1=SPLIT1, split2=SPLIT2, r_max=R_MAX, cap=CAP, min_cluster=MIN_CLUSTER,
                    fiber_reserve=FIBER_RESERVE, min_fibers=MIN_FIBERS, std_fibers=STD_FIBERS,
                    cable_stock=CABLE_STOCK, drop_stock=DROP_STOCK, suspend_per_km=SUSPEND_PER_KM,
                    drop_anchors_per_dh=DROP_ANCHORS_PER_DH, drop_fix_per_dh=DROP_FIX_PER_DH,
                    consum_stock=CONSUM_STOCK, orsh_ports_row=ORSH_PORTS_ROW),
                  villages=out, totals=tot, materials_total=mat_tot),
              open(f'{BASE}/work/boq_cascade_data.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nСохранено: work/boq_cascade_data.json')


if __name__ == '__main__':
    main()
