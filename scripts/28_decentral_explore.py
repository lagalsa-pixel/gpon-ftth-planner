# -*- coding: utf-8 -*-
"""
Шаг 28. Децентрализованная архитектура: несколько ОРШ на село + единый узел OLT.

Запрос пользователя: попробовать использовать несколько ОРШ для построения
децентрализованной структуры и единым узлом OLT.

Концепция (схема D «зонные ОРШ»):
  - топология сетей НЕ меняется (дерево, муфты, дропы — как в централизованной);
  - единый узел OLT (одна станция, как и во всех схемах книги; межселённый
    транспорт до ЦУ сёл — за рамками расчёта); точка входа фидера в селе —
    существующий ЦУ/ОРШ (якорное здание);
  - дерево села режется на зоны: корень зоны — существующая муфта ветвления,
    получающая ОРШ со сплиттерами 1:64 своей зоны. Врезы выбираются ЖАДНО
    по максимальной маржинальной экономии волокно-км (точный диф полной
    раскладки сети), зона >= 48 ДХ (заполнение сплиттера 1:64 >= 75%);
    экономия вреза должна превышать порог окупаемости шкафа S_MIN;
  - распределительная сеть внутри зоны: то же правило модели
    F = max(8, ceil(1.25 x ДХ потока)), разложение 8..96;
  - фидер ЦУ -> ОРШ зоны: ceil(1.25 x сплиттеры зоны) волокон, идёт по дереву
    сети совместно с распределительными волокнами на общих участках;
  - дропы не меняются (95,8 км — минимум по всем схемам).

Состав:
  1) контроль: без врезов модель воспроизводит централизованную книгу;
  2) sweep порога окупаемости S_MIN (волокно-км на один доп. ОРШ);
  3) статистика зон рекомендованной конфигурации (размер, удалённость, сплиттеры);
  4) индекс стоимости 4 схем (коэффициенты шага 25) + чувствительность к k.

Выход: work/decentral_explore.json + консольный отчёт.
"""
import json, math
from collections import defaultdict, Counter, deque

BASE = '/home/z/my-project'

VILLAGES = [
    dict(key='verhneberezovka', name='Верхнеберезовка', net='network.json'),
    dict(key='solnechnoe', name='Солнечное', net='network_v2.json'),
    dict(key='perevalnoe', name='Перевальное', net='network_v2.json'),
    dict(key='vinnoe', name='Винное', net='network_v2.json'),
    dict(key='prigorodnoe', name='Пригородное', net='network_v2.json'),
    dict(key='altaiskiy', name='Алтайский', net='network_v2.json'),
]

STD_FIBERS = [8, 12, 16, 24, 32, 48, 64, 72, 96]

# Task 45 (v4): опциональная подмена файлов сетей через окружение —
# например, FTTH_NET_OVERRIDE=network_hh2.json (сети с уточнёнными ДХ).
# Без переменной поведение идентично исходному (воспроизводимость v1-v3).
import os as _os
if _os.environ.get('FTTH_NET_OVERRIDE'):
    for _v in VILLAGES:
        _v['net'] = _os.environ['FTTH_NET_OVERRIDE']
FIBER_RESERVE = 1.25
MIN_FIBERS = 8
SPLIT_RATIO = 64
ORSH_PORTS_ROW = [144, 288, 576, 864, 1152]
ORSH_PORTS_ROW_ZONE = [48, 96, 144, 288, 576]  # кросс зонных ОРШ (уличные шкафы)
MIN_ZONE = 48          # мин. ДХ в зоне (заполнение сплиттера 1:64 >= 75%)


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


def ceilr(x):
    return math.ceil(round(x, 6))


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(math.ceil(q / 100.0 * len(sorted_vals))) - 1))
    return sorted_vals[i]


class Tree:
    """Дерево магистрали села (ориентация BFS от ЦУ — как в 12_boq_calc.py)."""

    def __init__(self, v):
        geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[v['key']]
        self.mpp = geo['mpp']
        net = json.load(open(f"{BASE}/work/{v['key']}/{v['net']}"))
        self.name = v['name']
        self.key = v['key']
        adj = defaultdict(set)
        self.edge_len = {}
        for e in net['feeder_edges']:
            k1, k2 = nkey(e[0]), nkey(e[1])
            if k1 == k2:
                continue
            L = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * self.mpp
            adj[k1].add(k2)
            adj[k2].add(k1)
            self.edge_len[(min(k1, k2), max(k1, k2))] = L
        ax, ay = net['anchor']['x'], net['anchor']['y']
        self.root = min(adj.keys(), key=lambda k: (k[0] - ax) ** 2 + (k[1] - ay) ** 2)

        # BFS-ориентация
        self.parent = {self.root: None}
        self.children = defaultdict(list)
        order = deque([self.root])
        self.bfs = [self.root]
        while order:
            u = order.popleft()
            for w in adj[u]:
                if w not in self.parent:
                    self.parent[w] = u
                    self.children[u].append(w)
                    self.bfs.append(w)
                    order.append(w)

        # рёбра дерева в форме (родитель, ребёнок, длина)
        self.edges = []
        for (k1, k2), L in self.edge_len.items():
            if self.parent.get(k1) == k2:
                self.edges.append((k2, k1, L))
            elif self.parent.get(k2) == k1:
                self.edges.append((k1, k2, L))

        # привязка домов к узлам
        ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
        self.coupler_nodes = set()
        for c in net['couplers']:
            k = nkey([c['x'], c['y']])
            if k in adj:
                self.coupler_nodes.add(k)
        self.homes = defaultdict(int)
        for d in net['drops']:
            k = ck.get(d['coupler'])
            if k is None or k not in adj:
                k = self.root
            self.homes[k] += 1
        self.dh_total = len(net['drops'])
        self.drop_km = sum(d['length_m'] for d in net['drops']) / 1000.0
        self.n_couplers = len(net['couplers'])

        # расстояния от корня
        self.dist = {self.root: 0.0}
        for u in self.bfs[1:]:
            p = self.parent[u]
            self.dist[u] = self.dist[p] + self.edge_len[(min(u, p), max(u, p))]

    # ------------------------------------------------------------------
    def flows(self, cuts):
        """Потоки при заданном наборе врезов (корней зон)."""
        cutset = set(cuts)
        zr = {self.root: self.root}
        for u in self.bfs:
            if u == self.root:
                continue
            zr[u] = u if u in cutset else zr[self.parent[u]]

        zone_dh = Counter()
        cnt = Counter()
        for node, dh in self.homes.items():
            z = zr[node]
            zone_dh[z] += dh
            cnt[node] += dh
            cnt[z] -= dh
        spl = {z: ceilr(dh / SPLIT_RATIO) for z, dh in zone_dh.items()}
        ffnode = Counter()
        for z in cutset:
            ffnode[z] += ceilr(FIBER_RESERVE * spl[z])

        df, ffw = {}, {}
        for u in reversed(self.bfs):
            acc_d = cnt.get(u, 0)
            acc_f = ffnode.get(u, 0)
            for ch in self.children[u]:
                acc_d += df[ch]
                acc_f += ffw[ch]
            df[u] = acc_d
            ffw[u] = acc_f
        return zr, zone_dh, spl, df, ffw

    # ------------------------------------------------------------------
    def raw_fkm(self, cuts):
        """Σ F x L (волокно-м, до разложения по ёмкостям) + df для кандидатов."""
        zr, zone_dh, spl, df, ffw = self.flows(cuts)
        fkm = 0.0
        for _, child, L in self.edges:
            F = max(MIN_FIBERS, ceilr(FIBER_RESERVE * df[child]) + ffw[child])
            fkm += F * L
        return fkm, df

    # ------------------------------------------------------------------
    def partition_greedy(self, s_min_km):
        """Жадные врезы по максимальной маржинальной экономии волокно-км.

        Кандидаты: муфты (узлы ветвления) с потоком ДХ >= MIN_ZONE.
        Экономия вреза = разность Σ F x L до/после (точный диф раскладки).
        Остановка: лучший врез экономит < s_min_km волокно-км.
        """
        cuts = []
        cur_fkm, df = self.raw_fkm(cuts)
        log = []
        while True:
            best_u, best_sav = None, 0.0
            cands = [u for u in self.coupler_nodes
                     if u != self.root and u not in cuts and df.get(u, 0) >= MIN_ZONE]
            for u in cands:
                fkm_new, df_new = self.raw_fkm(cuts + [u])
                sav = (cur_fkm - fkm_new) / 1000.0
                if sav > best_sav:
                    best_u, best_sav = u, sav
            if best_u is None or best_sav < s_min_km:
                break
            cuts.append(best_u)
            log.append(dict(node=best_u, sav_km=round(best_sav, 1)))
            cur_fkm, df = self.raw_fkm(cuts)
        return cuts, log

    # ------------------------------------------------------------------
    def layout(self, cuts):
        """Полная раскладка для заданного набора врезов."""
        zr, zone_dh, spl, df, ffw = self.flows(cuts)
        cutset = set(cuts)

        km_by_size = defaultdict(float)
        fiber_km = 0.0
        cable_km = 0.0
        top_fibers = 0
        max_parallel = 0
        feeder_route_km = 0.0
        for _, child, L in self.edges:
            d, f = df[child], ffw[child]
            F = max(MIN_FIBERS, ceilr(FIBER_RESERVE * d) + f)
            top_fibers = max(top_fibers, F)
            cables = decompose(F)
            max_parallel = max(max_parallel, len(cables))
            for s in cables:
                km_by_size[s] += L / 1000.0
                cable_km += L / 1000.0
                fiber_km += L / 1000.0 * s
            if f > 0:
                feeder_route_km += L / 1000.0

        # волоконные маршруты ДХ до СВОЕГО ОРШ (зона -> муфта)
        routes = []
        for node, dh in self.homes.items():
            r = max(0.0, self.dist[node] - self.dist[zr[node]])
            routes.extend([r] * dh)
        routes.sort()

        # зоны: детали (корневая зона на ЦУ — главный ОРШ села; врезы — зонные шкафы)
        zinfo = [dict(
            root_dist_m=0.0, houses=zone_dh.get(self.root, 0),
            splitters=spl.get(self.root, 0), feeder_fibers=0,
            orsh_ports=next(p for p in ORSH_PORTS_ROW
                            if p >= zone_dh.get(self.root, 0) * 1.1),
        )]
        for z in cuts:
            zinfo.append(dict(
                root_dist_m=round(self.dist[z], 1), houses=zone_dh[z],
                splitters=spl[z], feeder_fibers=ceilr(FIBER_RESERVE * spl[z]),
                orsh_ports=next(p for p in ORSH_PORTS_ROW_ZONE if p >= zone_dh[z] * 1.1),
            ))
        # ВАЖНО: порядок [ЦУ, врезы...] не сортируем — координаты в шаге 29
        # привязываются по индексу (zip с [root] + cuts)

        mufty = self.n_couplers - sum(1 for z in cuts if z in self.coupler_nodes)
        dh = self.dh_total
        spl_total = sum(spl.values())
        return dict(
            cuts=cuts, zones=zinfo, n_zones=len(cuts),
            orsh=1 + len(cuts),
            fiber_km=round(fiber_km, 1),
            cable_km_raw=round(cable_km, 3),
            km_by_size={str(s): round(km_by_size.get(s, 0.0), 3) for s in STD_FIBERS
                        if km_by_size.get(s, 0.0) > 0},
            top_fibers=top_fibers, max_parallel=max_parallel,
            feeder_route_km=round(feeder_route_km, 2),
            splitters=spl_total, olt_ports=spl_total,
            orsh_ports=sum(z['orsh_ports'] for z in zinfo),
            mufty=mufty,
            splices=ceilr((2 * dh + 2 * spl_total) * 1.1),
            pigtails=dh + 2 * spl_total,
            suspend_kits=math.ceil(cable_km * 30),
            routes=dict(avg_m=round(sum(routes) / max(1, len(routes)), 1),
                        med_m=round(pct(routes, 50), 1),
                        p90_m=round(pct(routes, 90), 1),
                        max_m=round(routes[-1], 1) if routes else 0),
        )


# ===========================================================================
# Индекс стоимости (коэффициенты шага 25 — сопоставимость с листом
# «Проверка волокно-км»); кабели A/B/C/D по одной формуле.
# ===========================================================================
COST_COEFFS = dict(
    cable_k=0.5, mufta=0.125, spl64=0.22, splice=0.005, conn=0.007,
    orsh_port=0.02, olt_port=0.40, suspend=0.008, pigtail=0.004,
    orsh_box=1.5,   # доп. ОРШ-шкаф с монтажом ~ 1,5 км кабеля 8F (отдельная строка)
)


def cost_of(mt, orsh_ports_total, k):
    C = COST_COEFFS
    cable = sum(mt[f'cable_{s}'] * (s / 8.0) ** k for s in STD_FIBERS if mt.get(f'cable_{s}'))
    drop = mt['drop_cable_km'] * (2 / 8.0) ** k
    hw = dict(
        mufty=mt['mufty'] * C['mufta'],
        splitters=mt['splitters'] * C['spl64'],
        splices=mt['splices'] * C['splice'],
        conns=mt['fast_conn'] * C['conn'],
        orsh_ports=orsh_ports_total * C['orsh_port'],
        olt=mt['olt_ports'] * C['olt_port'],
        suspend=mt['suspend_kits'] * C['suspend'],
        pigtails=mt['pigtails'] * C['pigtail'],
    )
    return dict(cable=cable, drop=drop, hw=hw, total=cable + drop + sum(hw.values()))


def roundup01(x):
    return math.ceil(x * 10 - 1e-9) / 10


def materials_from_layout(rs):
    """Сводные материалы схемы D из раскладок сёл."""
    mt = defaultdict(float)
    mt['drop_cable_km'] = 95.8
    mt['fast_conn'] = ceilr(2334 * 1.1)
    for r in rs:
        for s, km in r['km_by_size'].items():
            mt[f'cable_{s}'] += roundup01(km * 1.1)
        mt['mufty'] += r['mufty']
        mt['splitters'] += r['splitters']
        mt['splices'] += r['splices']
        mt['olt_ports'] += r['olt_ports']
        mt['suspend_kits'] += r['suspend_kits']
        mt['pigtails'] += r['pigtails']
    mt['abonent_boxes'] = 2334
    return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in mt.items()}


def scheme_abc_costs(k):
    """A/B/C — как в шаге 25 (для сопоставимости), по книгам."""
    C = COST_COEFFS
    out = {}
    specs = [
        ('A_centr', 'boq_data.json', dict(spl='splitters', cascade=False)),
        ('B_cascade88', 'boq_cascade_data.json', dict(spl=None, cascade=True)),
        ('C_cascade416', 'boq_cascade16_data.json', dict(spl=None, cascade=True)),
    ]
    splc = dict(spl8=0.055, spl4=0.045, spl16=0.09)
    for tag, f, sp in specs:
        d = json.load(open(f'{BASE}/work/{f}'))
        mt = d['materials_total']
        cable = sum(mt[f'cable_{s}'] * (s / 8.0) ** k for s in STD_FIBERS if mt.get(f'cable_{s}'))
        drop = mt['drop_cable_km'] * (2 / 8.0) ** k
        hw = dict(
            mufty=mt['mufty'] * C['mufta'],
            splices=mt['splices'] * C['splice'],
            conns=mt['fast_conn'] * C['conn'],
            orsh_ports=sum(v['orsh_ports'] for v in d['villages']) * C['orsh_port'],
            olt=mt['olt_ports'] * C['olt_port'],
            suspend=(mt['suspend_kits'] + mt.get('drop_ext_suspends', 0)) * C['suspend'],
            pigtails=mt['pigtails'] * C['pigtail'],
        )
        if sp['spl']:
            hw['splitters'] = mt[sp['spl']] * C['spl64']
        else:
            hw['splitters1'] = mt['splitters1'] * splc['spl8' if tag == 'B_cascade88' else 'spl4']
            hw['splitters2'] = mt['splitters2'] * splc['spl8' if tag == 'B_cascade88' else 'spl16']
            hw['por_boxes'] = mt['por_boxes'] * 0.25
        fk = d['totals'].get('fiber_km')
        if fk is None:
            fk = round(sum(v['fiber_km'] for v in d['villages']), 1)
        out[tag] = dict(cable=cable, drop=drop, hw=hw, total=cable + drop + sum(hw.values()),
                        fiber_km=fk)
    return out


def main():
    trees = [Tree(v) for v in VILLAGES]
    book = {v['key']: v for v in json.load(open(f'{BASE}/work/boq_data.json'))['villages']}

    # ---------- 1) контроль ----------
    print('=' * 108)
    print('1. КОНТРОЛЬ: без врезов модель должна воспроизводить централизованную книгу')
    print('=' * 108)
    ok_all = True
    for t in trees:
        r = t.layout([])
        b = book[t.key]
        ok = abs(r['fiber_km'] - b['fiber_km']) < 0.15 and r['splitters'] == b['splitters64']
        ok_all &= ok
        print(f"  {t.name:<18} волокно-км: книга {b['fiber_km']:>7.1f} / расчёт {r['fiber_km']:>7.1f} "
              f" сплиттеры {b['splitters64']}/{r['splitters']}  {'OK' if ok else '!! РАСХОЖДЕНИЕ'}")
    print(f"  ИТОГ: {'СХОДИТСЯ — модель зон корректна' if ok_all else 'ОШИБКА'}")

    # ---------- 2) sweep порога окупаемости ----------
    print()
    print('=' * 108)
    print(f"2. SWEEP ПОРОГА ОКУПАЕМОСТИ S_MIN (волокно-км на один доп. ОРШ; MIN_ZONE={MIN_ZONE} ДХ)")
    print('=' * 108)
    hdr = (f"{'S_MIN':>6} {'ОРШ':>4} {'зон':>4} {'волокно-км':>11} {'кабель км':>10} {'дропы':>7} {'ВСЕГО км':>9} "
           f"{'сплитт.':>8} {'сварки':>7} {'портыОРШ':>9} {'ср.маршр':>9} {'максF':>6} {'пар':>4}")
    print(hdr)
    sweep = []
    for s_min in (2, 5, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80):
        rs = [t.layout(t.partition_greedy(s_min)[0]) for t in trees]
        tot = dict(
            s_min=s_min, orsh=sum(r['orsh'] for r in rs), zones=sum(r['n_zones'] for r in rs),
            fiber_km=round(sum(r['fiber_km'] for r in rs), 1),
            cable_km=round(sum(r['cable_km_raw'] for r in rs) * 1.1, 1),
            splitters=sum(r['splitters'] for r in rs),
            splices=sum(r['splices'] for r in rs),
            orsh_ports=sum(r['orsh_ports'] for r in rs),
            avg_route=round(sum(r['routes']['avg_m'] * t.dh_total for r, t in zip(rs, trees))
                            / sum(t.dh_total for t in trees), 0),
            top_fibers=max(r['top_fibers'] for r in rs),
            max_parallel=max(r['max_parallel'] for r in rs),
            villages=[dict(name=t.name, key=t.key,
                           **{kk: vv for kk, vv in r.items() if kk not in ('cuts', 'zones')})
                      for r, t in zip(rs, trees)],
        )
        sweep.append(tot)
        print(f"{s_min:>6} {tot['orsh']:>4} {tot['zones']:>4} {tot['fiber_km']:>11.1f} "
              f"{tot['cable_km']:>10.1f} {'95,8':>7} {tot['cable_km'] + 95.8:>9.1f} {tot['splitters']:>8} {tot['splices']:>7} "
              f"{tot['orsh_ports']:>9} {tot['avg_route']:>9.0f} {tot['top_fibers']:>6} {tot['max_parallel']:>4}")

    # ---------- 3) индекс стоимости ----------
    print()
    print('=' * 108)
    print('3. ИНДЕКС СТОИМОСТИ A/B/C/D (у.е. = 1 км кабеля 8F; цена ~ (F/8)^0.5; коэффициенты шага 25)')
    print('=' * 108)
    abc = scheme_abc_costs(COST_COEFFS['cable_k'])
    labels = dict(A_centr='A централизованная 1:64', B_cascade88='B каскад 1:8+1:8',
                  C_cascade416='C каскад 1:4+1:16')
    for tag, lab in labels.items():
        c = abc[tag]
        print(f"  {lab:<28} кабель {c['cable']:>6.1f} + дропы {c['drop']:>6.1f} + обор. "
              f"{sum(c['hw'].values()):>6.1f} = {c['total']:>6.1f} у.е. (волокно-км {c['fiber_km']})")

    d_costs = {}
    for sw in sweep:
        mt = materials_from_layout(sw['villages'])
        c = cost_of(mt, sw['orsh_ports'], COST_COEFFS['cable_k'])
        cab = (sw['orsh'] - 6) * COST_COEFFS['orsh_box']
        d_costs[sw['s_min']] = dict(cost=c, orsh=sw['orsh'], extra_orsh=sw['orsh'] - 6,
                                    extra_orsh_cost=round(cab, 1),
                                    total_with_boxes=round(c['total'] + cab, 1),
                                    fiber_km=sw['fiber_km'], mt=mt)
        print(f"  D S_MIN={sw['s_min']:<3} (ОРШ {sw['orsh']:<3})      кабель {c['cable']:>6.1f} + дропы {c['drop']:>6.1f} + обор. "
              f"{sum(c['hw'].values()):>6.1f} = {c['total']:>6.1f} у.е. (волокно-км {sw['fiber_km']}); "
              f"доп. ОРШ {sw['orsh'] - 6} шт = +{cab:.1f} -> итого {c['total'] + cab:.1f}")

    # ---------- 4) чувствительность к k (для нескольких S_MIN) ----------
    print()
    print('4. ЧУВСТВИТЕЛЬНОСТЬ К ПОКАЗАТЕЛЮ ЦЕНЫ КАБЕЛЯ k (D — с шкафами)')
    for s_ref in (10, 15, 25):
        dref = d_costs[s_ref]
        sw_ref = next(s for s in sweep if s['s_min'] == s_ref)
        line = [f"  S_MIN={s_ref}:"]
        for k in (0.0, 0.3, 0.5, 0.7, 1.0):
            abc_k = scheme_abc_costs(k)
            vals = {t: abc_k[t]['total'] for t in labels}
            c = cost_of(dref['mt'], sw_ref['orsh_ports'], k)
            vals['D'] = c['total'] + dref['extra_orsh_cost']
            best = min(vals, key=vals.get)
            line.append(f"k={k}: " + '/'.join(f"{t.split('_')[0]}={vals[t]:.0f}" for t in
                                              ['A_centr', 'B_cascade88', 'C_cascade416', 'D'])
                        + f" -> {best.split('_')[0]}")
        print('\n     '.join(line))

    # ---------- 5) зоны рекомендованной конфигурации ----------
    print()
    print('=' * 108)
    print('5. ЗОНЫ ПРИ S_MIN=10 (размер / удалённость от ЦУ / сплиттеры / фидер)')
    print('=' * 108)
    for t in trees:
        cuts, log = t.partition_greedy(10)
        r = t.layout(cuts)
        if r['n_zones'] == 0:
            print(f"  {t.name:<18} зон нет (село на одном ОРШ, {t.dh_total} ДХ)")
            continue
        zs = ', '.join(f"{z['houses']}ДХ@{z['root_dist_m']:.0f}м(s{z['splitters']},f{z['feeder_fibers']})"
                       for z in r['zones'])
        print(f"  {t.name:<18} {zs}")

    # ---------- сохранение ----------
    json.dump(dict(control_all_match=ok_all, min_zone=MIN_ZONE, sweep=sweep,
                   d_costs={str(kk): {k2: v2 for k2, v2 in vv.items() if k2 != 'mt'}
                            for kk, vv in d_costs.items()},
                   d_materials={str(kk): vv['mt'] for kk, vv in d_costs.items()},
                   coeffs=COST_COEFFS),
              open(f'{BASE}/work/decentral_explore.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nСохранено: work/decentral_explore.json')


if __name__ == '__main__':
    main()
