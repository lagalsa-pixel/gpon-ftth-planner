# -*- coding: utf-8 -*-
"""
Шаг 12. Расчёт сводной таблицы материалов FTTH по 6 СНП ВКО.

Источники (финальные сети, соответствующие переданным картам):
  - Верхнеберезовка: work/verhneberezovka/network.json  (полная мозаика; пользователем подтверждена)
  - Солнечное/Перевальное/Пригородное/Алтайский: work/<key>/network_v2.json (границы кадров пользователя, Task 4)
  - Винное: work/vinnoe/network_v2.json (= исходная сеть 550 ДХ, перенесённая на кадр, Task 5)

Модель (централизованная GPON, см. Методику в книге Excel):
  - сплиттеры 1:64 в ОРШ; каждое ДХ — выделенное волокно до ОРШ;
  - волокна на участке магистрали = ceil(1.25 x ДХ ниже по потоку), минимум 8;
  - разложение по ёмкостям самонесущего кабеля 8..96 волокон (параллельные кабели);
  - запас кабеля на монтаж +10% (округление вверх до 0,1 км);
  - дроп-кабель 2-волоконный, запас +5%;
  - расходники — по нормам (см. NORMS).
"""
import sys, os, json, math, glob
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
FIBER_RESERVE = 1.25          # резерв волокон магистрали
MIN_FIBERS = 8                # минимальная ёмкость участка
STD_FIBERS = [8, 12, 16, 24, 32, 48, 64, 72, 96]
CABLE_STOCK = 1.10            # запас магистрального кабеля на монтаж
DROP_STOCK = 1.05             # запас дроп-кабеля
SUSPEND_PER_KM = 30           # комплектов подвеса на км магистрального кабеля
DROP_ANCHORS_PER_DH = 2       # анкерных зажимов дропа на ДХ
DROP_FIX_PER_DH = 6           # точек крепления дропа на ДХ (скобы/хомуты)
SPLICES_PER_DH = 2            # сварок на ДХ (муфта + пигтейль ОРШ)
CONSUM_STOCK = 1.10           # запас расходников
ORSH_PORTS_ROW = [144, 288, 576, 864, 1152]
SPLIT_RATIO = 64


def nkey(p):
    return (round(p[0], 2), round(p[1], 2))


def decompose(F):
    """Число волокон участка -> список параллельных кабелей стандартной ёмкости."""
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
    """ceil без артефактов плавающей точки (770.0000000000001 -> 770)."""
    return math.ceil(round(x, 6))


def analyse(v):
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[v['key']]
    mpp = geo['mpp']
    net = json.load(open(f"{BASE}/work/{v['key']}/{v['net']}"))

    # --- граф магистрали из рёбер (координаты мозаики) ---
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

    # --- корень = узел, ближайший к ОРШ ---
    ax, ay = net['anchor']['x'], net['anchor']['y']
    root = min(adj.keys(), key=lambda k: (k[0] - ax) ** 2 + (k[1] - ay) ** 2)

    # --- привязка муфт и ДХ к узлам графа ---
    ck = {}
    for c in net['couplers']:
        ck[c['node']] = nkey([c['x'], c['y']])
    homes_direct = Counter()
    unmapped = 0
    for d in net['drops']:
        k = ck.get(d['coupler'])
        if k is None or k not in adj:
            k = root
            unmapped += 1
        homes_direct[k] += 1

    # --- BFS от корня: ориентация дерева ---
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
    unreachable = len(adj) - len(parent)

    # --- дома в поддереве (обратный BFS-порядок) ---
    sub = dict(homes_direct)
    for u in reversed(bfs):
        p = parent[u]
        if p is not None:
            sub[p] = sub.get(p, 0) + sub.get(u, 0)

    # --- волокна и кабель по участкам ---
    km_by_size = defaultdict(float)
    fiber_km = 0.0
    total_cable_km = 0.0
    top_fibers = 0
    max_parallel = 0
    feeder_m = 0.0
    for (k1, k2), L in edge_len.items():
        feeder_m += L
        # ребёнок = тот, что дальше от корня
        if parent.get(k1) == k2:
            child = k1
        elif parent.get(k2) == k1:
            child = k2
        else:
            continue  # недостижимое ребро (не должно быть)
        F = max(MIN_FIBERS, math.ceil(FIBER_RESERVE * sub.get(child, 0)))
        top_fibers = max(top_fibers, F)
        cables = decompose(F)
        max_parallel = max(max_parallel, len(cables))
        for s in cables:
            km_by_size[s] += L / 1000.0
            total_cable_km += L / 1000.0
            fiber_km += L / 1000.0 * s

    # --- базовая статистика ---
    drops = net['drops']
    drop_km = sum(d['length_m'] for d in drops) / 1000.0
    st = net.get('stats', {})

    res = dict(v)
    res.update(dict(
        dhx_served=len(drops),
        couplers=len(net['couplers']),
        feeder_km=round(feeder_m / 1000.0, 2),
        drop_km=round(drop_km, 2),
        avg_drop_m=round(sum(d['length_m'] for d in drops) / max(1, len(drops)), 1),
        max_drop_m=round(max((d['length_m'] for d in drops), default=0), 1),
        top_fibers=top_fibers,
        max_parallel=max_parallel,
        total_cable_km=round(total_cable_km, 3),
        fiber_km=round(fiber_km, 1),
        cable_km={str(s): round(roundup(km_by_size.get(s, 0.0) * CABLE_STOCK), 1) for s in STD_FIBERS if km_by_size.get(s, 0.0) > 0},
        cable_km_raw=round(total_cable_km * CABLE_STOCK, 2),
        drop_cable_km=round(roundup(drop_km * DROP_STOCK), 1),
        orsh_ports=next(p for p in ORSH_PORTS_ROW if p >= len(drops) * 1.1),
        splitters64=ceilr(len(drops) / SPLIT_RATIO),
        checks=dict(
            stats_served=st.get('served'), stats_couplers=st.get('couplers'),
            stats_feeder_km=st.get('feeder_km'), stats_drop_km=st.get('drop_km'),
            unreachable_nodes=unreachable, unmapped_drop_couplers=unmapped,
        ),
    ))
    # --- материалы ---
    dh = len(drops)
    m = dict(
        orsh=1,
        splitters=res['splitters64'],
        olt_ports=res['splitters64'],
        pigtails=dh,
        mufty=res['couplers'],
        drop_cable_km=res['drop_cable_km'],
        abonent_boxes=dh,
        fast_conn=ceilr(dh * CONSUM_STOCK),
        splices=ceilr(SPLICES_PER_DH * dh * CONSUM_STOCK),
        kdzs=ceilr(SPLICES_PER_DH * dh * CONSUM_STOCK),
        suspend_kits=math.ceil(total_cable_km * SUSPEND_PER_KM),
        drop_anchors=DROP_ANCHORS_PER_DH * dh,
        drop_fix=DROP_FIX_PER_DH * dh,
    )
    m.update({f'cable_{s}': res['cable_km'].get(str(s), 0.0) for s in STD_FIBERS})
    res['materials'] = m
    return res


def main():
    out = []
    print(f"{'Село':<18}{'ДХ':>5}{'муфт':>6}{'магистр':>9}{'дропы':>8}{'ср.дроп':>8}{'макс':>7}{'вол-км':>8}{'кабель км':>10}{'макс.пар':>9}")
    for v in VILLAGES:
        r = analyse(v)
        out.append(r)
        c = r['checks']
        print(f"{r['name']:<18}{r['dhx_served']:>5}{r['couplers']:>6}{r['feeder_km']:>9}{r['drop_km']:>8}"
              f"{r['avg_drop_m']:>8}{r['max_drop_m']:>7}{r['fiber_km']:>8}{r['cable_km_raw']:>10}{r['max_parallel']:>9}")
        # сверка со stats из JSON
        if c['stats_served'] is not None and c['stats_served'] != r['dhx_served']:
            print(f"   ! served: расчёт {r['dhx_served']} vs stats {c['stats_served']}")
        if c['stats_couplers'] is not None and c['stats_couplers'] != r['couplers']:
            print(f"   ! couplers: расчёт {r['couplers']} vs stats {c['stats_couplers']}")
        if c['stats_feeder_km'] is not None and abs(c['stats_feeder_km'] - r['feeder_km']) > 0.05 * max(1, c['stats_feeder_km']):
            print(f"   ! feeder_km: расчёт {r['feeder_km']} vs stats {c['stats_feeder_km']}")
        if c['stats_drop_km'] is not None and abs(c['stats_drop_km'] - r['drop_km']) > 0.05:
            print(f"   ! drop_km: расчёт {r['drop_km']} vs stats {c['stats_drop_km']}")
        if c['unreachable_nodes']:
            print(f"   ! недостижимых узлов графа: {c['unreachable_nodes']}")
        if c['unmapped_drop_couplers']:
            print(f"   ! дропов с непрозрачной муфтой (привязаны к ОРШ): {c['unmapped_drop_couplers']}")
        print(f"     ёмкости кабеля, км: {r['cable_km']}; верхний участок {r['top_fibers']} волокон")

    # --- итоги ---
    tot = dict(
        dhx_served=sum(r['dhx_served'] for r in out),
        dhx_excel=sum(r['dhx_excel'] for r in out),
        couplers=sum(r['couplers'] for r in out),
        feeder_km=round(sum(r['feeder_km'] for r in out), 2),
        drop_km=round(sum(r['drop_km'] for r in out), 2),
        cable_km_raw=round(sum(r['cable_km_raw'] for r in out), 2),
        drop_cable_km=round(sum(r['drop_cable_km'] for r in out), 1),
        splitters64=sum(r['splitters64'] for r in out),
    )
    mat_tot = {}
    for r in out:
        for k, val in r['materials'].items():
            mat_tot[k] = round(mat_tot.get(k, 0) + val, 1)
    print('\nИТОГО по 6 СНП:', json.dumps(tot, ensure_ascii=False))
    print('ИТОГО материалы:', json.dumps(mat_tot, ensure_ascii=False))

    json.dump(dict(model=dict(
                    fiber_reserve=FIBER_RESERVE, min_fibers=MIN_FIBERS, std_fibers=STD_FIBERS,
                    cable_stock=CABLE_STOCK, drop_stock=DROP_STOCK, suspend_per_km=SUSPEND_PER_KM,
                    drop_anchors_per_dh=DROP_ANCHORS_PER_DH, drop_fix_per_dh=DROP_FIX_PER_DH,
                    splices_per_dh=SPLICES_PER_DH, consum_stock=CONSUM_STOCK,
                    orsh_ports_row=ORSH_PORTS_ROW, split_ratio=SPLIT_RATIO),
                  villages=out, totals=tot, materials_total=mat_tot),
              open(f'{BASE}/work/boq_data.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\nСохранено: work/boq_data.json')


if __name__ == '__main__':
    main()
