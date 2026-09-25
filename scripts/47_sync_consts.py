# -*- coding: utf-8 -*-
"""
Шаг 47 (Task 47/52). Синхронизация захардкоженных констант в скриптах
пересборки (30/34/38) с итогами книги work/boq_decentral_data_v4.json.
Запускать ПОСЛЕ 54_topology_v4.py и ДО 30/34/38.

Task 53: OLD-константы обновлены на состояние книги Task 52 (2765 ДХ,
32 зоны, 38 ОРШ, 59 сплиттеров, 1108 муфт, 6216 сварок, 4752 портов,
1474,4 вол-км, 305 м) — книга пересобрана из network_hh3 после правок
замечаний заказчика по Алтайскому (многоэтажки-квартиры, новые ДХ).
"""
import io
import json

BASE = '/home/z/my-project'
T = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))['totals']
VIL = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))['villages']

NEW = dict(
    dhx=T['dhx_served'], zones=T['n_zones'], orsh=T['orsh'],
    splitters=T['splitters64'], mufty=T['mufty'], splices=T['splices'],
    ports=T['orsh_ports'], fiber=T['fiber_km'],
)
# ср. волоконный маршрут ДХ — взвешенное среднее по сёлам (как в 28/54)
NEW['route'] = round(sum(v['routes']['avg_m'] * v['dhx_served'] for v in VIL)
                     / max(1, T['dhx_served']), 1)

# состояние книги Task 55 ФИНАЛ (до правок Task 57: южный карман +4 ДХ,
# 637127295 многоэтажка 1->8 ДХ, +11 ДХ)
OLD = dict(dhx=3076, zones=36, orsh=42, splitters=65, mufty=1103,
           splices=6914, ports=5184, fiber=1497.1, route=279.0)


def ru_num(x, nd=0):
    return f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 100 in (11, 12, 13, 14):
        return many
    if n % 10 == 1:
        return one
    if n % 10 in (2, 3, 4):
        return few
    return many


def patch(path, pairs, must=True):
    src = io.open(path, encoding='utf-8').read()
    n_applied = 0
    for old, new in pairs:
        if old == new:
            continue
        if old in src:
            src = src.replace(old, new)
            n_applied += 1
        elif must:
            print(f'  ВНИМАНИЕ: не найдено «{old}» в {path.split("/")[-1]}')
    io.open(path, 'w', encoding='utf-8').write(src)
    print(f'{path.split("/")[-1]}: замен {n_applied}')


# ---------------- 30_decentral_xlsx.py ----------------
p30 = f'{BASE}/scripts/30_decentral_xlsx.py'
spl_ru = plural(NEW['splitters'], 'сплиттер', 'сплиттера', 'сплиттеров')
port_ru = plural(NEW['ports'], 'порт', 'порта', 'портов')
pairs30 = [
    (f"== TOTD['dhx_served'] == {OLD['dhx']}",
     f"== TOTD['dhx_served'] == {NEW['dhx']}"),
    (f"for z in v['zones']) == {OLD['dhx']}",
     f"for z in v['zones']) == {NEW['dhx']}"),
    (f"/ {OLD['dhx']} * 1000", f"/ {NEW['dhx']} * 1000"),
    (f"('Обслужено ДХ, шт', {OLD['dhx']}, {OLD['dhx']}, {OLD['dhx']}, {OLD['dhx']}, F_INT, False)",
     f"('Обслужено ДХ, шт', {NEW['dhx']}, {NEW['dhx']}, {NEW['dhx']}, {NEW['dhx']}, F_INT, False)"),
    ("'={L}{fk_r}/" + str(OLD['dhx']) + "'", "'={L}{fk_r}/" + str(NEW['dhx']) + "'"),
    (f"{OLD['splitters']} сплиттеров, {ru_num(OLD['ports'])} портов",
     f"{NEW['splitters']} {spl_ru}, {ru_num(NEW['ports'])} {port_ru}"),
]
patch(p30, pairs30)

# ---------------- 34_svod_d_xlsx.py ----------------
p34 = f'{BASE}/scripts/34_svod_d_xlsx.py'
pairs34 = [
    (f"assert sums['splitters'] == mt['splitters'] == {OLD['splitters']}",
     f"assert sums['splitters'] == mt['splitters'] == {NEW['splitters']}"),
    (f"assert sums['mufty'] == mt['mufty'] == {OLD['mufty']}",
     f"assert sums['mufty'] == mt['mufty'] == {NEW['mufty']}"),
    (f"полная VLM-верификация): {OLD['zones']} зон + 6 ЦУ = {OLD['orsh']} ОРШ",
     f"полная VLM-верификация): {NEW['zones']} зон + 6 ЦУ = {NEW['orsh']} ОРШ"),
    (f"маршрут ДХ {OLD['route']:.0f} м", f"маршрут ДХ {NEW['route']:.0f} м"),
    (f"DBOOK['totals']['n_zones'] == {OLD['zones']}",
     f"DBOOK['totals']['n_zones'] == {NEW['zones']}"),
]
patch(p34, pairs34)

# ---------------- 38_pdf_album.py ----------------
p38 = f'{BASE}/scripts/38_pdf_album.py'
pairs38 = [
    (f"{ru_num(OLD['dhx'])} обслуживаемых домохозяйств · {OLD['zones']} зонных ОРШ + 6 ЦУ · ОРШ в центрах секторов, фидеры в границе НП",
     f"{ru_num(NEW['dhx'])} обслуживаемых домохозяйств · {NEW['zones']} зонных ОРШ + 6 ЦУ · ОРШ в центрах секторов, фидеры в границе НП"),
    (f"('{ru_num(OLD['dhx'])}', 'домохозяйств (ДХ)')",
     f"('{ru_num(NEW['dhx'])}', 'домохозяйств (ДХ)')"),
    (f"('{OLD['zones']} + 6', 'зонных ОРШ + ЦУ (OLT)')",
     f"('{NEW['zones']} + 6', 'зонных ОРШ + ЦУ (OLT)')"),
    (f"('{ru_num(OLD['fiber'], 1)} км', 'суммарного волокна')",
     f"('{ru_num(NEW['fiber'], 1)} км', 'суммарного волокна')"),
    (f"ВКО · 6 СНП · {OLD['dhx']} ДХ", f"ВКО · 6 СНП · {NEW['dhx']} ДХ"),
]
patch(p38, pairs38, must=False)

print('\nНовые итоги книги:', {k: v for k, v in NEW.items()})
