# -*- coding: utf-8 -*-
"""Шаг 21. Семантическая проверка книги «..._каскад.xlsx» (1:4 x 1:16) против boq_cascade16_data.json
и.cross-check со схемами 1:8 x 1:8 и централизованной."""
from openpyxl import load_workbook
import json

F = '/home/z/my-project/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx'
D = json.load(open('/home/z/my-project/work/boq_cascade16_data.json', encoding='utf-8'))
D88 = json.load(open('/home/z/my-project/work/boq_cascade_data.json', encoding='utf-8'))
C = json.load(open('/home/z/my-project/work/boq_data.json', encoding='utf-8'))
V = D['villages']
mt = D['materials_total']
m88 = D88['materials_total']
ct = C['materials_total']

wb = load_workbook(F, data_only=True)
errs = []


def chk(label, got, exp, tol=0.051):
    ok = (got is not None) and abs(float(got) - float(exp)) <= tol
    if not ok:
        errs.append(f'{label}: в книге {got}, ожидалось {exp}')
    return ok


# --- Лист 1 «Сводная»: позиции по наименованию ---
ws = wb['Сводная']
rows = {}
for r in range(5, 40):
    name = ws.cell(row=r, column=3).value
    if name:
        rows[name] = r

CHECK1 = {
    'Сплиттер PLC 1×4 — 1-я ступень (в ОРШ)': 'splitters1',
    'Сплиттер PLC 1×16 — 2-я ступень (в РОР)': 'splitters2',
    'РОР — бокс оптический распределительный (под сплиттер)': 'por_boxes',
    'Пигтейль SC/UPC для кросса ОРШ': 'pigtails',
    'Порт PON OLT — справочно (активное оборудование)': 'olt_ports',
    'Кабель оптический самонесущий, 8 волокон': 'cable_8',
    'Кабель оптический самонесущий, 16 волокон': 'cable_16',
    'Кабель оптический самонесущий, 24 волокна': 'cable_24',
    'Кабель оптический самонесущий, 48 волокон': 'cable_48',
    'Кабель оптический самонесущий, 96 волокон': 'cable_96',
    'Кабель дроп-кабельный самонесущий, 2 волокна (1 раб. + 1 рез.)': 'drop_cable_km',
    'Муфта оптическая (ветвления магистрали)': 'mufty',
    'Бокс абонентский оптический с адаптером SC/UPC': 'abonent_boxes',
    'Коннектор оптический механический SC/UPC': 'fast_conn',
    'Сварное соединение (оценка объёма работ)': 'splices',
    'Гильза КДЗС, 60 мм': 'kdzs',
    'Комплект подвеса магистрального кабеля (кронштейн + спиральный зажим)': 'suspend_kits',
    'Комплект подвеса дроп-кабеля на участках РОР→ДХ': 'drop_ext_suspends',
    'Анкерный зажим дроп-кабеля': 'drop_anchors',
    'Крепёж дроп-кабеля (скобы / хомуты)': 'drop_fix',
}
n1 = 0
for name, key in CHECK1.items():
    r = rows.get(name)
    if r is None:
        errs.append(f'Лист1: нет строки «{name}»')
        continue
    chk(f'Лист1 ИТОГО [{name}]', ws.cell(row=r, column=12).value, mt[key])
    n1 += 1
chk('Лист1 ИТОГО [волокно-км]', ws.cell(row=rows['Справочно: суммарная ёмкость магистрального кабеля'], column=12).value,
    sum(v['fiber_km'] for v in V))
chk('Лист1 ОРШ', ws.cell(row=rows['Шкаф оптический распределительный (ОРШ)'], column=12).value, 6)
chk('Лист1 ИТОГО [кабель 72F] (нет потребности)', ws.cell(row=rows['Кабель оптический самонесущий, 72 волокна'], column=12).value, 0)

# выборочно по селам (F=Верхнеберезовка, G=Солнечное, I=Винное)
r = rows['Сплиттер PLC 1×16 — 2-я ступень (в РОР)']
for ci, vi in [(6, 0), (7, 1), (9, 3)]:
    chk(f'Лист1 спл2 {V[vi]["name"]}', ws.cell(row=r, column=ci).value, V[vi]['materials']['splitters2'])
r = rows['РОР — бокс оптический распределительный (под сплиттер)']
chk('Лист1 РОР Верхнеберезовка', ws.cell(row=r, column=6).value, V[0]['materials']['por_boxes'])
r = rows['Кабель оптический самонесущий, 8 волокон']
chk('Лист1 8F Винное', ws.cell(row=r, column=9).value, V[3]['materials']['cable_8'])

# --- Лист 2 «Параметры сетей» ---
ws2 = wb['Параметры сетей']
tr = 11
chk('Лист2 ДХ', ws2.cell(row=tr, column=6).value, 2334)
chk('Лист2 РОР', ws2.cell(row=tr, column=8).value, D['totals']['n_pop'])
chk('Лист2 спл2 (1:16)', ws2.cell(row=tr, column=9).value, D['totals']['n2'])
chk('Лист2 заполнение %', ws2.cell(row=tr, column=10).value, 45.2, tol=0.15)
chk('Лист2 муфты', ws2.cell(row=tr, column=11).value, D['totals']['mufty'])
chk('Лист2 магистраль', ws2.cell(row=tr, column=12).value, D['totals']['trunk_km'])
chk('Лист2 волокно-км', ws2.cell(row=tr, column=13).value, D['totals']['fiber_km'])
chk('Лист2 дропы проект', ws2.cell(row=tr, column=15).value, 90.89)
chk('Лист2 подводки', ws2.cell(row=tr, column=16).value, D['totals']['extra_km'])
chk('Лист2 дроп-кабель', ws2.cell(row=tr, column=17).value, D['totals']['drop_cable_km'])
chk('Лист2 спл1 (1:4)', ws2.cell(row=tr, column=21).value, D['totals']['splitters1'])
avg = ws2.cell(row=tr, column=18).value
chk('Лист2 ср. дроп', avg, (90.89 + D['totals']['extra_km']) * 1000 / 2334, tol=1.5)
# по селам: ВБ строка 5
chk('Лист2 ВБ заполнение', ws2.cell(row=5, column=10).value, V[0]['fill_pct'], tol=0.05)
chk('Лист2 ВБ верхний участок', ws2.cell(row=5, column=14).value, V[0]['top_fibers'])
chk('Лист2 ВБ макс дроп', ws2.cell(row=5, column=19).value, V[0]['max_drop_m'])
chk('Лист2 ВБ РОР', ws2.cell(row=5, column=8).value, V[0]['n_pop'])
chk('Лист2 Винное заполнение', ws2.cell(row=8, column=10).value, V[3]['fill_pct'], tol=0.05)

# --- Лист 3 «Сравнение схем» (E=центр, F=каскад 1:8x1:8, G=каскад 1:4x1:16, H=Δ) ---
ws3 = wb['Сравнение схем']
comp = {}
for r in range(5, 45):
    name = ws3.cell(row=r, column=3).value
    if name:
        comp[name] = r
chk('Лист3 спл 1×64 центр', ws3.cell(row=comp['Сплиттер PLC 1×64 (в ОРШ)'], column=5).value, ct['splitters'])
chk('Лист3 спл 1×4 (1-я ступ.) новый', ws3.cell(row=comp['Сплиттер PLC 1×4, 1-я ступень (в ОРШ)'], column=7).value, mt['splitters1'])
chk('Лист3 спл 1×16 (2-я ступ.) новый', ws3.cell(row=comp['Сплиттер PLC 1×16, 2-я ступень (в РОР)'], column=7).value, mt['splitters2'])
chk('Лист3 спл 1×8 1-я ступ. прежний', ws3.cell(row=comp['Сплиттер PLC 1×8, 1-я ступень (в ОРШ)'], column=6).value, m88['splitters1'])
chk('Лист3 спл 1×8 2-я ступ. прежний', ws3.cell(row=comp['Сплиттер PLC 1×8, 2-я ступень (в РОР)'], column=6).value, m88['splitters2'])
chk('Лист3 сплиттеры всего центр', ws3.cell(row=comp['Сплиттеры всего (обе ступени)'], column=5).value, ct['splitters'])
chk('Лист3 сплиттеры всего прежний', ws3.cell(row=comp['Сплиттеры всего (обе ступени)'], column=6).value, m88['splitters1'] + m88['splitters2'])
chk('Лист3 сплиттеры всего новый', ws3.cell(row=comp['Сплиттеры всего (обе ступени)'], column=7).value, mt['splitters1'] + mt['splitters2'])
chk('Лист3 РОР прежний', ws3.cell(row=comp['РОР — боксы распределительные'], column=6).value, m88['por_boxes'])
chk('Лист3 РОР новый', ws3.cell(row=comp['РОР — боксы распределительные'], column=7).value, mt['por_boxes'])
chk('Лист3 муфты центр', ws3.cell(row=comp['Муфты оптические'], column=5).value, 1140)
chk('Лист3 муфты прежний', ws3.cell(row=comp['Муфты оптические'], column=6).value, m88['mufty'])
chk('Лист3 муфты новый', ws3.cell(row=comp['Муфты оптические'], column=7).value, mt['mufty'])
chk('Лист3 узлы новый', ws3.cell(row=comp['Пассивные узлы всего (муфты + РОР)'], column=7).value, mt['mufty'] + mt['por_boxes'])
chk('Лист3 OLT центр', ws3.cell(row=comp['Порты PON OLT — справочно'], column=5).value, ct['olt_ports'])
chk('Лист3 OLT прежний', ws3.cell(row=comp['Порты PON OLT — справочно'], column=6).value, m88['olt_ports'])
chk('Лист3 OLT новый', ws3.cell(row=comp['Порты PON OLT — справочно'], column=7).value, mt['olt_ports'])
chk('Лист3 ОРШ-порты новый', ws3.cell(row=comp['Порты ОРШ, суммарно'], column=7).value, 864)
chk('Лист3 волокно-км центр', ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=5).value,
    sum(v['fiber_km'] for v in C['villages']), tol=0.1)
chk('Лист3 волокно-км прежний', ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=6).value, D88['totals']['fiber_km'])
chk('Лист3 волокно-км новый', ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=7).value, D['totals']['fiber_km'])
chk('Лист3 дроп центр', ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=5).value, ct['drop_cable_km'])
chk('Лист3 дроп прежний', ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=6).value, m88['drop_cable_km'])
chk('Лист3 дроп новый', ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=7).value, mt['drop_cable_km'])
chk('Лист3 сварки центр', ws3.cell(row=comp['Сварные соединения'], column=5).value, ct['splices'])
chk('Лист3 сварки прежний', ws3.cell(row=comp['Сварные соединения'], column=6).value, m88['splices'])
chk('Лист3 сварки новый', ws3.cell(row=comp['Сварные соединения'], column=7).value, mt['splices'])
chk('Лист3 коннекторы новый', ws3.cell(row=comp['Коннекторы механические SC/UPC'], column=7).value, mt['fast_conn'])
chk('Лист3 подвесы дроп-подводок новый', ws3.cell(row=comp['Комплекты подвеса дроп-подводок РОР→ДХ'], column=7).value, mt['drop_ext_suspends'])
chk('Лист3 анкеры Δ=0', ws3.cell(row=comp['Анкерные зажимы дроп-кабеля'], column=8).value, 0, tol=1e-9)
d = ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=8).value
chk('Лист3 Δ волокно-км (новый/прежний)', d, D['totals']['fiber_km'] / D88['totals']['fiber_km'] - 1, tol=0.002)
d = ws3.cell(row=comp['Сварные соединения'], column=8).value
chk('Лист3 Δ сварки', d, mt['splices'] / m88['splices'] - 1, tol=0.002)
d = ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=8).value
chk('Лист3 Δ дроп-кабель', d, mt['drop_cable_km'] / m88['drop_cable_km'] - 1, tol=0.002)

# --- Лист 4 ---
ws4 = wb['Методика']
cnt = sum(1 for r in range(5, 45) if ws4.cell(row=r, column=2).value is not None)
print(f'Лист4 «Методика»: {cnt} положений')

print(f'\nПроверено: Лист1 — {n1} позиций ИТОГО + спот-чеки, Лист2 — итоговая строка и 5 сёл, Лист3 — 33 значения (3 схемы), Лист4 — {cnt} положений')
if errs:
    print('ОШИБКИ:')
    for e in errs:
        print(' -', e)
    raise SystemExit(1)
print('ВСЕ ЗНАЧЕНИЯ СХОДЯТСЯ ✓')
