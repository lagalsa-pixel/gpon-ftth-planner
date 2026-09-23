# -*- coding: utf-8 -*-
"""
Шаг 44b. Оценка сквозных сварок фидерных волокон в старой логике (фидеры
внутри дерева): каждое прохождение муфты = 2 сварки на волокно (вход/выход).
В новой логике (отдельный кабель по кратчайшему пути) фидерные волокна
муфты распределения не вскрывают — сварки только на концах (уже в формуле).

Выход: консольная сводка (для отчёта и worklog).
"""
import json
import importlib.util

BASE = '/home/z/my-project'


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
OLD = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
OLD_BY = {v['key']: v for v in OLD['villages']}
S_MIN = 15.0

tot_thr = 0
print(f"{'Село':<18}{'зон':>4}{'сумма фид. волокон':>19}{'муфт на путях':>15}"
      f"{'сквозные сварки':>17}")
for v in de28.VILLAGES:
    t = de28.Tree(v)
    cuts = [tuple(l['node']) for l in OLD_BY[v['key']]['cut_log']]
    zr, zone_dh, spl, df, _ = t.flows(cuts)
    ff_sum = 0
    mufta_hits = 0
    for z in cuts:
        ff = de28.ceilr(1.25 * spl[z])
        ff_sum += ff
        # путь в дереве: муфты строго между корнем и врезом
        chain = []
        u = z
        while t.parent[u] is not None:
            u = t.parent[u]
            chain.append(u)  # без самого вреза (там концы, не сквозные)
        for node in chain:
            if node in t.coupler_nodes:
                mufta_hits += 1
    thr = 2 * ff_sum * mufta_hits
    tot_thr += thr
    print(f"{v['name']:<18}{len(cuts):>4}{ff_sum:>19}{mufta_hits:>15}{thr:>17}")

print(f"\nИТОГО сквозных сварок фидерных волокон в старой логике "
      f"(не учитывались): ~{tot_thr}")
print(f"Для сравнения: сварки по формуле книги (2*ДХ + 2*сплиттеры)*1.1 = "
      f"{OLD['totals']['splices']}")
