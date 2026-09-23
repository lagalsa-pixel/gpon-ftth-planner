# -*- coding: utf-8 -*-
"""Шаг 17. Семантическая проверка книги «..._каскад.xlsx» против boq_cascade_data.json."""
from openpyxl import load_workbook

F = '/home/z/my-project/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx'
D = __import__('json').load(open('/home/z/my-project/work/boq_cascade_data.json', encoding='utf-8'))
C = __import__('json').load(open('/home/z/my-project/work/boq_data.json', encoding='utf-8'))
V = D['villages']
mt = D['materials_total']
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
    'Сплиттер PLC 1×8 — 1-я ступень (в ОРШ)': 'splitters1',
    'Сплиттер PLC 1×8 — 2-я ступень (в РОР)': 'splitters2',
    'РОР — бокс оптический распределительный (под сплиттер)': 'por_boxes',
    'Пигтейль SC/UPC для кросса ОРШ': 'pigtails',
    'Порт PON OLT — справочно (активное оборудование)': 'olt_ports',
    'Кабель оптический самонесущий, 8 волокон': 'cable_8',
    'Кабель оптический самонесущий, 24 волокна': 'cable_24',
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

# выборочно по селам (Верхнеберезовка = колонка F)
r = rows['Сплиттер PLC 1×8 — 2-я ступень (в РОР)']
for ci, vi in [(6, 0), (7, 1), (9, 3)]:
    chk(f'Лист1 спл2 {V[vi]["name"]}', ws.cell(row=r, column=ci).value, V[vi]['materials']['splitters2'])
r = rows['Кабель оптический самонесущий, 8 волокон']
chk('Лист1 8F Винное', ws.cell(row=r, column=9).value, V[3]['materials']['cable_8'])

# --- Лист 2 «Параметры сетей» ---
ws2 = wb['Параметры сетей']
tr = 11
chk('Лист2 ДХ', ws2.cell(row=tr, column=6).value, 2334)
chk('Лист2 РОР', ws2.cell(row=tr, column=8).value, 515)
chk('Лист2 спл2', ws2.cell(row=tr, column=9).value, 515)
chk('Лист2 муфты', ws2.cell(row=tr, column=11).value, 115)
chk('Лист2 магистраль', ws2.cell(row=tr, column=12).value, D['totals']['trunk_km'])
chk('Лист2 волокно-км', ws2.cell(row=tr, column=13).value, D['totals']['fiber_km'])
chk('Лист2 дропы проект', ws2.cell(row=tr, column=15).value, 90.89)
chk('Лист2 подводки', ws2.cell(row=tr, column=16).value, D['totals']['extra_km'])
chk('Лист2 дроп-кабель', ws2.cell(row=tr, column=17).value, D['totals']['drop_cable_km'])
chk('Лист2 спл1', ws2.cell(row=tr, column=21).value, 66)
avg = ws2.cell(row=tr, column=18).value
chk('Лист2 ср. дроп', avg, (90.89 + D['totals']['extra_km']) * 1000 / 2334, tol=1.5)
# по селам: ВБ строка 5
chk('Лист2 ВБ заполнение', ws2.cell(row=5, column=10).value, 56.7, tol=0.05)
chk('Лист2 ВБ верхний участок', ws2.cell(row=5, column=14).value, 204)
chk('Лист2 ВБ макс дроп', ws2.cell(row=5, column=19).value, 201.0)

# --- Лист 3 «Сравнение схем» ---
ws3 = wb['Сравнение схем']
comp = {}
for r in range(5, 40):
    name = ws3.cell(row=r, column=3).value
    if name:
        comp[name] = r
chk('Лист3 муфты центр', ws3.cell(row=comp['Муфты оптические'], column=5).value, 1140)
chk('Лист3 муфты каскад', ws3.cell(row=comp['Муфты оптические'], column=6).value, 115)
chk('Лист3 узлы каскад', ws3.cell(row=comp['Пассивные узлы всего (муфты + РОР)'], column=6).value, 630)
chk('Лист3 OLT центр', ws3.cell(row=comp['Порты PON OLT — справочно'], column=5).value, 39)
chk('Лист3 OLT каскад', ws3.cell(row=comp['Порты PON OLT — справочно'], column=6).value, 66)
chk('Лист3 96F центр', ws3.cell(row=comp['Кабель самонесущий, 96 волокон'], column=5).value, 33.8)
chk('Лист3 96F каскад', ws3.cell(row=comp['Кабель самонесущий, 96 волокон'], column=6).value, 1.5)
chk('Лист3 волокно-км центр', ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=5).value,
    sum(v['fiber_km'] for v in C['villages']), tol=0.1)
chk('Лист3 волокно-км каскад', ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=6).value, 1256.1)
chk('Лист3 дроп центр', ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=5).value, 95.8)
chk('Лист3 дроп каскад', ws3.cell(row=comp['Дроп-кабель 2-волоконный (с запасом 5 %)'], column=6).value, 170.7)
chk('Лист3 сварки центр', ws3.cell(row=comp['Сварные соединения'], column=5).value, 5136)
chk('Лист3 сварки каскад', ws3.cell(row=comp['Сварные соединения'], column=6).value, 2585)
chk('Лист3 коннекторы каскад', ws3.cell(row=comp['Коннекторы механические SC/UPC'], column=6).value, 5136)
chk('Лист3 анкеры Δ=0', ws3.cell(row=comp['Анкерные зажимы дроп-кабеля'], column=7).value, 0, tol=1e-9)
d = ws3.cell(row=comp['Суммарная ёмкость магистрали'], column=7).value
chk('Лист3 Δ волокно-км', d, 1256.1 / sum(v['fiber_km'] for v in C['villages']) - 1, tol=0.002)

# --- Лист 4 ---
ws4 = wb['Методика']
cnt = sum(1 for r in range(5, 45) if ws4.cell(row=r, column=2).value is not None)
print(f'Лист4 «Методика»: {cnt} положений')

print(f'\nПроверено: Лист1 — {n1} позиций ИТОГО + спот-чеки, Лист2 — итоговая строка и 3 села, Лист3 — 16 значений, Лист4 — {cnt} положений')
if errs:
    print('ОШИБКИ:')
    for e in errs:
        print(' -', e)
    raise SystemExit(1)
print('ВСЕ ЗНАЧЕНИЯ СХОДЯТСЯ ✓')
