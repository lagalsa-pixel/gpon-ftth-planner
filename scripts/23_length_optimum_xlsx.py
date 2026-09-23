# -*- coding: utf-8 -*-
"""
Шаг 23. Лист «Оптимум по длине» в книге каскадной сводной таблицы:
определение оптимального варианта по минимальной длине дропов и кабелей.

Блоки листа:
  А. Рассчитанные схемы — сравнение по длине (+ строка оптимума R=50 м);
  Б. Параметрический анализ размещения РОР (радиус 0–250 м x ёмкость 8/16 ДХ);
  В. Оптимум по длине (каскад 1:8+1:8, R=50 м) — разбивка по СНП;
  Г. Вывод (вердикт);
  Д. График трейдоффа «суммарная длина <-> волокно-км» (две оси).

Плюс секция 6 «Оптимизация по длине кабельной продукции» в листе «Методика».
Существующие листы («Сводная», «Параметры сетей», «Сравнение схем») не меняются.
Скрипт идемпотентен: повторный запуск пересоздаёт лист и секцию 6.
"""
import sys, os, json, math

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
DATE = '18.09.2026'

SW = json.load(open(f'{BASE_DIR}/work/length_sweep.json', encoding='utf-8'))
REFS = SW['references']
CFGS = SW['configs']
DH = CFGS[0]['dhx_served']                      # 2334 ДХ (инвариант всех схем)

def cfg(r_max, cap):
    return next(c for c in CFGS if c['r_max'] == r_max and c['cap'] == cap)

R50 = cfg(50, 8)                                 # оптимум по длине (практический)
R0 = cfg(0, 8)                                   # теоретический предел

# ---------------------------------------------------------------- стили ----
F_INT = '#,##0'
F_KM = '#,##0.0'
F_PCT = '+0.0%;-0.0%;0.0%'

def sect_font():
    return Font(name=base.FONT_NAME, size=11, bold=base.HEADER_BOLD, color=base.PRIMARY)

def sect_fill():
    return PatternFill('solid', fgColor=base.SECONDARY)

def cap_font():
    return Font(name=base.FONT_NAME, size=9, color=base.NEUTRAL_600)

def best_font():
    return Font(name=base.FONT_NAME, size=11, bold=True, color=base.ACCENT_POSITIVE)

def best_fill():
    return PatternFill('solid', fgColor='E8F5E9')   # CF_POSITIVE_FILL

def write_headers(ws, headers, row):
    for i, h in enumerate(headers, start=2):
        ws.cell(row=row, column=i, value=h)
    base.style_header_row(ws, row_num=row, col_start=2, col_end=1 + len(headers))

def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

def nz(x):
    return None if x in (0, 0.0) else x

# =========================================================== КНИГА ==========
wb = load_workbook(OUT)
if 'Оптимум по длине' in wb.sheetnames:
    del wb['Оптимум по длине']
ws = wb.create_sheet('Оптимум по длине', 3)      # после «Сравнение схем»

HDRS = ['№', 'Вариант / конфигурация РОР', 'Сплиттеры', 'РОР, шт', 'Заполнение портов, %',
        'Дроп-кабель, км', 'в т.ч. подводки РОР→ДХ, км', 'Магистральный кабель, км',
        'СУММА, км', 'Δ к минимуму', 'Волокно-км', 'Ср. дроп, м', 'Макс. дроп, м', 'Сварки, шт']
LAST = 1 + len(HDRS)                             # = 15 (O)
base.setup_sheet(ws, title='Оптимизация по минимальной длине дропов и кабелей — FTTH (GPON), 6 СНП ВКО', last_col=LAST)
ws['B3'] = ('Критерий: суммарная длина закупаемой кабельной продукции с запасами (дроп +5 %, магистраль +10 %) = '
            'дроп-кабель + магистральный кабель по всем ёмкостям; контрольный показатель — волокно-км. '
            'Сети и топология — без изменений; соотношение сплиттеров на длины не влияет, влияет только размещение РОР. Подготовлено ' + DATE)
ws['B3'].font = cap_font()
ws.row_dimensions[3].height = 14

write_headers(ws, HDRS, 4)
set_widths(ws, {'A': 3, 'B': 5, 'C': 36, 'D': 12, 'E': 8, 'F': 9, 'G': 10, 'H': 11,
                'I': 11, 'J': 10, 'K': 10, 'L': 10, 'M': 8, 'N': 8, 'O': 8})

R0_ROW = None       # строка теоретического минимума (база Δ) — заполняется в блоке Б

def data_row(r, num, label, split, c):
    """Строка таблиц А/Б; c — словарь метрик (refs или config)."""
    ws.cell(row=r, column=2, value=num)
    ws.cell(row=r, column=3, value=label)
    ws.cell(row=r, column=4, value=split)
    ws.cell(row=r, column=5, value=c.get('n_pop'))
    ws.cell(row=r, column=6, value=c.get('fill_pct'))
    ws.cell(row=r, column=7, value=c['drop_cable_km'])
    ws.cell(row=r, column=8, value=c.get('extra_km'))
    ws.cell(row=r, column=9, value=c['cable_boq_km'])
    ws.cell(row=r, column=10, value=f'=G{r}+I{r}')
    ws.cell(row=r, column=12, value=c['fiber_km'])
    ws.cell(row=r, column=13, value=c['avg_drop_m'])
    ws.cell(row=r, column=14, value=c['max_drop_m'])
    ws.cell(row=r, column=15, value=c.get('splices'))

def style_row(r, idx, highlight=False, highlight_delta=True):
    fill = best_fill() if highlight else base.fill_data_row(idx)
    for c in range(2, LAST + 1):
        cell = ws.cell(row=r, column=c)
        cell.fill = fill
        cell.font = best_font() if highlight else base.font_body()
        if c == 2 or c == 4:
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        elif c == 3:
            cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        else:
            cell.alignment = Alignment(horizontal='right', vertical='center')
    for c in (5, 15):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.cell(row=r, column=6).number_format = '0.0'
    for c in (7, 8, 9, 10, 12):
        ws.cell(row=r, column=c).number_format = F_KM
    for c in (13, 14):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.row_dimensions[r].height = 26

def delta_formula(r, base_row):
    ws.cell(row=r, column=11, value=f'=IFERROR(J{r}/$J${base_row}-1,"—")')
    ws.cell(row=r, column=11).number_format = F_PCT

def section_row(r, title):
    ws.cell(row=r, column=3, value=title)
    for c in range(2, LAST + 1):
        cell = ws.cell(row=r, column=c)
        cell.fill = sect_fill()
        cell.font = sect_font()
        cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[r].height = 24

# ------------------------------------------------- Блок А: три схемы --------
r = 5
section_row(r, 'А. Рассчитанные схемы — сравнение по длине кабельной продукции')
r += 1
a_rows = [
    ('Централизованная 1:64 (сплиттеры в ОРШ)', '1:64', REFS['centralized'], False),
    ('Каскадная 1:8 + 1:8 (радиус РОР 100 м, до 8 ДХ/РОР) — схема B', '1:8+1:8', REFS['cascade88'], False),
    ('Каскадная 1:4 + 1:16 (радиус РОР 150 м, до 16 ДХ/РОР) — схема C, принята', '1:4+1:16', REFS['cascade16'], False),
    ('Каскадная 1:8 + 1:8, радиус РОР 50 м — ОПТИМУМ ПО ДЛИНЕ', '1:8+1:8', R50, True),
]
n = 0
for label, split, c, hl in a_rows:
    n += 1
    data_row(r, n, label, split, c)
    # заполнение портов для схем B и C (агрегат по 6 СНП)
    if c.get('n2'):
        split2 = 8 if '1:8+1:8' in split else 16
        ws.cell(row=r, column=6, value=round(100.0 * DH / (c['n2'] * split2), 1))
    style_row(r, n, highlight=hl)
    r += 1
A_LAST = r - 1

# ------------------------------------------------- Блок Б: sweep ------------
r += 1
section_row(r, 'Б. Размещение РОР: параметрический анализ (радиус кластера x ёмкость РОР), те же сети')
r += 1
B_HDR = r - 1
n = 0
rows_b = []
for r_max in [0, 50, 75, 100, 125, 150, 175, 200, 250]:
    caps = [8] if r_max == 0 else [8, 16]
    for cap in caps:
        c = cfg(r_max, cap)
        if r_max == 0:
            label = 'Радиус 0 м — РОР в каждой муфте (предельный случай)'
            split = 'не влияет'
        else:
            label = f'Радиус {r_max} м, до {cap} ДХ на РОР'
            split = '1:8+1:8' if cap == 8 else '1:4+1:16'
            if r_max == 100 and cap == 8:
                label += ' (= схема B)'
            if r_max == 150 and cap == 16:
                label += ' (= схема C)'
        hl = (r_max == 50 and cap == 8)
        rows_b.append((label, split, c, hl))
B_FIRST = r
for label, split, c, hl in rows_b:
    n += 1
    data_row(r, n, label, split, c)
    ws.cell(row=r, column=6, value=c['fill_pct'])
    style_row(r, n, highlight=hl)
    if c['r_max'] == 0 and c['cap'] == 8:
        R0_ROW = r
    r += 1
B_LAST = r - 1

# Δ к минимуму (база — предельный случай R=0): живые формулы
for rr in list(range(6, A_LAST + 1)) + list(range(B_FIRST, B_LAST + 1)):
    delta_formula(rr, R0_ROW)

r += 1
for t in ['R — радиус кластера РОР по трассе сети (жадная кластеризация, та же модель, что в основных расчётах); «до N ДХ на РОР» — ёмкость кластера = ёмкость сплиттера 2-й ступени. При радиусе 0 м результаты для 1:8+1:8 и 1:4+1:16 совпадают.',
          'Δ — отношение суммарной длины к предельному минимуму (R=0, 185,1 км). Выделено зелёным — рекомендуемый по критерию длины вариант (радиус 50 м).']:
    ws.cell(row=r, column=2, value=t).font = cap_font()
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=LAST)
    ws.row_dimensions[r].height = 14
    r += 1

# ------------------------------------------------- Блок В: разбивка ---------
r += 1
section_row(r, 'В. Оптимум по длине — каскад 1:8 + 1:8, радиус РОР 50 м: разбивка по СНП')
r += 1
H_V = ['№', 'СНП', 'ДХ (проект)', 'РОР, шт', 'Заполнение портов, %', 'Дроп-кабель, км',
       'в т.ч. подводки, км', 'Магистральный кабель, км', 'СУММА, км', 'Волокно-км',
       'Ср. дроп, м', 'Макс. дроп, м']
for i, h in enumerate(H_V, start=2):
    ws.cell(row=r, column=i, value=h)
base.style_header_row(ws, row_num=r, col_start=2, col_end=1 + len(H_V))
r += 1
V_FIRST = r
for i, v in enumerate(R50['per_village'], 1):
    ws.cell(row=r, column=2, value=i)
    ws.cell(row=r, column=3, value=v['name'])
    ws.cell(row=r, column=4, value=v['dhx_served'])
    ws.cell(row=r, column=5, value=v['n_pop'])
    ws.cell(row=r, column=6, value=v['fill_pct'])
    ws.cell(row=r, column=7, value=v['drop_cable_km'])
    ws.cell(row=r, column=8, value=v['extra_km'])
    ws.cell(row=r, column=9, value=v['cable_boq_km'])
    ws.cell(row=r, column=10, value=f'=G{r}+I{r}')
    ws.cell(row=r, column=11, value=v['fiber_km'])
    ws.cell(row=r, column=12, value=v['avg_drop_m'])
    ws.cell(row=r, column=13, value=v['max_drop_m'])
    fill = base.fill_data_row(i - 1)
    for c in range(2, 14):
        cell = ws.cell(row=r, column=c)
        cell.fill = fill
        cell.font = base.font_body()
        if c in (2, 3):
            cell.alignment = Alignment(horizontal='left' if c == 3 else 'center', vertical='center')
        else:
            cell.alignment = Alignment(horizontal='right', vertical='center')
    for c in (4, 5, 12, 13):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.cell(row=r, column=6).number_format = '0.0'
    for c in (7, 8, 9, 10, 11):
        ws.cell(row=r, column=c).number_format = F_KM
    ws.row_dimensions[r].height = 22
    r += 1
V_LAST = r - 1

tr = r
ws.cell(row=tr, column=3, value='ИТОГО')
for col, f in [(4, f'=SUM(D{V_FIRST}:D{V_LAST})'), (5, f'=SUM(E{V_FIRST}:E{V_LAST})'),
               (6, f'=IFERROR(D{tr}/(E{tr}*8)*100,"")'),
               (7, f'=SUM(G{V_FIRST}:G{V_LAST})'), (8, f'=SUM(H{V_FIRST}:H{V_LAST})'),
               (9, f'=SUM(I{V_FIRST}:I{V_LAST})'), (10, f'=SUM(J{V_FIRST}:J{V_LAST})'),
               (11, f'=SUM(K{V_FIRST}:K{V_LAST})'),
               (12, f'=IFERROR(SUMPRODUCT(L{V_FIRST}:L{V_LAST},D{V_FIRST}:D{V_LAST})/D{tr},"")'),
               (13, f'=MAX(M{V_FIRST}:M{V_LAST})')]:
    ws.cell(row=tr, column=col, value=f)
base.style_total_row(ws, row_num=tr, col_start=2, col_end=13)
for c in (4, 5, 12, 13):
    cell = ws.cell(row=tr, column=c)
    cell.number_format = F_INT
    cell.alignment = Alignment(horizontal='right', vertical='center')
ws.cell(row=tr, column=6).number_format = '0.0'
for c in (7, 8, 9, 10, 11):
    ws.cell(row=tr, column=c).number_format = F_KM
    ws.cell(row=tr, column=c).alignment = Alignment(horizontal='right', vertical='center')

# ------------------------------------------------- Блок Г: вывод ------------
r = tr + 2
section_row(r, 'Г. Вывод')
r += 1
VERDICT = [
    ('Оптимум по критерию минимальной суммарной длины дропов и кабелей — каскадная схема с плотным размещением РОР: '
     'сплиттеры 1:8 + 1:8, радиус кластера 50 м. Суммарная длина 191,2 км (дропы 104,6 + магистраль 86,6) — '
     'на 6,8 % меньше централизованной схемы (205,2 км), на 22,7 % меньше рассчитанного каскада 1:8 + 1:8 (247,2 км) '
     'и на 39,3 % меньше принятого каскада 1:4 + 1:16 (315,1 км). Дроп-линии почти минимальны (104,6 км против '
     'теоретического минимума 95,8 км), магистраль на 20,8 % короче централизованной, волокно-км в 2,3 раза меньше централизованной (1 886 против 4 375).'),
    ('Предельный случай «РОР в каждой муфте» (радиус 0 м) даёт лишь −6,1 км (185,1 км) при +156 РОР, +248 волокно-км '
     'и +873 сварки к варианту радиуса 50 м — не рекомендуется. Средний дроп при радиусе 50 м — 42,6 м (максимум 133 м), '
     'заполнение портов сплиттеров 33 %.'),
    ('Контрфактор: у мелкорадиусных схем в 2,1 раза выше материалоёмкость магистрали (волокно-км 1 886 против 889 у схемы C) '
     'и в 2,7 раза больше пассивных узлов (873 РОР против 323). По волокно-км и минимуму узлов оптимальна принятая схема '
     '1:4 + 1:16 (радиус 150 м) — при ней суммарная длина на 64,8 % выше (315,1 км). Суммарная длина монотонно растёт '
     'с радиусом РОР (185–417 км), волокно-км монотонно падает (2 134–717) — «лучшего по всем критериям сразу» варианта нет.'),
    ('Итог: если решающий критерий — минимальная длина закупаемого кабеля (дропы + магистраль), рекомендуется перейти '
     'на каскад 1:8 + 1:8 с радиусом РОР 50 м; если приоритет — стоимость магистрали и число пассивных узлов — сохранить '
     'принятую схему 1:4 + 1:16 (радиус 150 м). Компромисс — радиус 75–100 м (сумма 228–247 км, волокно-км 1 256–1 426). '
     'Пересчёт сводной таблицы материалов под выбранный вариант — по подтверждению заказчика.'),
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

# ------------------------------------------------- Блок Д: график -----------
r += 1
section_row(r, 'Д. Трейдофф: суммарная длина кабельной продукции и материалоёмкость магистрали')
r += 1
CH_HDR = r
ws.cell(row=r, column=2, value='Радиус, м')
ws.cell(row=r, column=3, value='Сумма, км (1:8+1:8)')
ws.cell(row=r, column=4, value='Сумма, км (1:4+1:16)')
ws.cell(row=r, column=5, value='Волокно-км (1:4+1:16)')
base.style_header_row(ws, row_num=r, col_start=2, col_end=5)
r += 1
CH_FIRST = r
for r_max in [0, 50, 75, 100, 125, 150, 175, 200, 250]:
    c8, c16 = cfg(r_max, 8), cfg(r_max, 16)
    ws.cell(row=r, column=2, value=r_max)
    ws.cell(row=r, column=3, value=c8['L_total'])
    ws.cell(row=r, column=4, value=c16['L_total'])
    ws.cell(row=r, column=5, value=c16['fiber_km'])
    fill = base.fill_data_row(r - CH_FIRST)
    for c in range(2, 6):
        cell = ws.cell(row=r, column=c)
        cell.fill = fill
        cell.font = base.font_body()
        cell.alignment = Alignment(horizontal='right', vertical='center')
        cell.number_format = F_INT if c == 2 else F_KM
    r += 1
CH_LAST = r - 1

c1 = LineChart()
c1.style = 10
c1.width = 21
c1.height = 11
data1 = Reference(ws, min_col=3, max_col=4, min_row=CH_HDR, max_row=CH_LAST)
cats = Reference(ws, min_col=2, min_row=CH_FIRST, max_row=CH_LAST)
c1.add_data(data1, titles_from_data=True)
c1.set_categories(cats)
base.setup_chart_titles(c1, title='Суммарная длина и волокно-км в зависимости от радиуса РОР',
                        y_title='Дропы + магистраль, км', x_title='Радиус кластера РОР, м')
for s in c1.series:
    s.smooth = False
    s.marker = Marker(symbol='circle', size=6)

c2 = LineChart()
data2 = Reference(ws, min_col=5, max_col=5, min_row=CH_HDR, max_row=CH_LAST)
c2.add_data(data2, titles_from_data=True)
for s in c2.series:
    s.smooth = False
    s.marker = Marker(symbol='diamond', size=6)
c2.y_axis.axId = 200
c2.y_axis.title = base.make_chart_title('Волокно-км', 10, bold=False, axis=True)
c1.y_axis.crosses = 'max'
c1 += c2

# цвета линий явно (для LineChart solidFill серии не красит линию)
LINE_COLORS = [base.PRIMARY, base.ACCENT_POSITIVE, base.ACCENT_WARNING]
for s, col in zip(c1.series, LINE_COLORS[:2]):
    s.graphicalProperties.line = LineProperties(solidFill=col, w=22000)
for s in c2.series:
    s.graphicalProperties.line = LineProperties(solidFill=LINE_COLORS[2], w=22000)
ws.add_chart(c1, f'G{CH_HDR}')

ws.freeze_panes = 'D5'
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.print_title_rows = '4:4'

# =========================================================== МЕТОДИКА =======
ws4 = wb['Методика']
# идемпотентность: найти конец секции 5 и удалить всё после него (старую секцию 6)
last_keep = None
for row in range(5, ws4.max_row + 1):
    v = ws4.cell(row=row, column=3).value
    if v == 'За рамками расчёта':
        last_keep = row
if last_keep is None:
    raise RuntimeError('Не найден пункт «За рамками расчёта» в листе «Методика»')
if ws4.max_row > last_keep:
    ws4.delete_rows(last_keep + 1, ws4.max_row - last_keep)

r4 = last_keep + 1
# динамическая нумерация: последний номер пункта в существующей «Методике»
n4 = max((ws4.cell(row=rr, column=2).value or 0) for rr in range(5, last_keep + 1)
         if isinstance(ws4.cell(row=rr, column=2).value, int))
sec_row = r4
ws4.cell(row=r4, column=3, value='6. Оптимизация по длине кабельной продукции')
for c in range(2, 5):
    cell = ws4.cell(row=r4, column=c)
    cell.fill = sect_fill()
    cell.font = sect_font()
    cell.alignment = Alignment(horizontal='left', vertical='center')
ws4.row_dimensions[r4].height = 24
r4 += 1

M6 = [
    ('Критерий',
     'Минимальная суммарная длина закупаемой кабельной продукции: дроп-кабель (запас 5 %) + магистральный кабель по всем '
     'ёмкостям (запас 10 %), км. Контрольный показатель — волокно-км (материалоёмкость магистрали, прокси её стоимости). '
     'Количественный анализ — лист «Оптимум по длине».'),
    ('Метод',
     'Параметрический перебор размещения РОР: радиус кластера 0–250 м × ёмкость 8/16 ДХ (та же модель кластеризации, '
     'топология сетей не менялась). Соотношение сплиттеров на длины не влияет: длины определяются только размещением РОР — '
     'чем крупнее кластеры, тем короче магистраль и меньше волокно-км, но длиннее дроп-подводки РОР→ДХ.'),
    ('Результат',
     'Суммарная длина монотонно растёт с радиусом РОР: от 185,1 км (R=0, РОР в каждой муфте) до 416,8 км (R=250 м); '
     'волокно-км монотонно падает: от 2 134 до 717. Оптимум по длине — радиус 0–50 м (185–191 км); оптимум по '
     'материалоёмкости магистрали — радиус 150–250 м (889–717 волокно-км). Среди трёх рассчитанных схем минимальная '
     'суммарная длина у централизованной (205,2 км), однако она уступает мелкорадиусному каскаду по всем кабельным метрикам.'),
    ('Рекомендация',
     'При приоритете минимальной длины дропов и кабелей — каскад 1:8 + 1:8 с радиусом РОР 50 м: 191,2 км (дропы 104,6 км, '
     'магистраль 86,6 км, волокно-км 1 886, РОР 873, сварки 4 578). При приоритете стоимости магистрали и минимума '
     'пассивных узлов — принятая схема 1:4 + 1:16 (R=150 м). Пересчёт сводной таблицы под выбранный вариант — по '
     'подтверждению заказчика.'),
]
n4 = 21
for name, desc in M6:
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
print(f'Лист «Оптимум по длине»: блок А строки 6-{A_LAST}, блок Б {B_FIRST}-{B_LAST} (база Δ R0={R0_ROW}), '
      f'блок В {V_FIRST}-{V_LAST}, вывод, график (данные {CH_FIRST}-{CH_LAST})')
print(f'Методика: секция 6 добавлена, пункты 22-{n4}')
