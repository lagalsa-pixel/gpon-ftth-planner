# -*- coding: utf-8 -*-
"""
Шаг 46b (Task 46). Синхронизация захардкоженных констант в скриптах
пересборки (30/34/38) с фактическими итогами новой книги
work/boq_decentral_data_v4.json (пересобранной после уточнённой детекции
ДХ v3). Запускать ПОСЛЕ 54_topology_v4.py.

Замены (старое -> новое):
  30: asserts 2536 (x3), деления /2536 (x2), строка 'Обслужено ДХ' (x4),
      текст итогов (ОРШ/сплиттеры/порты); DATE.
  34: asserts splitters/mufty, тексты (зоны/ОРШ, шкафы).
  38: титул (ДХ, зон+ЦУ, волокно), подвал (ДХ).
"""
import io
import json
import re

BASE = '/home/z/my-project'
T = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))['totals']

NEW = dict(
    dhx=T['dhx_served'], zones=T['n_zones'], orsh=T['orsh'],
    splitters=T['splitters64'], mufty=T['mufty'], splices=T['splices'],
    ports=T['orsh_ports'], fiber=T['fiber_km'],
)
OLD = dict(dhx=2536, zones=28, orsh=34, splitters=54, mufty=1112,
           splices=5700, ports=4224, fiber=1386.0)

def ru_num(x, nd=0):
    s = f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')
    return s

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
pairs30 = [
    (f"== {OLD['dhx']}", f"== {NEW['dhx']}"),
    (f"/ {OLD['dhx']} * 1000", f"/ {NEW['dhx']} * 1000"),
    (f"/{OLD['dhx']}'", f"/{NEW['dhx']}'"),
    (f"('{OLD['dhx']}', '{OLD['dhx']}', '{OLD['dhx']}', '{OLD['dhx']}', F_INT, False)",
     f"('{NEW['dhx']}', '{NEW['dhx']}', '{NEW['dhx']}', '{NEW['dhx']}', F_INT, False)"),
    (f"{OLD['orsh']} ОРШ вместо 6 ({OLD['zones'] - 6} доп. шкафов, +42 у.е.), {OLD['splitters']} сплиттера, "
     f"{ru_num(OLD['ports'])} порта",
     f"{NEW['orsh']} ОРШ вместо 6 ({NEW['zones'] - 6} доп. шкафов, +42 у.е.), {NEW['splitters']} сплиттера, "
     f"{ru_num(NEW['ports'])} порта"),
    ("DATE = '18.09.2026'", "DATE = '19.09.2026'"),
]
patch(p30, pairs30)

# ---------------- 34_svod_d_xlsx.py ----------------
p34 = f'{BASE}/scripts/34_svod_d_xlsx.py'
pairs34 = [
    (f"assert sums['splitters'] == mt['splitters'] == {OLD['splitters']}",
     f"assert sums['splitters'] == mt['splitters'] == {NEW['splitters']}"),
    (f"assert sums['mufty'] == mt['mufty'] == {OLD['mufty']}",
     f"assert sums['mufty'] == mt['mufty'] == {NEW['mufty']}"),
    (f"Схема D (v4): {OLD['zones']} зон + 6 ЦУ = {OLD['orsh']} ОРШ",
     f"Схема D (v5-детекция): {NEW['zones']} зон + 6 ЦУ = {NEW['orsh']} ОРШ"),
    (f"добавлены зонные уличные шкафы ({OLD['zones']} шт.)",
     f"добавлены зонные уличные шкафы ({NEW['zones']} шт.)"),
]
patch(p34, pairs34)

# ---------------- 38_pdf_album.py ----------------
p38 = f'{BASE}/scripts/38_pdf_album.py'
pairs38 = [
    (f"2 334 обслуживаемых домохозяйства · 26 зонных ОРШ + 6 ЦУ",
     f"{ru_num(NEW['dhx'])} обслуживаемых домохозяйств · {NEW['zones']} зонных ОРШ + 6 ЦУ"),
    (f"('{ru_num(2334)}', 'домохозяйств (ДХ)')",
     f"('{ru_num(NEW['dhx'])}', 'домохозяйств (ДХ)')"),
    (f"('26 + 6', 'зонных ОРШ + ЦУ (OLT)')",
     f"('{NEW['zones']} + 6', 'зонных ОРШ + ЦУ (OLT)')"),
    ("('1 347,3 км', 'суммарного волокна')",
     f"('{ru_num(NEW['fiber'], 1)} км', 'суммарного волокна')"),
    ("ВКО · 6 СНП · 2334 ДХ", f"ВКО · 6 СНП · {NEW['dhx']} ДХ"),
]
patch(p38, pairs38, must=False)   # 38 мог уже быть обновлён частично

print('\nНовые итоги книги:', {k: v for k, v in NEW.items()})
