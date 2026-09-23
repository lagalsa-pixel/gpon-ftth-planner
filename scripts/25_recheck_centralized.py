# -*- coding: utf-8 -*-
"""
Шаг 25. НЕЗАВИСИМАЯ перепроверка централизованной схемы 1:64 (показатель волокно-км).

Запрос пользователя: почему в централизованной схеме очень большое волокно-км?
Схема оптимальна по длине дропов и кабелей — перепроверить волокно-км и оценить,
может ли централизованная схема быть лучшим вариантом.

Реализация НЕЗАВИСИМАЯ от 12_boq_calc.py (другой алгоритм ориентации дерева:
итеративный DFS + накопление потока ДХ в обратном порядке обхода).
Параметры модели те же (Методика книги):
  F участка = max(8, ceil(1.25 x ДХ ниже по потоку));
  разложение F на параллельные кабели 8..96 волокон;
  волокно-км = сумма (длина x установленная ёмкость), БЕЗ запаса +10%
  (тот же принцип во всех трёх схемах — сравнение корректно).

Состав:
  1) сверка пересчёта с книгой boq_data.json по всем показателям;
  2) декомпозиция волокно-км: базовые волокна -> +резерв 25% -> +мин. 8 -> стандарт;
  3) волоконные маршруты ДХ (среднее/медиана/p90 от ОРШ до муфты);
  4) индекс стоимости трёх схем: цена кабеля ~ (F/8)^k, k=0.5 базово,
     чувствительность k=0.4..1.0 (k=1 — стоимость пропорциональна волокно-км);
  5) точка безразличия k* (при каком k централизованная = каскад).

Выход: work/centralized_recheck.json + консольный отчёт.
"""
import json, math
from collections import defaultdict

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
FIBER_RESERVE = 1.25
MIN_FIBERS = 8


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


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(math.ceil(q / 100.0 * len(sorted_vals))) - 1))
    return sorted_vals[i]


def analyse(v):
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[v['key']]
    mpp = geo['mpp']
    net = json.load(open(f"{BASE}/work/{v['key']}/{v['net']}"))

    # --- граф (смежность + длины) ---
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

    # --- итеративный DFS: родитель, порядок, расстояния от корня ---
    parent = {root: None}
    dist = {root: 0.0}
    order = [root]
    stack = [root]
    while stack:
        u = stack.pop()
        for w in adj[u]:
            if w not in parent:
                parent[w] = u
                L = edge_len[(min(u, w), max(u, w))]
                dist[w] = dist[u] + L
                order.append(w)
                stack.append(w)

    # --- привязка ДХ к узлам ---
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    homes = defaultdict(int)
    unmapped = []
    for d in net['drops']:
        k = ck.get(d['coupler'])
        if k is None or k not in adj:
            k = root
            unmapped.append(d.get('hh_id', d.get('hh')))
        homes[k] += 1

    # --- поток ДХ в поддеревьях (обратный порядок DFS) ---
    sub = dict(homes)
    for u in reversed(order):
        p = parent[u]
        if p is not None:
            sub[p] = sub.get(p, 0) + sub.get(u, 0)

    # --- волокна/кабель + ДЕКОМПОЗИЦИЯ волокно-км ---
    km_by_size = defaultdict(float)
    fiber_km = 0.0
    total_cable_km = 0.0
    feeder_m = 0.0
    base_m = res_m = min8_m = std_m = 0.0
    tail_cnt = tail_len = tail_std = 0.0
    zero_cnt = zero_len = 0.0
    top_fibers = 0
    max_parallel = 0
    for (k1, k2), L in edge_len.items():
        feeder_m += L
        if parent.get(k1) == k2:
            child = k1
        elif parent.get(k2) == k1:
            child = k2
        else:
            continue
        n = sub.get(child, 0)
        F_need = math.ceil(FIBER_RESERVE * n)          # только резерв
        F = max(MIN_FIBERS, F_need)                    # + минимальная ёмкость
        cables = decompose(F)
        cap = sum(cables)
        base_m += L * n
        res_m += L * F_need
        min8_m += L * F
        std_m += L * cap
        top_fibers = max(top_fibers, F)
        max_parallel = max(max_parallel, len(cables))
        if F_need < MIN_FIBERS:                        # «хвост»: мин. 8 доминирует
            tail_cnt += 1
            tail_len += L
            tail_std += L * cap
        if n == 0:
            zero_cnt += 1
            zero_len += L
        for s in cables:
            km_by_size[s] += L / 1000.0
            total_cable_km += L / 1000.0
            fiber_km += L / 1000.0 * s

    # --- волоконные маршруты ДХ (ОРШ -> муфта этого ДХ) ---
    routes = [dist[ck[d['coupler']]] for d in net['drops']
              if ck.get(d['coupler']) in dist]
    routes.sort()

    return dict(
        key=v['key'], name=v['name'],
        dhx=len(net['drops']), couplers=len(net['couplers']),
        feeder_km=round(feeder_m / 1000.0, 2),
        fiber_km=round(fiber_km, 1),
        total_cable_km=round(total_cable_km, 3),
        km_by_size={str(s): round(km_by_size.get(s, 0.0), 3) for s in STD_FIBERS
                    if km_by_size.get(s, 0.0) > 0},
        top_fibers=top_fibers, max_parallel=max_parallel,
        decomp=dict(base=round(base_m / 1000, 1), reserve=round(res_m / 1000, 1),
                    min8=round(min8_m / 1000, 1), std=round(std_m / 1000, 1)),
        tails=dict(cnt=int(tail_cnt), km=round(tail_len / 1000, 2),
                   fiber_km=round(tail_std / 1000, 1)),
        zero_edges=dict(cnt=zero_cnt, km=round(zero_len / 1000, 2)),
        routes=dict(avg_m=round(sum(routes) / max(1, len(routes)), 1),
                    avg_km=round(sum(routes) / max(1, len(routes)) / 1000, 2),
                    med_m=round(pct(routes, 50), 1), p90_m=round(pct(routes, 90), 1),
                    max_m=round(routes[-1], 1) if routes else 0),
        unmapped=unmapped,
    )


# ===========================================================================
# Индексная оценка стоимости трёх схем
# ===========================================================================
COST_COEFFS = dict(
    # у.е. = стоимость 1 км 8-волоконного самонесущего кабеля (базис)
    cable_k=0.5,        # цена кабеля ~ (F/8)^k (базово k=0.5, чувствительность ниже)
    mufta=0.125,        # проходная муфта с монтажом
    por_box=0.25,       # РОР: муфта-сплиттерный узел (бокс + плашка + монтаж)
    spl4=0.045, spl8=0.055, spl16=0.09, spl64=0.22,
    splice=0.005,       # сварка + КДЗС
    conn=0.007,         # коннектор/розетка FAST
    orsh_port=0.02,     # порт кросса ОРШ
    olt_port=0.40,      # порт OLT (доля стоимости станции + SFP)
    suspend=0.008,      # комплект подвеса
    pigtail=0.004,
)


def scheme_costs(k):
    """Индексы стоимости трёх схем при показателе цены кабеля k."""
    C = COST_COEFFS
    out = {}

    # --- централизованная 1:64 ---
    d = json.load(open(f'{BASE}/work/boq_data.json'))
    mt = d['materials_total']
    cable = sum(mt[f'cable_{s}'] * (s / 8.0) ** k for s in STD_FIBERS)
    drop = mt['drop_cable_km'] * (2 / 8.0) ** k
    hw = dict(
        mufty=mt['mufty'] * C['mufta'],
        splitters=mt['splitters'] * C['spl64'],
        splices=mt['splices'] * C['splice'],
        conns=mt['fast_conn'] * C['conn'],
        orsh_ports=sum(v['orsh_ports'] for v in d['villages']) * C['orsh_port'],
        olt=mt['olt_ports'] * C['olt_port'],
        suspend=mt['suspend_kits'] * C['suspend'],
        pigtails=mt['pigtails'] * C['pigtail'],
    )
    out['A_centr'] = dict(cable=cable, drop=drop, hw=hw,
                          total=cable + drop + sum(hw.values()),
                          fiber_km=round(sum(v['fiber_km'] for v in d['villages']), 1))

    # --- каскады ---
    for tag, f, s1c, s2c in [('B_cascade88', 'boq_cascade_data.json', 'spl8', 'spl8'),
                             ('C_cascade416', 'boq_cascade16_data.json', 'spl4', 'spl16')]:
        d = json.load(open(f'{BASE}/work/{f}'))
        mt = d['materials_total']
        cable = sum(mt[f'cable_{s}'] * (s / 8.0) ** k for s in STD_FIBERS)
        drop = mt['drop_cable_km'] * (2 / 8.0) ** k
        hw = dict(
            mufty=mt['mufty'] * C['mufta'],
            por_boxes=mt['por_boxes'] * C['por_box'],
            splitters1=mt['splitters1'] * C[s1c],
            splitters2=mt['splitters2'] * C[s2c],
            splices=mt['splices'] * C['splice'],
            conns=mt['fast_conn'] * C['conn'],
            orsh_ports=sum(v['orsh_ports'] for v in d['villages']) * C['orsh_port'],
            olt=mt['olt_ports'] * C['olt_port'],
            suspend=(mt['suspend_kits'] + mt['drop_ext_suspends']) * C['suspend'],
            pigtails=mt['pigtails'] * C['pigtail'],
        )
        out[tag] = dict(cable=cable, drop=drop, hw=hw,
                        total=cable + drop + sum(hw.values()),
                        fiber_km=d['totals']['fiber_km'])
    return out


def main():
    book = json.load(open(f'{BASE}/work/boq_data.json'))
    bv = {v['key']: v for v in book['villages']}

    # ---------- 1-2) перепроверка + декомпозиция ----------
    print('=' * 100)
    print('1. НЕЗАВИСИМЫЙ ПЕРЕСЧЁТ ЦЕНТРАЛИЗОВАННОЙ СХЕМЫ (сверка с книгой)')
    print('=' * 100)
    rows, all_ok = [], True
    for v in VILLAGES:
        r = analyse(v)
        rows.append(r)
        b = bv[v['key']]
        ok = (r['dhx'] == b['dhx_served'] and r['couplers'] == b['couplers']
              and abs(r['feeder_km'] - b['feeder_km']) < 0.02
              and abs(r['fiber_km'] - b['fiber_km']) < 0.15)
        size_ok = all(abs(r['km_by_size'].get(s, 0) * 1.1 - b['cable_km'].get(s, 0)) < 0.15
                      for s in STD_FIBERS if b['cable_km'].get(s, 0) > 0 or r['km_by_size'].get(s, 0) > 0)
        all_ok &= ok and size_ok
        dc = r['decomp']
        print(f"{r['name']:<18} ДХ {r['dhx']:>4}  волокно-км: книга {b['fiber_km']:>7.1f} / "
              f"пересчёт {r['fiber_km']:>7.1f}  {'OK' if ok and size_ok else '!! РАСХОЖДЕНИЕ'}")
        print(f"{'':<18} декомпозиция: база {dc['base']:>7.1f} -> +резерв25% {dc['reserve']:>7.1f} -> "
              f"+мин8 {dc['min8']:>7.1f} -> +станд.ёмкости {dc['std']:>7.1f}")
        print(f"{'':<18} маршрут волокна на ДХ: ср {r['routes']['avg_m']:.0f} м, "
              f"медиана {r['routes']['med_m']:.0f} м, p90 {r['routes']['p90_m']:.0f} м; "
              f"хвосты(min8): {r['tails']['cnt']} уч. / {r['tails']['km']:.1f} км")
        if r['unmapped']:
            print(f"{'':<18} дропы вне графа (привязаны к ОРШ): hh_id {r['unmapped']}")
    print(f"\nИТОГ СВЕРКИ: {'ВСЕ ПОКАЗАТЕЛИ СХОДЯТСЯ' if all_ok else 'ЕСТЬ РАСХОЖДЕНИЯ'}")

    tot = dict(
        fiber_km=round(sum(r['fiber_km'] for r in rows), 1),
        decomp={kk: round(sum(r['decomp'][kk] for r in rows), 1) for kk in ('base', 'reserve', 'min8', 'std')},
        tails=dict(cnt=int(sum(r['tails']['cnt'] for r in rows)),
                   km=round(sum(r['tails']['km'] for r in rows), 1),
                   fiber_km=round(sum(r['tails']['fiber_km'] for r in rows), 1)),
        zero_edges=dict(cnt=int(sum(r['zero_edges']['cnt'] for r in rows)),
                        km=round(sum(r['zero_edges']['km'] for r in rows), 2)),
        avg_route_m=round(sum(r['routes']['avg_m'] * r['dhx'] for r in rows)
                          / sum(r['dhx'] for r in rows), 0),
        top_fibers=max(r['top_fibers'] for r in rows),
    )
    d = tot['decomp']
    print(f"\nИТОГО волокно-км: {tot['fiber_km']} = база {d['base']} "
          f"(+{d['reserve']-d['base']:.0f} резерв 25%, +{d['min8']-d['reserve']:.0f} мин. 8, "
          f"+{d['std']-d['min8']:.0f} стандартные ёмкости)")
    print(f"Ср. волоконный маршрут на ДХ: {tot['avg_route_m']:.0f} м; "
          f"хвосты с мин. 8: {tot['tails']['cnt']} участков, {tot['tails']['km']:.1f} км, "
          f"{tot['tails']['fiber_km']:.0f} волокно-км")

    # ---------- 3) установленная ёмкость с запасом +10% ----------
    inst = {}
    for tag, f in [('A_centr', 'boq_data.json'), ('B_cascade88', 'boq_cascade_data.json'),
                   ('C_cascade416', 'boq_cascade16_data.json')]:
        mt = json.load(open(f'{BASE}/work/{f}'))['materials_total']
        inst[tag] = round(sum(mt[f'cable_{s}'] * s for s in STD_FIBERS), 0)
    print(f"\nУстановленная ёмкость магистральных кабелей (BoQ, с запасом +10%): "
          f"A {inst['A_centr']:.0f} / B {inst['B_cascade88']:.0f} / C {inst['C_cascade416']:.0f} волокно-км")

    # ---------- 4) индекс стоимости ----------
    print('\n' + '=' * 100)
    print('2. ИНДЕКС СТОИМОСТИ ТРЁХ СХЕМ (у.е. = 1 км кабеля 8F; цена кабеля ~ (F/8)^0.5)')
    print('=' * 100)
    base_costs = scheme_costs(COST_COEFFS['cable_k'])
    labels = dict(A_centr='A централизованная 1:64', B_cascade88='B каскад 1:8+1:8 (R100)',
                  C_cascade416='C каскад 1:4+1:16 (R150)')
    for tag, lab in labels.items():
        c = base_costs[tag]
        hw = c['hw']
        print(f"{lab:<30} кабель {c['cable']:>6.1f} + дропы {c['drop']:>6.1f} + "
              f"оборудование {sum(hw.values()):>6.1f} = {c['total']:>6.1f} у.е. "
              f"(волокно-км {c['fiber_km']})")
    print('   оборудование:', {t: {kk: round(vv, 1) for kk, vv in base_costs[t]['hw'].items()} for t in labels})

    # ---------- 5) чувствительность к показателю цены k ----------
    sens = {}
    for k in (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0):
        cs = scheme_costs(k)
        sens[k] = {t: round(cs[t]['total'], 1) for t in labels}
        best = min(sens[k], key=sens[k].get)
        print(f"k={k:.1f}: " + ' / '.join(f"{t.split('_')[0]}={sens[k][t]:.0f}" for t in labels)
              + f"  -> лучшая: {best}")

    # точка безразличия A vs лучшей из B/C (в диапазоне цен от "цена не зависит от
    # ёмкости" (k=0) до линейной по волокнам (k=1))
    def diff(k):
        cs = scheme_costs(k)
        return cs['A_centr']['total'] - min(cs['B_cascade88']['total'], cs['C_cascade416']['total'])
    lo, hi = 0.0, 0.45
    if diff(lo) * diff(hi) < 0:
        for _ in range(40):
            mid = (lo + hi) / 2
            if diff(lo) * diff(mid) <= 0:
                hi = mid
            else:
                lo = mid
        k_star = round((lo + hi) / 2, 3)
    else:
        k_star = None
    print(f"\nТочка безразличия (A = лучшая из каскадов): k* = {k_star}"
          + ("" if k_star is None else f"  (k<{k_star} -> дешевле централизованная, k>{k_star} -> каскад)"))

    json.dump(dict(recheck=dict(all_match=all_ok, villages=rows, totals=tot),
                   installed_with_margin=inst,
                   cost=dict(coeffs=COST_COEFFS, base=base_costs, sensitivity={str(k): v for k, v in sens.items()},
                             breakeven_k=k_star)),
              open(f'{BASE}/work/centralized_recheck.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nСохранено: work/centralized_recheck.json')


if __name__ == '__main__':
    main()
