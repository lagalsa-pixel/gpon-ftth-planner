# -*- coding: utf-8 -*-
"""
Шаг 56. Расчёт энергетического бюджета (затухания) оптических линий схемы D.

Основание (Task 48, сверка с отраслевыми материалами):
  - foxes-com «Методика построения xPON сетей»: «расчёты затухания выполняются
    для линии от передатчика до самого удалённого абонента; сумма всех потерь —
    энергетический бюджет; учитывать эксплуатационный запас»;
  - prorostelecom «Построение сети GPON»: «самый ответственный момент в
    проектировании PON/GPON сетей — расчёт оптического бюджета потерь»;
  - begemot.ai (курсовая): расчёт бюджета с учётом специфики ИЖС.

Модель линии (худший абонент зоны, восходящий поток 1310 нм — максимум потерь):
  OLT(ЦУ) → ODF → [фидер ЦУ→зонный ОРШ] → кросс ОРШ → сплиттер PLC 1:64
  → [распределение ОРШ→муфта] → муфта → [дроп муфта→ДХ] → розетка/ONT

Нормативы (фиксируются в ALGORITHM_FTTH.md v1.1):
  ALPHA_FIBER_DB_KM = 0.35   G.652D @1310 нм (upstream, худший поток)
  SPLITTER_IL_DB    = 21.0   PLC 1:64, верхняя граница спецификации
  SPLICE_DB         = 0.10   качественная сварка
  CONNECTOR_DB      = 0.50   SC/APC (ODF ЦУ, кросс ОРШ, ONT) = 3 шт
  PENALTY_DB        = 0.20   изгибы/наплывы (штрафные потери)
  BUDGET_CLASS_B    = 28.0   GPON Class B+ (OLT Tx +3…+7 дБм, ONT Rx −27 дБм)
  BUDGET_CLASS_C    = 32.0   GPON Class C+ (оптика с расширенным бюджетом)
  MARGIN_MIN_DB     = 3.0    эксплуатационный запас (ремонтные вставки/сростки)

Маршрут: фидер = root_dist_m зоны (v4: кратчайший путь Дейкстра ЦУ→медиана ОРШ,
в границе НП); распределение = путь дерева ОРШ→муфта худшего ДХ зоны (верхняя
оценка от узла вреза); дроп = max_drop_m села (верхняя граница по зоне).
Сварки: 2 (концы фидера) + n_транзит (муфты ветвления на пути распределения)
+ 2 (оба конца дропа — формула проекта (2×ДХ+2×сплиттеры)×1.1).

Выход: work/optical_budget.json + таблица по зонам; QA-гейт:
  все зоны: A + MARGIN_MIN_DB <= BUDGET_CLASS_B  (цель),
  иначе     A <= BUDGET_CLASS_B (жёстко) — иначе митигация (C+ / 1:32).
"""
import json, math, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)

Tree, nkey = de28.Tree, de28.nkey

ALPHA_FIBER_DB_KM = 0.35
SPLITTER_IL_DB = 21.0
SPLICE_DB = 0.10
CONNECTOR_DB = 0.50
N_CONNECTORS = 3          # ODF ЦУ + кросс ОРШ + ONT
PENALTY_DB = 0.20
BUDGET_CLASS_B = 28.0
BUDGET_CLASS_C = 32.0
MARGIN_MIN_DB = 3.0


def attenuation(L_km, n_transit_splices):
    n_splices = 2 + n_transit_splices + 2          # фидер(2) + транзит + дроп(2)
    return (ALPHA_FIBER_DB_KM * L_km + SPLITTER_IL_DB
            + N_CONNECTORS * CONNECTOR_DB + n_splices * SPLICE_DB + PENALTY_DB)


def main():
    d4 = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json'))
    out_villages = []
    worst_overall = None
    print(f"{'Село':18s}{'зона':>6s}{'ДХ':>5s}{'фид,м':>7s}{'распр,м':>8s}{'дроп,м':>7s}"
          f"{'L,км':>6s}{'транз':>6s}{'A,дБ':>7s}{'маржа':>7s}  статус")
    for v in d4['villages']:
        t = Tree(v)                                # v['net'] = network_hh2.json
        cuts = [nkey(c['node']) for c in v['cut_log']]
        zr, zone_dh, spl, df, ffw = t.flows(cuts)
        zones4 = v['zones']                        # [ЦУ, врезы...] — тот же порядок
        max_drop = v['max_drop_m']

        # худший узел каждой зоны: максимум (dist - dist[zroot]) среди домов зоны
        zone_worst_node = {}
        for node, dh in t.homes.items():
            z = zr[node]
            r = t.dist[node] - t.dist[z]
            if z not in zone_worst_node or r > zone_worst_node[z][0]:
                zone_worst_node[z] = (r, node)

        vz = []
        for zi, z in enumerate([t.root] + cuts):
            zdata = zones4[zi]
            feeder_m = zdata['root_dist_m']
            dist_m, wnode = zone_worst_node.get(z, (0.0, z))
            # муфты ветвления на пути распределения wnode -> z (транзитные сварки)
            n_tr = 0
            u = wnode
            while u != z:
                p = t.parent[u]
                if p != z and p in t.coupler_nodes:
                    n_tr += 1
                u = p
            L_km = (feeder_m + dist_m + max_drop) / 1000.0
            A = attenuation(L_km, n_tr)
            margin = BUDGET_CLASS_B - A
            status = ('OK' if A + MARGIN_MIN_DB <= BUDGET_CLASS_B else
                      'OK-жёстко' if A <= BUDGET_CLASS_B else 'ПРЕВЫШЕНИЕ')
            vz.append(dict(
                kind=zdata['zone'], houses=zdata['houses'], splitters=zdata['splitters'],
                feeder_m=round(feeder_m, 1), distrib_m=round(dist_m, 1),
                drop_max_m=max_drop, L_km=round(L_km, 3), transit_splices=n_tr,
                attenuation_db=round(A, 2), margin_db=round(margin, 2), status=status))
            if worst_overall is None or A > worst_overall[0]:
                worst_overall = (A, v['name'], zi, vz[-1])
            print(f"{v['name']:18s}{zi:>6d}{zdata['houses']:>5d}{feeder_m:>7.0f}"
                  f"{dist_m:>8.0f}{max_drop:>7.0f}{L_km:>6.2f}{n_tr:>6d}"
                  f"{A:>7.2f}{margin:>7.2f}  {status}")
        out_villages.append(dict(key=v['key'], name=v['name'],
                                  max_drop_m=max_drop, n_zones=len(cuts),
                                  worst_attenuation_db=round(max(z['attenuation_db'] for z in vz), 2),
                                  worst_margin_db=round(min(z['margin_db'] for z in vz), 2),
                                  all_ok=all(z['status'] != 'ПРЕВЫШЕНИЕ' for z in vz),
                                  all_ok_with_margin=all(z['status'] == 'OK' for z in vz),
                                  zones=vz))
        print()

    wa, wn, wz, wzdata = worst_overall
    summary = dict(
        model=dict(alpha_db_km=ALPHA_FIBER_DB_KM, splitter_il_db=SPLITTER_IL_DB,
                   splice_db=SPLICE_DB, connector_db=CONNECTOR_DB, n_connectors=N_CONNECTORS,
                   penalty_db=PENALTY_DB, budget_class_b=BUDGET_CLASS_B,
                   budget_class_c=BUDGET_CLASS_C, margin_min_db=MARGIN_MIN_DB),
        worst=dict(village=wn, zone_idx=wz, **{k: val for k, val in wzdata.items()
                                                     if k != 'attenuation_db'},
                   attenuation_db=round(wa, 2)),
        villages=out_villages,
        verdict=('ВСЕ ЗОНЫ В БЮДЖЕТЕ Class B+ С ЭКСПЛ. ЗАПАСОМ 3 дБ'
                 if all(x['all_ok_with_margin'] for x in out_villages) else
                 'В БЮДЖЕТЕ B+ БЕЗ ПОЛНОГО ЗАПАСА — см. статусы зон' if
                 all(x['all_ok'] for x in out_villages) else
                 'ЕСТЬ ЗОНЫ С ПРЕВЫШЕНИЕМ B+ — ТРЕБУЕТСЯ МИТИГАЦИЯ (C+/1:32)'))
    json.dump(summary, open(f'{BASE}/work/optical_budget.json', 'w'), ensure_ascii=False, indent=1)
    print('=' * 78)
    print(f"Худшая линия: {wn}, зона {wz}: A={wa:.2f} дБ, маржа {BUDGET_CLASS_B - wa:.2f} дБ")
    print('ВЕРДИКТ:', summary['verdict'])


if __name__ == '__main__':
    main()
