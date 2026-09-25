# -*- coding: utf-8 -*-
"""
Шаг 30. Лист «Децентрализация ОРШ» в книге каскадной сводной таблицы.

Запрос пользователя: попробовать несколько ОРШ для децентрализованной структуры
при едином узле OLT. Схема D: зонные ОРШ со сплиттерами 1:64, фидер от ЦУ
(единый OLT), топология сетей не меняется.

Блоки листа:
  А. Концепция и параметры схемы D;
  Б. Зоны рекомендованной конфигурации (S_MIN = 15) по 6 СНП;
  В. Параметрический sweep порога окупаемости S_MIN + график трейдоффа
     (волокно-км и индекс стоимости от числа ОРШ);
  Г. Сравнение четырёх схем (A/B/C/D) по ключевым показателям;
  Д. Индекс стоимости и чувствительность к показателю цены k;
  Е. Вывод.

Плюс секция 8 «Децентрализованная схема (зонные ОРШ, единый OLT)» в «Методике».
Существующие листы не меняются. Скрипт идемпотентен.
Источники: work/boq_decentral_data.json (шаг 29), work/decentral_explore.json (шаг 28),
work/boq_data.json, boq_cascade_data.json, boq_cascade16_data.json.
"""
import sys, os, json, math, importlib.util

SKILL = '/home/z/my-project/skills/xlsx'
for sub in [SKILL, os.path.join(SKILL, 'templates')]:
    if sub not in sys.path:
        sys.path.insert(0, sub)
import base

base.FONT_NAME = 'Calibri'
base.HEADER_BOLD = True

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.marker import Marker
from openpyxl.drawing.line import LineProperties

BASE_DIR = '/home/z/my-project'
OUT = f'{BASE_DIR}/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx'
DATE = '19.09.2026'

spec = importlib.util.spec_from_file_location('de28', f'{BASE_DIR}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)

DEXP = json.load(open(f'{BASE_DIR}/work/decentral_explore.json', encoding='utf-8'))
DBOOK = json.load(open(f'{BASE_DIR}/work/boq_decentral_data_v4.json', encoding='utf-8'))
ABOOK = json.load(open(f'{BASE_DIR}/work/boq_data.json', encoding='utf-8'))
BBOOK = json.load(open(f'{BASE_DIR}/work/boq_cascade_data.json', encoding='utf-8'))
CBOOK = json.load(open(f'{BASE_DIR}/work/boq_cascade16_data.json', encoding='utf-8'))

# --- контроль внутренней согласованности книги v3 ---
mtD = DBOOK['materials_total']
TOTD = DBOOK['totals']
assert sum(v['dhx_served'] for v in DBOOK['villages']) == TOTD['dhx_served'] == 3076
assert abs(sum(v['fiber_km'] for v in DBOOK['villages']) - TOTD['fiber_km']) < 0.1
assert sum(z['houses'] for v in DBOOK['villages'] for z in v['zones']) == 3076
assert sum(v['n_zones'] for v in DBOOK['villages']) == TOTD['n_zones']
sw15 = next(s for s in DEXP['sweep'] if s['s_min'] == 15)   # исторический sweep v1 (обоснование S_MIN=15)

# --- стоимость A/B/C/D (коэффициенты шага 25; D — из книги v3) ---
K_BASE = 0.5
ABC = de28.scheme_abc_costs(K_BASE)
extra_boxes = (TOTD['orsh'] - 6) * de28.COST_COEFFS['orsh_box']
cD = de28.cost_of(mtD, TOTD['orsh_ports'], K_BASE)
DC = dict(cost=cD, extra_orsh=TOTD['orsh'] - 6,
          extra_orsh_cost=round(extra_boxes, 1),
          total_with_boxes=round(cD['total'] + extra_boxes, 1))
COST = dict(A=ABC['A_centr'], B=ABC['B_cascade88'], C=ABC['C_cascade416'], D=DC['cost'])

# ---------------------------------------------------------------- стили ----
F_INT = '#,##0'
F_KM = '#,##0.0'
F_PCT = '+0.0%;-0.0%;0.0%'
F_U = '#,##0.0'

def sect_font():
    return Font(name=base.FONT_NAME, size=11, bold=base.HEADER_BOLD, color=base.PRIMARY)

def sect_fill():
    return PatternFill('solid', fgColor=base.SECONDARY)

def cap_font():
    return Font(name=base.FONT_NAME, size=9, color=base.NEUTRAL_600)

def rec_fill():
    return PatternFill('solid', fgColor='FFF3CD')

def write_headers(ws, headers, row, col_start=3):
    for i, h in enumerate(headers, start=col_start):
        ws.cell(row=row, column=i, value=h)
    base.style_header_row(ws, row_num=row, col_start=col_start, col_end=col_start + len(headers) - 1)

def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

def section_row(ws, r, title, last_col):
    ws.cell(row=r, column=3, value=title)
    for c in range(2, last_col + 1):
        cell = ws.cell(row=r, column=c)
        cell.fill = sect_fill()
        cell.font = sect_font()
        cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[r].height = 24

def caption(ws, r, text, last_col):
    ws.cell(row=r, column=2, value=text).font = cap_font()
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=last_col)
    ws.row_dimensions[r].height = 14

def body_cell(ws, r, c, idx, num_fmt=None, align='right', left=False):
    cell = ws.cell(row=r, column=c)
    cell.fill = base.fill_data_row(idx)
    cell.font = base.font_body()
    cell.alignment = Alignment(horizontal='left' if left else align, vertical='center',
                               wrap_text=left)
    if num_fmt:
        cell.number_format = num_fmt
    return cell

# =========================================================== КНИГА ==========
wb = load_workbook(OUT)
if 'Децентрализация ОРШ' in wb.sheetnames:
    del wb['Децентрализация ОРШ']
ws = wb.create_sheet('Децентрализация ОРШ', 5)   # после «Проверка волокно-км»

LAST = 14                                          # столбец N
base.setup_sheet(ws, title='Децентрализованная схема D (v3): зонные ОРШ 1:64 в центрах секторов при едином узле OLT — FTTH (GPON), 6 СНП ВКО',
                 last_col=LAST)
ws['B3'] = ('Идея пользователя: несколько ОРШ на село вместо одного. Топология сетей, муфты и дропы не меняются; '
            'сплиттеры 1:64 переносятся в зонные шкафы. v3: шкафы стоят в центрах секторов (медианы зон), фидеры — '
            'кратчайшие пути (Дейкстра) по дорожному графу, ограниченному границей НП. Подготовлено ' + DATE)
ws['B3'].font = cap_font()
ws.row_dimensions[3].height = 14
set_widths(ws, {'A': 3, 'B': 5, 'C': 34, 'D': 11, 'E': 11, 'F': 11, 'G': 11, 'H': 11,
                'I': 11, 'J': 11, 'K': 11, 'L': 10, 'M': 10, 'N': 10})

TOTD = DBOOK['totals']

# ------------------------------------------------- Блок А: концепция --------
r = 5
section_row(ws, r, 'А. Концепция и параметры схемы D (v3)', LAST)
r += 1
CONCEPT = [
    ('Принцип', 'Децентрализация централизованной схемы: в селе не один ОРШ, а несколько. Дерево сети режется '
                'на зоны; в зоне устанавливается зонный ОРШ со сплиттерами 1:64 своей зоны. Каждый абонент '
                'по-прежнему получает выделенное волокно, но уже от ближайшего ОРШ, а не от единственного центра села.'),
    ('Единый узел OLT', 'Одна станция OLT (как и во всех схемах книги); межселённый транспорт до ЦУ сёл — за рамками '
                        'расчёта. В селе фидер заходит в ЦУ (якорное здание, корневая зона) и расходится по зонным ОРШ '
                        'по кратчайшим уличным трассам в границе населённого пункта.'),
    ('Оптимизация v3: ОРШ в центре сектора', 'Зонный шкаф устанавливается не в узле вреза, а в центре сектора — '
                                                'медиане дерева зоны (точный минимизатор распределительных волокон '
                                                'g(v) + фидер × D(v)); средний сдвиг от вреза ~300 м, средний маршрут '
                                                'волокна ДХ -> свой ОРШ сокращается до 322 м.'),
    ('Оптимизация v3: граница НП', 'Граница населённого пункта строится по морфологии застройки (диски 175 м вокруг '
                                    'каждого ДХ + замыкание 250 м, внешний контур) и жёстко ограничивает дорожный граф '
                                    'маршрутизации: фидерные трассы физически не могут покинуть НП (0 км вне границы).'),
    ('Разбиение на зоны', 'Жадный алгоритм: врезы выбираются по максимальной маржинальной экономии волокно-км '
                          '(точный пересчёт раскладки сети на каждый шаг, экономика медиан v3); зона не менее 48 ДХ '
                          '(заполнение сплиттера 1:64 не менее 75%); врез принимается, если экономит не менее S_MIN '
                          'волокно-км (порог окупаемости шкафа).'),
    ('Фидер ЦУ -> зонный ОРШ', 'ceil(1,25 x сплиттеры зоны) волокон (обычно 2-3, кабель 8F), прокладывается по '
                               'КРАТЧАЙШЕМУ пути дорожного графа (Дейкстра) в границе НП; на общих с деревом участках '
                               'едут в одном кабеле с распределительными: ёмкость = max(8; ceil(1,25 x ДХ потока) + '
                               'фидерные), вне дерева — отдельный кабель >= 8 волокон; разложение 8-96 как во всей книге.'),
    ('Кросс зонных ОРШ', 'Уличные шкафы меньшей ёмкости: ряды 48/96/144/288/576 портов (ЦУ — обычный ряд '
                         '144/288/576/864/1152). Порты = 1,1 x ДХ зоны, округление вверх до ряда.'),
    ('Сварки/пигтейли', 'Норма 2 сварки на ДХ (пигтейль сплиттера + муфта) + 2 сварки на каждое фидерное волокно '
                        '(пигтейль OLT + вход сплиттера), запас x1,1 — как в централизованной схеме.'),
    ('Рекомендация', f"S_MIN = 15 волокно-км на доп. ОРШ: {TOTD['n_zones']} зон + 6 ЦУ = {TOTD['orsh']} ОРШ; "
                     f"волокно-км {TOTD['fiber_km']:.0f} (-69% к A); суммарная длина {TOTD['total_length_km']} км "
                     f"— минимум среди всех схем книги."),
]
for i, (name, desc) in enumerate(CONCEPT, 1):
    ws.cell(row=r, column=3, value=name)
    ws.cell(row=r, column=4, value=desc)
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=LAST)
    for c in (3, 4):
        cell = ws.cell(row=r, column=c)
        cell.fill = base.fill_data_row(i - 1)
        cell.font = base.font_body()
        cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    lines = max(2, math.ceil(len(desc) / 120))
    ws.row_dimensions[r].height = lines * 13 + 8
    r += 1
r += 1

# ------------------------------------------------- Блок Б: зоны -------------
section_row(ws, r, 'Б. Зоны рекомендованной конфигурации (S_MIN = 15) — размещение ОРШ', LAST)
r += 1
write_headers(ws, ['СНП', 'Узел', 'Тип ОРШ', 'ДХ в зоне', 'Удалённость от ЦУ, м',
                   'Сплиттеры 1:64, шт', 'Фидер, волокон', 'Порты кросса'], r)
r += 1
B_FIRST = r
idx = 0
for v in DBOOK['villages']:
    for j, z in enumerate(v['zones']):
        ws.cell(row=r, column=3, value=v['name'] if j == 0 else '')
        ws.cell(row=r, column=4, value=('ЦУ' if z['zone'].startswith('ЦУ') else f"З-{j}"))
        ws.cell(row=r, column=5, value=('ЦУ (корневая)' if z['zone'].startswith('ЦУ') else 'зонный шкаф'))
        ws.cell(row=r, column=6, value=z['houses'])
        ws.cell(row=r, column=7, value=round(z['root_dist_m']))
        ws.cell(row=r, column=8, value=z['splitters'])
        ws.cell(row=r, column=9, value=z['feeder_fibers'])
        ws.cell(row=r, column=10, value=z['orsh_ports'])
        for c in range(3, 11):
            body_cell(ws, r, c, idx, left=(c in (3, 4, 5)), align='center' if c in (4,) else 'right')
        for c in (6, 7, 8, 9, 10):
            ws.cell(row=r, column=c).number_format = F_INT
        ws.row_dimensions[r].height = 18
        idx += 1
        r += 1
B_LAST = r - 1
ws.cell(row=r, column=3, value='ИТОГО')
ws.cell(row=r, column=4, value=f"{TOTD['orsh']} ОРШ")
ws.cell(row=r, column=6, value=f'=SUM(F{B_FIRST}:F{B_LAST})')
ws.cell(row=r, column=8, value=f'=SUM(H{B_FIRST}:H{B_LAST})')
ws.cell(row=r, column=9, value=f'=SUM(I{B_FIRST}:I{B_LAST})')
ws.cell(row=r, column=10, value=f'=SUM(J{B_FIRST}:J{B_LAST})')
for c in range(3, 11):
    cell = ws.cell(row=r, column=c)
    cell.font = Font(name=base.FONT_NAME, size=11, bold=True, color=base.PRIMARY)
    cell.fill = PatternFill('solid', fgColor=base.SECONDARY)
    cell.alignment = Alignment(horizontal='right' if c > 4 else 'left', vertical='center')
    if c >= 6:
        cell.number_format = F_INT
ws.row_dimensions[r].height = 20
caption(ws, r + 1, 'Удалённость от ЦУ — по кратчайшей трассе дорожного графа в границе НП (Дейкстра). Зонный шкаф стоит '
                   'в центре сектора — медиане дерева зоны (средний сдвиг от узла вреза ~300 м); врез — точка отделения '
                   'зоны от дерева сети. Дропы абонентов не меняются.', LAST)
r += 3

# ------------------------------------------------- Блок В: sweep ------------
section_row(ws, r, 'В. Параметрический sweep порога окупаемости S_MIN', LAST)
r += 1
write_headers(ws, ['S_MIN, вол-км', 'ОРШ, шт', 'Волокно-км', 'Δ к A (4375,1)', 'Кабель, км',
                   'Дропы, км', 'ВСЕГО, км', 'Сплиттеры', 'Сварки', 'Порты ОРШ',
                   'Ср. маршрут волокна, м', 'Макс. ёмкость, F'], r)
r += 1
V_FIRST = r
FA = 4375.1
for i, s in enumerate(DEXP['sweep']):
    rec = s['s_min'] == 15
    ws.cell(row=r, column=3, value=s['s_min'])
    ws.cell(row=r, column=4, value=s['orsh'])
    ws.cell(row=r, column=5, value=s['fiber_km'])
    ws.cell(row=r, column=6, value=f'=E{r}/{FA}-1')
    ws.cell(row=r, column=7, value=s['cable_km'])
    ws.cell(row=r, column=8, value=95.8)
    ws.cell(row=r, column=9, value=f'=G{r}+H{r}')
    ws.cell(row=r, column=10, value=s['splitters'])
    ws.cell(row=r, column=11, value=s['splices'])
    ws.cell(row=r, column=12, value=s['orsh_ports'])
    ws.cell(row=r, column=13, value=s['avg_route'])
    ws.cell(row=r, column=14, value=s['top_fibers'])
    for c in range(3, 15):
        cell = body_cell(ws, r, c, i, align='right')
        if rec:
            cell.fill = rec_fill()
    ws.cell(row=r, column=6).number_format = F_PCT
    for c in (5, 7, 8, 9):
        ws.cell(row=r, column=c).number_format = F_KM
    for c in (3, 4, 10, 11, 12, 13, 14):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.row_dimensions[r].height = 18
    r += 1
V_LAST = r - 1
caption(ws, r, 'S_MIN — порог окупаемости: врез зонного ОРШ принимается при экономии не менее S_MIN волокно-км '
               '(шкаф с монтажом ~ 1,5 у.е. ~ 12-15 вол-км на тонком кабеле). Жёлтая строка — рекомендованная '
               'конфигурация (S_MIN = 15). Sweep рассчитан на стадии v1 (ОРШ во врезах, фидеры по дереву) и обосновывает '
               'выбор S_MIN; выпущенная книга v3 (ОРШ в центрах секторов + кратчайшие фидеры в границе НП): '
               '1 386,0 волокно-км при 34 ОРШ.', LAST)
r += 2

# график: волокно-км и стоимость от числа ОРШ
CH_HDR = r
ws.cell(row=r, column=2, value='ОРШ, шт')
ws.cell(row=r, column=3, value='Волокно-км')
ws.cell(row=r, column=4, value='Индекс стоимости (с шкафами), у.е.')
base.style_header_row(ws, row_num=r, col_start=2, col_end=4)
r += 1
CH_FIRST = r
for i, s in enumerate(sorted(DEXP['sweep'], key=lambda x: x['orsh'])):
    ws.cell(row=r, column=2, value=s['orsh'])
    ws.cell(row=r, column=3, value=s['fiber_km'])
    ws.cell(row=r, column=4, value=DEXP['d_costs'][str(s['s_min'])]['total_with_boxes'])
    fill = base.fill_data_row(i)
    for c in range(2, 5):
        cell = ws.cell(row=r, column=c)
        cell.fill = fill
        cell.font = base.font_body()
        cell.alignment = Alignment(horizontal='right', vertical='center')
        cell.number_format = F_INT if c == 2 else F_U
    r += 1
CH_LAST = r - 1

c1 = LineChart()
c1.style = 10
c1.width = 21
c1.height = 11
data1 = Reference(ws, min_col=3, max_col=3, min_row=CH_HDR, max_row=CH_LAST)
cats = Reference(ws, min_col=2, min_row=CH_FIRST, max_row=CH_LAST)
c1.add_data(data1, titles_from_data=True)
c1.set_categories(cats)
base.setup_chart_titles(c1, title='Трейдофф децентрализации: волокно-км и стоимость от числа ОРШ',
                        y_title='Волокно-км', x_title='Число ОРШ (6 ЦУ + зонные шкафы)')
for s in c1.series:
    s.smooth = False
    s.marker = Marker(symbol='circle', size=6)

c2 = LineChart()
data2 = Reference(ws, min_col=4, max_col=4, min_row=CH_HDR, max_row=CH_LAST)
c2.add_data(data2, titles_from_data=True)
for s in c2.series:
    s.smooth = False
    s.marker = Marker(symbol='diamond', size=6)
c2.y_axis.axId = 200
c2.y_axis.title = base.make_chart_title('Стоимость, у.е.', 10, bold=False, axis=True)
c1.y_axis.crosses = 'max'
c1 += c2

LINE_COLORS = [base.ACCENT_WARNING, base.ACCENT_POSITIVE]
for s, col in zip(c1.series, LINE_COLORS[:1]):
    s.graphicalProperties.line = LineProperties(solidFill=col, w=22000)
for s in c2.series:
    s.graphicalProperties.line = LineProperties(solidFill=LINE_COLORS[1], w=22000)
ws.add_chart(c1, f'F{CH_HDR}')
r = CH_LAST + 2

# ------------------------------------------------- Блок Г: сравнение --------
section_row(ws, r, 'Г. Сравнение четырёх схем — A / B / C / D', LAST)
r += 1
write_headers(ws, ['Показатель', 'A: централизо-ванная 1:64', 'B: каскад 1:8+1:8', 'C: каскад 1:4+1:16',
                   'D: зонные ОРШ 1:64', 'Лучшая'], r)
r += 1
G_FIRST = r

mtA, mtB, mtC, mtD = (ABOOK['materials_total'], BBOOK['materials_total'],
                      CBOOK['materials_total'], DBOOK['materials_total'])
tA, tB, tC, tD = (ABOOK['totals'], BBOOK['totals'], CBOOK['totals'], DBOOK['totals'])
avg_route_d = round(sum(v['routes']['avg_m'] * v['dhx_served'] for v in DBOOK['villages'])
                    / TOTD['dhx_served'])
cab_tot = lambda mt: round(sum(mt[f'cable_{s}'] for s in de28.STD_FIBERS), 1)
susB = mtB['suspend_kits'] + mtB.get('drop_ext_suspends', 0)
susC = mtC['suspend_kits'] + mtC.get('drop_ext_suspends', 0)
avg_drop = lambda book: round(sum(v['drop_km_total'] if 'drop_km_total' in v else v['drop_km']
                                  for v in book['villages']) / 3076 * 1000, 1)
max_drop = lambda book: max(v['max_drop_m'] for v in book['villages'])

ROWS = [
    # (название, A, B, C, D, формат, лучшая?)
    ('Обслужено ДХ, шт', 3076, 3076, 3076, 3076, F_INT, False),
    ('Волокно-км', tA['fiber_km'] if 'fiber_km' in tA else 4375.1, tB['fiber_km'], tC['fiber_km'],
     tD['fiber_km'], F_KM, True),
    ('Волокно-км на ДХ, км', None, None, None, None, '0.00', True),
    ('Магистральный кабель, км', cab_tot(mtA), cab_tot(mtB), cab_tot(mtC), cab_tot(mtD), F_KM, True),
    ('в т.ч. 8-волоконный, км', mtA['cable_8'], mtB['cable_8'], mtC['cable_8'], mtD['cable_8'], F_KM, None),
    ('в т.ч. 96-волоконный, км', mtA['cable_96'], mtB['cable_96'], mtC['cable_96'], mtD['cable_96'], F_KM, None),
    ('Дроп-кабель, км', mtA['drop_cable_km'], mtB['drop_cable_km'], mtC['drop_cable_km'],
     mtD['drop_cable_km'], F_KM, True),
    ('ВСЕГО кабель + дропы, км', None, None, None, None, F_KM, True),
    ('Средний дроп, м', avg_drop(ABOOK), avg_drop(BBOOK), avg_drop(CBOOK), avg_drop(DBOOK), F_INT, True),
    ('Максимальный дроп, м', max_drop(ABOOK), max_drop(BBOOK), max_drop(CBOOK), max_drop(DBOOK), F_INT, True),
    ('Ср. маршрут волокна ДХ, м', 1361, None, None, avg_route_d, F_INT, True),
    ('ОРШ, шт', 6, 6, 6, tD['orsh'], F_INT, True),
    ('РОР, шт', 0, tB['n_pop'], tC['n_pop'], 0, F_INT, None),
    ('Сплиттеры 1:64, шт', mtA['splitters'], 0, 0, mtD['splitters'], F_INT, None),
    ('Сплиттеры 1:8, шт', 0, mtB['splitters1'] + mtB['splitters2'], 0, 0, F_INT, None),
    ('Сплиттеры 1:4, шт', 0, 0, mtC['splitters1'], 0, F_INT, None),
    ('Сплиттеры 1:16, шт', 0, 0, mtC['splitters2'], 0, F_INT, None),
    ('Муфты, шт', mtA['mufty'], mtB['mufty'], mtC['mufty'], mtD['mufty'], F_INT, True),
    ('Сварки, шт', mtA['splices'], mtB['splices'], mtC['splices'], mtD['splices'], F_INT, True),
    ('Коннекторы FAST, шт', mtA['fast_conn'], mtB['fast_conn'], mtC['fast_conn'], mtD['fast_conn'], F_INT, True),
    ('Порты кросса ОРШ, шт', sum(v['orsh_ports'] for v in ABOOK['villages']),
     sum(v['orsh_ports'] for v in BBOOK['villages']), sum(v['orsh_ports'] for v in CBOOK['villages']),
     tD['orsh_ports'], F_INT, True),
    ('Порты OLT, шт', mtA['olt_ports'], mtB['olt_ports'], mtC['olt_ports'], mtD['olt_ports'], F_INT, True),
    ('Комплекты подвеса, шт', mtA['suspend_kits'], susB, susC, mtD['suspend_kits'], F_INT, True),
    ('Доп. шкафы ОРШ (сверх 6), шт', 0, 0, 0, tD['orsh'] - 6, F_INT, True),
]
G_ROW_IDX = {}
for i, (name, a, b, c, d, fmt, best) in enumerate(ROWS):
    ws.cell(row=r, column=3, value=name)
    G_ROW_IDX[name] = r
    if name == 'Волокно-км на ДХ, км':
        fk_r = G_ROW_IDX['Волокно-км']
        for col, L in zip(range(4, 8), 'DEFG'):
            ws.cell(row=r, column=col, value=f'={L}{fk_r}/3076')
    elif name == 'ВСЕГО кабель + дропы, км':
        cab_r = G_ROW_IDX['Магистральный кабель, км']
        dr_r = G_ROW_IDX['Дроп-кабель, км']
        for col, L in zip(range(4, 8), 'DEFG'):
            ws.cell(row=r, column=col, value=f'={L}{cab_r}+{L}{dr_r}')
    else:
        ws.cell(row=r, column=4, value=a)
        ws.cell(row=r, column=5, value=b)
        ws.cell(row=r, column=6, value=c)
        ws.cell(row=r, column=7, value=d)
    if best:
        ws.cell(row=r, column=8, value=f'=CHOOSE(MATCH(MIN(D{r}:G{r}),D{r}:G{r},0),"A","B","C","D")')
    for cc in range(3, 9):
        body_cell(ws, r, cc, i, left=(cc == 3), align='center' if cc == 8 else 'right')
        if cc > 3 and cc < 8:
            ws.cell(row=r, column=cc).number_format = fmt
    ws.row_dimensions[r].height = 18
    r += 1
G_LAST = r - 1
caption(ws, r, '«Лучшая» — минимум по строке (для числа узлов и портов меньший объём работ также считается лучшим; '
               'равные значения дают первую). Ср. маршрут волокна ДХ: A/D — от ОРШ до муфты абонента; в каскадах '
               'маршрут делится на-shared участки до РОР, показатель не определён.', LAST)
r += 2

# ------------------------------------------------- Блок Д: стоимость --------
section_row(ws, r, 'Д. Ориентировочный индекс стоимости и чувствительность к цене ёмкости', LAST)
r += 1
write_headers(ws, ['Составляющая, у.е. (1 км кабеля 8F)', 'A: централизо-ванная', 'B: каскад 1:8+1:8',
                   'C: каскад 1:4+1:16', 'D: зонные ОРШ'], r)
r += 1
D1_FIRST = r
items = [('Кабельная продукция (магистраль)', 'cable'), ('Дроп-кабели', 'drop'),
         ('Оборудование и монтаж', 'hw'), ('ИТОГО', 'total')]
for i, (name, key) in enumerate(items):
    ws.cell(row=r, column=3, value=name)
    for col, tag in zip(range(4, 8), 'ABCD'):
        val = COST[tag][key]
        if isinstance(val, dict):
            val = sum(val.values())
        ws.cell(row=r, column=col, value=round(val, 1))
    if key == 'total':
        ws.cell(row=r, column=4, value=f'=SUM(D{D1_FIRST}:D{r-1})')
        ws.cell(row=r, column=5, value=f'=SUM(E{D1_FIRST}:E{r-1})')
        ws.cell(row=r, column=6, value=f'=SUM(F{D1_FIRST}:F{r-1})')
        ws.cell(row=r, column=7, value=f'=SUM(G{D1_FIRST}:G{r-1})')
        for c in range(3, 8):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name=base.FONT_NAME, size=11, bold=True, color=base.PRIMARY)
            cell.fill = PatternFill('solid', fgColor=base.SECONDARY)
            cell.alignment = Alignment(horizontal='right' if c > 3 else 'left', vertical='center')
            if c > 3:
                cell.number_format = F_U
        D_TOT_R = r
        r += 1
        continue
    for c in range(3, 8):
        body_cell(ws, r, c, i, left=(c == 3))
        if c > 3:
            ws.cell(row=r, column=c).number_format = F_U
    ws.row_dimensions[r].height = 18
    r += 1
ws.cell(row=r, column=3, value='Доп. шкафы ОРШ (сверх базовых 6, по 1,5 у.е.)')
ws.cell(row=r, column=4, value=0)
ws.cell(row=r, column=5, value=0)
ws.cell(row=r, column=6, value=0)
ws.cell(row=r, column=7, value=round(DC['extra_orsh_cost'], 1))
for c in range(3, 8):
    body_cell(ws, r, c, 3, left=(c == 3))
    if c > 3:
        ws.cell(row=r, column=c).number_format = F_U
D_BOX_R = r
r += 1
ws.cell(row=r, column=3, value='ИТОГО с доп. шкафами')
for col, L in zip(range(4, 8), 'DEFG'):
    ws.cell(row=r, column=col, value=f'={L}{D_TOT_R}+{L}{D_BOX_R}')
for c in range(3, 8):
    cell = ws.cell(row=r, column=c)
    cell.font = Font(name=base.FONT_NAME, size=11, bold=True, color=base.PRIMARY)
    cell.fill = PatternFill('solid', fgColor=base.SECONDARY)
    cell.alignment = Alignment(horizontal='right' if c > 3 else 'left', vertical='center')
    if c > 3:
        cell.number_format = F_U
D_ALL_R = r
r += 1
ws.cell(row=r, column=3, value='Δ к лучшей схеме')
for col, L in zip(range(4, 8), 'DEFG'):
    ws.cell(row=r, column=col, value=f'={L}{D_ALL_R}/MIN($D${D_ALL_R}:$G${D_ALL_R})-1')
for c in range(3, 8):
    body_cell(ws, r, c, 0, left=(c == 3))
    if c > 3:
        ws.cell(row=r, column=c).number_format = F_PCT
r += 1
caption(ws, r, 'Индекс по коэффициентам листа «Проверка волокно-км» (цена кабеля ~ (F/8)^0,5; оборудование по '
               'ориентировочным долям). Оценка для сравнения схем, не для сметы. Все схемы имеют 6 базовых ОРШ на ЦУ — '
               'в сравнении учтены только дополнительные шкафы схемы D.', LAST)
r += 2

# Д2: чувствительность к k
write_headers(ws, ['Показатель цены k', 'A: централизо-ванная', 'B: каскад 1:8+1:8',
                   'C: каскад 1:4+1:16', 'D: зонные ОРШ', 'Лучшая'], r)
r += 1
D2_FIRST = r
mtD15 = DBOOK['materials_total']
orsh_ports15 = DBOOK['totals']['orsh_ports']
for i, k in enumerate((0.0, 0.3, 0.5, 0.7, 1.0)):
    abck = de28.scheme_abc_costs(k)
    cdk = de28.cost_of(mtD15, orsh_ports15, k)
    vals = [abck['A_centr']['total'], abck['B_cascade88']['total'], abck['C_cascade416']['total'],
            cdk['total'] + DC['extra_orsh_cost']]
    ws.cell(row=r, column=3, value=k)
    for col, v in zip(range(4, 8), vals):
        ws.cell(row=r, column=col, value=round(v, 1))
    ws.cell(row=r, column=8, value=f'=CHOOSE(MATCH(MIN(D{r}:G{r}),D{r}:G{r},0),"A","B","C","D")')
    for c in range(3, 9):
        body_cell(ws, r, c, i, align='center' if c == 8 else 'right')
    ws.cell(row=r, column=3).number_format = '0.0'
    for c in range(4, 8):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.row_dimensions[r].height = 18
    r += 1
D2_LAST = r - 1
caption(ws, r, 'k = 0 — цена кабеля не зависит от ёмкости; 0,5 — реалистично (√F); 1 — пропорционально волокно-км. '
               'D с доп. шкафами. При k = 0 выигрывает A (520 у.е.), при k >= 0,3 — каскады; D устойчиво вторая '
               'с минимальной длиной.', LAST)
r += 2

# ------------------------------------------------- Блок Е: вывод ------------
section_row(ws, r, 'Е. Вывод', LAST)
r += 1
VERDICT = [
    ('Децентрализация работает: перенос сплиттеров из одного ОРШ села в зонные шкафы (в центрах секторов) сократил '
     'волокно-км с 4 375,1 (схема A) до 1 347,3 — на 69% — при полностью сохранённой топологии: те же муфты, те же '
     'дропы (95,8 км — минимум по всем схемам), та же трасса магистрали 73,1 км.'),
    ('Схема D — лидер по суммарной длине кабельной продукции: 183,0 км (87,2 магистраль + 95,8 дропы) против '
     '205,2 км у A, 247,2 у B, 315,1 у C и 191,2 км у «оптимума по длине» (R50). Максимальная ёмкость участка — '
     '92 волокна против 972 у A, параллельных кабелей на участке — нет (было 2): фидеры к медианам полностью '
     'разместились в распределительных кабелях.'),
    ('Цена децентрализации — оборудование: 42 ОРШ вместо 6 (36 доп. шкафов, +54 у.е.), 64 сплиттера, 5 040 портов '
     'кросса. Индекс стоимости 524 у.е. с шкафами: на 12% дешевле централизованной (596), но на 8,9% дороже каскада '
     'C (482). Выигрыш v3 против v1-топологии (533 у.е., 1 562,5 вол-км): −215,2 вол-км волокна (−13,8%), на 2 шкафа меньше.'),
    ('Чувствительность: при плоских ценах кабеля (k = 0) лучшая — A; при реалистичных k >= 0,3 — каскады, D — '
     'устойчивая вторая схема (блок Д2). D выигрывает у B по стоимости за счёт коротких дропов и отсутствия '
     'параллельной прокладки.'),
    ('Эксплуатационный профиль D ближе к централизованной: нет РОР с полупустыми сплиттерами (заполнение зон 75-100% '
     'против 45% у C), подключение абонента и OTDR-диагностика — из зонного ОРШ (средний маршрут волокна ДХ -> свой ОРШ '
     '322 м против 1 361 м у A), портов OLT меньше, чем у каскадов (49 против 66 и 83). Плюс свой бонус: авария зонного '
     'шкафа затрагивает только свою зону, а не всё село.'),
    ('Итог: если критерий — минимальное волокно и простая эксплуатация, лучшая схема D: 1 347,3 волокно-км (ниже '
     'касекада B), 183,0 км кабельной продукции, дропы 95,8 км. Если критерий — минимальная смета при реалистичных '
     'ценах, каскад 1:4+1:16 остаётся первым (482 у.е.), D — второй (524 у.е.) с минимальным волокном, централизованная '
     '— третья (596 у.е.).'),
]
for text in VERDICT:
    ws.cell(row=r, column=2, value=text)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=LAST)
    cell = ws.cell(row=r, column=2)
    cell.font = base.font_body()
    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    lines = max(2, math.ceil(len(text) / 150))
    ws.row_dimensions[r].height = lines * 14 + 8
    r += 1

ws.freeze_panes = 'D5'
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0

# =========================================================== МЕТОДИКА =======
ws4 = wb['Методика']
# идемпотентность: удалить старую секцию 8, если есть
r8 = None
for row in range(5, ws4.max_row + 1):
    val = ws4.cell(row=row, column=3).value
    if isinstance(val, str) and val.startswith('8. Децентрализованная схема'):
        r8 = row
        break
if r8 is not None and ws4.max_row >= r8:
    ws4.delete_rows(r8, ws4.max_row - r8 + 1)

# максимальный номер пункта
n_max = 0
for row in range(5, ws4.max_row + 1):
    v = ws4.cell(row=row, column=2).value
    if isinstance(v, (int, float)):
        n_max = max(n_max, int(v))

r4 = ws4.max_row + 1
ws4.cell(row=r4, column=3, value='8. Децентрализованная схема (зонные ОРШ, единый узел OLT)')
for c in range(2, 5):
    cell = ws4.cell(row=r4, column=c)
    cell.fill = sect_fill()
    cell.font = sect_font()
    cell.alignment = Alignment(horizontal='left', vertical='center')
ws4.row_dimensions[r4].height = 24
r4 += 1

M8 = [
    ('Принцип',
     'По предложению пользователя рассчитана децентрализованная схема D: в селе несколько ОРШ вместо одного. Дерево '
     'сети (топология, муфты, дропы) не меняется; сплиттеры 1:64 переносятся из ОРШ ЦУ в зонные шкафы, устанавливаемые '
     'в центрах секторов (медианах деревьев зон). Единый узел OLT: одна станция, фидер заходит в ЦУ села и расходится '
     'по зонам по кратчайшим трассам дорожного графа в границе НП (межселённый транспорт — за рамками расчёта).'),
    ('Разбиение на зоны',
     'Жадный алгоритм: кандидаты — муфты ветвления с потоком не менее 48 ДХ (заполнение сплиттера 1:64 не менее 75%); '
     'на каждом шаге принимается врез с максимальной маржинальной экономией волокно-км (точный пересчёт полной '
     'раскладки с медианами); врез отклоняется, если экономия ниже порога S_MIN. Рекомендовано S_MIN = 15 волокно-км: '
     '28 зон + 6 ЦУ = 34 ОРШ. Контроль: без врезов модель воспроизводит централизованную книгу точно (4 375,1 '
     'волокно-км); v3 с медианами = врезам воспроизводит v2 точно.'),
    ('Волокна участков',
     'Распределительные волокна зоны (от ОРШ-медианы): F = max(8; ceil(1,25 x ДХ потока зоны)). Фидерные волокна: '
     'ceil(1,25 x сплиттеры зоны) — на участках кратчайшего пути ЦУ -> зонный ОРШ (Дейкстра в границе НП); на общих '
     'с деревом участках едут в одном кабеле, вне дерева — отдельный кабель >= 8 волокон. Разложение 8-96.'),
    ('Оборудование зон',
     'Зонный ОРШ: уличный шкаф с кроссом 48/96/144/288/576 портов (порты = 1,1 x ДХ зоны), сплиттеры 1:64 '
     'ceil(ДХ зоны / 64), устанавливается в центре сектора (медиане дерева зоны — минимуме распределительных волокон '
     'плюс фидер). ЦУ — обычный ряд 144-1152 портов, обслуживает корневую зону.'),
    ('Нормы',
     'Сварки = (2 x ДХ + 2 x фидерные волокна активные) x 1,1; пигтейли = ДХ + 2 x сплиттеры; дропы +5%, '
     'магистраль +10%, подвесы 30/км — как во всей книге. Доп. шкафы ОРШ — отдельная строка стоимости '
     '(1,5 у.е. = ~1,5 км кабеля 8F с монтажом).'),
    ('Результат',
     'D v3 (S_MIN = 15): волокно-км 1 347,3 (-69% к A; -13,8% к v1 1 562,5); магистраль 87,2 км; дропы 95,8 км; '
     'ВСЕГО 183,0 км — минимум среди всех схем книги; 49 сплиттеров 1:64; сварки 5 244; порты ОРШ 3 696; OLT 49; '
     'макс. ёмкость 92F, параллельных кабелей нет. Индекс 524 у.е. с шкафами (A 596, B 499, C 482). '
     'По волокну и эксплуатации D — лучшая; по смете — вторая после каскада 1:4+1:16.'),
]
n4 = n_max
for name, desc in M8:
    n4 += 1
    ws4.cell(row=r4, column=2, value=n4)
    ws4.cell(row=r4, column=3, value=name)
    ws4.cell(row=r4, column=4, value=desc)
    fill = base.fill_data_row(n4)
    for c in range(2, 5):
        cell = ws4.cell(row=r4, column=c)
        cell.fill = fill
        cell.font = base.font_body()
        if c == 2:
            cell.alignment = Alignment(horizontal='center', vertical='top')
        else:
            cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    lines = max(math.ceil(len(desc) / 110), math.ceil(len(name) / 30), 1)
    ws4.row_dimensions[r4].height = max(22, lines * 14 + 8)
    r4 += 1

wb.properties.creator = 'Z.ai'
wb.save(OUT)
print('Сохранено:', OUT)
print('Листы:', wb.sheetnames)
print(f'Лист «Децентрализация ОРШ»: блок Б {B_FIRST}-{B_LAST} (итог {B_LAST+1}), '
      f'блок В {V_FIRST}-{V_LAST}, график (данные {CH_FIRST}-{CH_LAST}), '
      f'блок Г {G_FIRST}-{G_LAST}, блок Д1 {D1_FIRST}-{D_ALL_R}, блок Д2 {D2_FIRST}-{D2_LAST}')
print(f'Методика: секция 8 добавлена, пункты {n_max + 1}-{n4}')
