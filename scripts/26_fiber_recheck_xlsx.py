# -*- coding: utf-8 -*-
"""
Шаг 26. Лист «Проверка волокно-км» в книге каскадной сводной таблицы.

Ответ на вопрос пользователя: почему в централизованной схеме очень большое
волокно-км (схема оптимальна по длине дропов и кабелей) — перепроверка расчёта
и оценка, может ли централизованная схема быть лучшим вариантом.

Блоки листа:
  А. Независимая перепроверка: волокно-км книги vs пересчёт (по 6 СНП);
  Б. Декомпозиция волокно-км: база / резерв 25 % / мин. 8 / стандартные ёмкости;
  В. Три схемы: физика различия (волокно-км на ДХ, ёмкость BoQ);
  Г. Ориентировочный индекс стоимости + чувствительность к цене ёмкости k;
  Д. Вывод.

Плюс секция 7 «Проверка волокно-км централизованной схемы» в «Методике».
Существующие листы не меняются. Скрипт идемпотентен.
Источник данных: work/centralized_recheck.json (шаг 25), work/boq_data.json.
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

RC = json.load(open(f'{BASE_DIR}/work/centralized_recheck.json', encoding='utf-8'))
BOOK = json.load(open(f'{BASE_DIR}/work/boq_data.json', encoding='utf-8'))
BV = {v['key']: v for v in BOOK['villages']}
RE_V = RC['recheck']['villages']
TOT = RC['recheck']['totals']
COST = RC['cost']['base']
SENS = RC['cost']['sensitivity']
K_STAR = RC['cost']['breakeven_k']
INST = RC['installed_with_margin']

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
    return PatternFill('solid', fgColor='E8F5E9')

def write_headers(ws, headers, row, col_start=2):
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
if 'Проверка волокно-км' in wb.sheetnames:
    del wb['Проверка волокно-км']
ws = wb.create_sheet('Проверка волокно-км', 4)      # после «Оптимум по длине»

LAST = 12                                           # столбец L
base.setup_sheet(ws, title='Проверка волокно-км централизованной схемы — FTTH (GPON), 6 СНП ВКО',
                 last_col=LAST)
ws['B3'] = ('Вопрос: почему в централизованной схеме 4 375 волокно-км при минимальной суммарной длине кабеля? '
            'Независимая перепроверка расчёта, декомпозиция показателя и сопоставление с каскадными схемами. '
            'Сети и топология — без изменений. Подготовлено ' + DATE)
ws['B3'].font = cap_font()
ws.row_dimensions[3].height = 14
set_widths(ws, {'A': 3, 'B': 5, 'C': 36, 'D': 10, 'E': 12, 'F': 12, 'G': 12,
                'H': 13, 'I': 11, 'J': 11, 'K': 10, 'L': 10})

# ------------------------------------------------- Блок А: перепроверка -----
r = 5
section_row(ws, r, 'А. Независимая перепроверка расчёта централизованной схемы', LAST)
r += 1
write_headers(ws, ['№', 'СНП', 'ДХ (проект)', 'Волокно-км — книга',
                   'Волокно-км — пересчёт', 'Расхождение', 'Статус'], r)
r += 1
A_FIRST = r
for i, v in enumerate(RE_V, 1):
    b = BV[v['key']]
    ws.cell(row=r, column=2, value=i)
    ws.cell(row=r, column=3, value=v['name'])
    ws.cell(row=r, column=4, value=v['dhx'])
    ws.cell(row=r, column=5, value=b['fiber_km'])
    ws.cell(row=r, column=6, value=v['fiber_km'])
    ws.cell(row=r, column=7, value=f'=F{r}-E{r}')
    ws.cell(row=r, column=8, value=f'=IF(ABS(G{r})<0.15,"совпадает","РАСХОЖДЕНИЕ")')
    for c in range(2, 9):
        body_cell(ws, r, c, i - 1, left=(c == 3), align='center' if c in (2, 8) else 'right')
    ws.cell(row=r, column=4).number_format = F_INT
    for c in (5, 6, 7):
        ws.cell(row=r, column=c).number_format = F_KM
    ws.row_dimensions[r].height = 22
    r += 1
A_LAST = r - 1
tr = r
ws.cell(row=tr, column=3, value='ИТОГО')
ws.cell(row=tr, column=4, value=f'=SUM(D{A_FIRST}:D{A_LAST})')
ws.cell(row=tr, column=5, value=f'=SUM(E{A_FIRST}:E{A_LAST})')
ws.cell(row=tr, column=6, value=f'=SUM(F{A_FIRST}:F{A_LAST})')
ws.cell(row=tr, column=7, value=f'=F{tr}-E{tr}')
ws.cell(row=tr, column=8, value=f'=IF(ABS(G{tr})<0.15,"совпадает","РАСХОЖДЕНИЕ")')
base.style_total_row(ws, row_num=tr, col_start=2, col_end=8)
ws.cell(row=tr, column=4).number_format = F_INT
for c in (5, 6, 7):
    ws.cell(row=tr, column=c).number_format = F_KM
    ws.cell(row=tr, column=c).alignment = Alignment(horizontal='right', vertical='center')
r = tr + 1
caption(ws, r, 'Пересчёт выполнен независимой реализацией (обход дерева DFS вместо BFS, код писался заново); '
               'дополнительно сверены ДХ, муфты, длины магистрали и дропов, ёмкости кабеля по сёлам — расхождений нет. '
               'Винное: 1 дроп (hh 23) привязан к ОРШ, его волокно не проходит по магистрали — на итог не влияет.', LAST)
r += 2

# ------------------------------------------------- Блок Б: декомпозиция -----
section_row(ws, r, 'Б. Декомпозиция волокно-км: из чего складываются 4 375 км', LAST)
r += 1
write_headers(ws, ['№', 'СНП', 'ДХ', 'База: выделенное волокно каждому ДХ, км',
                   '+ Резерв 25 %, км', '+ Минимум 8 волокон, км', '+ Стандартные ёмкости, км',
                   'Итого волокно-км', 'Ср. маршрут волокна, м', 'Медиана, м', 'p90, м'], r)
r += 1
B_FIRST = r
for i, v in enumerate(RE_V, 1):
    dc = v['decomp']
    base_km, std = round(dc['base'], 1), round(dc['std'], 1)
    inc_res = round(dc['reserve'] - dc['base'], 1)
    inc_min8 = round(dc['min8'] - dc['reserve'], 1)
    inc_std = round(std - base_km - inc_res - inc_min8, 1)   # поглощает округление
    ws.cell(row=r, column=2, value=i)
    ws.cell(row=r, column=3, value=v['name'])
    ws.cell(row=r, column=4, value=v['dhx'])
    ws.cell(row=r, column=5, value=base_km)
    ws.cell(row=r, column=6, value=inc_res)
    ws.cell(row=r, column=7, value=inc_min8)
    ws.cell(row=r, column=8, value=inc_std)
    ws.cell(row=r, column=9, value=f'=SUM(E{r}:H{r})')
    ws.cell(row=r, column=10, value=v['routes']['avg_m'])
    ws.cell(row=r, column=11, value=v['routes']['med_m'])
    ws.cell(row=r, column=12, value=v['routes']['p90_m'])
    for c in range(2, 13):
        body_cell(ws, r, c, i - 1, left=(c == 3), align='center' if c == 2 else 'right')
    ws.cell(row=r, column=4).number_format = F_INT
    for c in range(5, 10):
        ws.cell(row=r, column=c).number_format = F_KM
    for c in (10, 11, 12):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.row_dimensions[r].height = 22
    r += 1
B_LAST = r - 1
tr = r
ws.cell(row=tr, column=3, value='ИТОГО')
for col in (4, 5, 6, 7, 8):
    L = chr(64 + col)
    ws.cell(row=tr, column=col, value=f'=SUM({L}{B_FIRST}:{L}{B_LAST})')
ws.cell(row=tr, column=9, value=f'=SUM(I{B_FIRST}:I{B_LAST})')
ws.cell(row=tr, column=10, value=f'=IFERROR(SUMPRODUCT(J{B_FIRST}:J{B_LAST},D{B_FIRST}:D{B_LAST})/D{tr},"")')
ws.cell(row=tr, column=11, value='—')
ws.cell(row=tr, column=12, value='—')
base.style_total_row(ws, row_num=tr, col_start=2, col_end=12)
ws.cell(row=tr, column=4).number_format = F_INT
for c in range(5, 10):
    ws.cell(row=tr, column=c).number_format = F_KM
    ws.cell(row=tr, column=c).alignment = Alignment(horizontal='right', vertical='center')
ws.cell(row=tr, column=10).number_format = F_INT
r = tr + 1
caption(ws, r, 'Хвостовые участки с минимумом 8 волокон: 6 873 участка суммарной длиной 29,0 км — лишь 232 волокно-км (5 %). '
               'Средний волоконный маршрут ДХ (ОРШ -> муфта) по 6 СНП — 1 361 м. Резерв 25 % заложен и в каскадных схемах.', LAST)
r += 2

# ------------------------------------------------- Блок В: три схемы --------
section_row(ws, r, 'В. Три схемы: почему в каскадах волокон в 3,5–4,9 раза меньше', LAST)
r += 1
write_headers(ws, ['Схема', 'Волокно-км', 'Установленная ёмкость BoQ (+10 %), волокно-км',
                   'Волокно-км на 1 ДХ, км'], r)
ws.cell(row=r, column=7, value='Принцип формирования ёмкости участка магистрали')
base.style_header_row(ws, row_num=r, col_start=7, col_end=LAST)
ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=LAST)
r += 1
V_ROWS = [
    ('A. Централизованная 1:64 (сплиттеры в ОРШ)', COST['A_centr']['fiber_km'], INST['A_centr'],
     'Каждому ДХ — выделенное волокно на всей трассе от ОРШ до его муфты (в среднем 1 361 м); '
     'ёмкость участка = 1,25 × ДХ ниже по потоку, минимум 8 волокон.'),
    ('B. Каскадная 1:8 + 1:8 (радиус РОР 100 м)', COST['B_cascade88']['fiber_km'], INST['B_cascade88'],
     'Одно волокно делится между 8 абонентами до РОР (сплиттер 1:8 в РОР); '
     'ёмкость участка = 1,25 × число РОР ниже по потоку (515 РОР).'),
    ('C. Каскадная 1:4 + 1:16 (радиус РОР 150 м) — принята', COST['C_cascade416']['fiber_km'], INST['C_cascade416'],
     'Одно волокно делится между 16 абонентами до РОР (сплиттер 1:16 в РОР); '
     'ёмкость участка = 1,25 × число РОР ниже по потоку (323 РОР).'),
]
V_FIRST = r
for i, (name, fkm, inst, principle) in enumerate(V_ROWS, 1):
    ws.cell(row=r, column=3, value=name)
    ws.cell(row=r, column=4, value=fkm)
    ws.cell(row=r, column=5, value=inst)
    ws.cell(row=r, column=6, value=f'=ROUND(D{r}/2334,2)')
    ws.cell(row=r, column=7, value=principle)
    for c in range(3, 8):
        body_cell(ws, r, c, i - 1, left=(c in (3, 7)))
    for c in range(8, LAST + 1):
        cell = ws.cell(row=r, column=c)
        cell.fill = base.fill_data_row(i - 1)
    ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=LAST)
    ws.cell(row=r, column=4).number_format = F_KM
    ws.cell(row=r, column=5).number_format = F_INT
    ws.cell(row=r, column=6).number_format = '0.00'
    ws.row_dimensions[r].height = 42
    r += 1
V_LAST = r - 1
caption(ws, r, 'Во всех схемах обслуживается 2 334 ДХ на одной и той же геометрии сети; установленная ёмкость BoQ — '
               'магистральный кабель по позициям сводной таблицы (с запасом +10 %).', LAST)
r += 2

# ------------------------------------------------- Блок Г: индекс стоимости -
section_row(ws, r, 'Г. Волокно-км и деньги: ориентировочный индекс стоимости трёх схем', LAST)
r += 1
caption(ws, r, 'у.е. = 1 км 8-волоконного самонесущего кабеля. Цена кабеля ёмкости F принята ~ (F/8)^0,5: '
               '96-волоконный дороже 8-волоконного в 3,0–3,5 раза (по данным рынка); дроп 2F = 0,50 у.е./км.', LAST)
r += 1
caption(ws, r, 'Оборудование — ориентировочные коэффициенты к стоимости км кабеля 8F: муфта 0,125; РОР-узел 0,25; '
               'сплиттер 0,045–0,22 (по типу); сварка 0,005; коннектор 0,007; порт кросса ОРШ 0,02; порт OLT 0,40; '
               'подвес 0,008. Оценка для сравнения схем, не для сметы.', LAST)
r += 1
write_headers(ws, ['Компонент', 'A: централизо-ванная', 'B: каскад 1:8+1:8', 'C: каскад 1:4+1:16'], r)
r += 1
G1_FIRST = r
G1_ROWS = [
    ('Магистральный кабель (взвешенно по ёмкостям)', 'cable'),
    ('Дроп-кабель', 'drop'),
    ('Оборудование и монтаж (муфты, РОР, сплиттеры, сварки, кросс, OLT, подвесы)', 'hw'),
]
for i, (label, key) in enumerate(G1_ROWS, 1):
    ws.cell(row=r, column=3, value=label)
    for j, t in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
        val = sum(COST[t]['hw'].values()) if key == 'hw' else COST[t][key]
        ws.cell(row=r, column=4 + j, value=round(val, 1))
    for c in range(3, 7):
        body_cell(ws, r, c, i - 1, left=(c == 3))
        if c > 3:
            ws.cell(row=r, column=c).number_format = F_KM
    ws.row_dimensions[r].height = 26
    r += 1
G1_LAST = r - 1
tr = r
ws.cell(row=tr, column=3, value='ИТОГО индекс стоимости, у.е.')
for j, col in enumerate((4, 5, 6)):
    L = chr(64 + col)
    ws.cell(row=tr, column=col, value=f'=SUM({L}{G1_FIRST}:{L}{G1_LAST})')
base.style_total_row(ws, row_num=tr, col_start=3, col_end=6)
for col in (4, 5, 6):
    ws.cell(row=tr, column=col).number_format = F_KM
    ws.cell(row=tr, column=col).alignment = Alignment(horizontal='right', vertical='center')
G_TOT = tr
r += 1
ws.cell(row=r, column=3, value='Δ к лучшей схеме')
for col in (4, 5, 6):
    L = chr(64 + col)
    ws.cell(row=r, column=col, value=f'={L}{G_TOT}/MIN($D${G_TOT}:$F${G_TOT})-1')
for c in range(3, 7):
    body_cell(ws, r, c, 1, left=(c == 3))
    if c > 3:
        ws.cell(row=r, column=c).number_format = F_PCT
ws.row_dimensions[r].height = 22
r += 2

# Г2: чувствительность к показателю цены k
write_headers(ws, ['Показатель цены k', 'A: централизо-ванная', 'B: каскад 1:8+1:8',
                   'C: каскад 1:4+1:16', 'Лучшая схема'], r)
r += 1
G2_FIRST = r
K_ORDER = ['0.0', '0.3', '0.4', '0.5', '0.6', '0.7', '1.0']
for i, k in enumerate(K_ORDER, 1):
    s = SENS[k]
    ws.cell(row=r, column=3, value=float(k))
    ws.cell(row=r, column=4, value=s['A_centr'])
    ws.cell(row=r, column=5, value=s['B_cascade88'])
    ws.cell(row=r, column=6, value=s['C_cascade416'])
    ws.cell(row=r, column=7, value=f'=IF(AND(D{r}<=E{r},D{r}<=F{r}),"A",IF(E{r}<=F{r},"B","C"))')
    for c in range(3, 8):
        body_cell(ws, r, c, i - 1, left=False, align='center' if c == 7 else 'right')
    ws.cell(row=r, column=3).number_format = '0.0'
    for c in (4, 5, 6):
        ws.cell(row=r, column=c).number_format = F_INT
    ws.row_dimensions[r].height = 20
    r += 1
G2_LAST = r - 1
caption(ws, r, 'k = 0 — цена кабеля не зависит от ёмкости (критерий чистой длины); 0,5 — реалистично (√F, рынок); '
               '1 — пропорционально волокно-км. Точка безразличия A и лучшей из каскадов: k* ≈ 0,16 — централизованная '
               'дешевле только при почти плоских ценах, что рынку не соответствует.', LAST)
r += 2

# ------------------------------------------------- Блок Д: вывод ------------
section_row(ws, r, 'Д. Вывод', LAST)
r += 1
VERDICT = [
    ('Расчёт подтверждён. Независимая перепроверка (обход дерева DFS, код писался заново) воспроизвела волокно-км по всем '
     '6 СНП точно: 4 375,1 км — столько же, сколько в сводной таблице. Сходятся и ДХ, и муфты, и длины магистрали с дропами, '
     'и ёмкости кабеля по сёлам. Ошибки в расчёте нет.'),
    ('Причина большого волокно-км — сама архитектура: сплиттер стоит в ОРШ, и каждому абоненту выделяется собственное '
     'волокно на всей трассе до его муфты. Средняя длина маршрута волокна — 1 361 м (в Верхнеберезовке медиана 1 819 м, '
     'p90 — 2 827 м). Отсюда базовые 3 175 волокно-км (73 % итога); резерв 25 % добавляет 826 км (он же заложен и в каскадах), '
     'минимум 8 волокон на хвостах — 131 км, округление до стандартных ёмкостей — 243 км.'),
    ('В каскадах волокон меньше не потому, что сеть короче, а потому, что одно волокно делится между 8–16 абонентами до РОР: '
     '1 256 волокно-км у схемы B и 889 у C против 4 375 у A — при одинаковой геометрии сети. Волокно-км на одного абонента: '
     '1,88 км у A против 0,54 и 0,38 км у каскадов.'),
    ('Волокно-км — не деньги. Цена кабеля растёт примерно как корень из ёмкости, поэтому 33,8 км 96-волоконного кабеля — это '
     'не 12× стоимости 8-волоконного, а лишь ~3,5×. Ориентировочный индекс стоимости (у.е. = 1 км кабеля 8F): централизованная '
     '596, каскад B — 499, каскад C — 482. Несмотря на минимальную суммарную длину (205,2 км) и самые короткие дропы (95,8 км), '
     'централизованная схема дороже каскада C на ~24 %: она выиграла бы только при почти плоских ценах (k* < 0,16), чего на рынке нет.'),
    ('Практические ограничения A: у ОРШ Верхнеберезовки до 972 волокон — до 11 параллельных кабелей на участке (нагрузка на '
     'опоры, ветровая нагрузка, монтаж), кросс ОРШ на 3 600 портов. Достоинства: всего 39 портов OLT (против 66 и 83), все '
     'сплиттеры в ОРШ (39 против 581 и 406 шт.), нет потерь на незаполненных портах РОР (в каскадах занято 45–55 %), '
     'подключение абонента и OTDR-диагностика — из ОРШ, без выезда к РОР.'),
    ('Итог: по критерию «минимальная длина дропов и кабелей» централизованная схема действительно лучшая из трёх рассчитанных '
     '(205,2 км против 247,2 и 315,1 км; дропы 95,8 км), а расчёт её волокно-км верен. Но по капитальным затратам при '
     'реалистичных ценах кабеля выгоднее каскад 1:4 + 1:16 — на 19 % дешевле (482 против 596 у.е.). Выбор: минимальная длина '
     'и простота эксплуатации — централизованная; минимальная смета — каскад 1:4 + 1:16 (текущая рекомендация сохраняется).'),
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

# ------------------------------------------------- График: стоимость vs k ---
r += 1
CH_HDR = r
ws.cell(row=r, column=2, value='k')
ws.cell(row=r, column=3, value='A: централизованная')
ws.cell(row=r, column=4, value='B: каскад 1:8+1:8')
ws.cell(row=r, column=5, value='C: каскад 1:4+1:16')
base.style_header_row(ws, row_num=r, col_start=2, col_end=5)
r += 1
CH_FIRST = r
for k in K_ORDER:
    s = SENS[k]
    ws.cell(row=r, column=2, value=float(k))
    ws.cell(row=r, column=3, value=s['A_centr'])
    ws.cell(row=r, column=4, value=s['B_cascade88'])
    ws.cell(row=r, column=5, value=s['C_cascade416'])
    fill = base.fill_data_row(r - CH_FIRST)
    for c in range(2, 6):
        cell = ws.cell(row=r, column=c)
        cell.fill = fill
        cell.font = base.font_body()
        cell.alignment = Alignment(horizontal='right', vertical='center')
        cell.number_format = '0.0' if c == 2 else F_INT
    r += 1
CH_LAST = r - 1

ch = LineChart()
ch.style = 10
ch.width = 20
ch.height = 10
data = Reference(ws, min_col=3, max_col=5, min_row=CH_HDR, max_row=CH_LAST)
cats = Reference(ws, min_col=2, min_row=CH_FIRST, max_row=CH_LAST)
ch.add_data(data, titles_from_data=True)
ch.set_categories(cats)
base.setup_chart_titles(ch, title='Индекс стоимости схем в зависимости от цены ёмкости кабеля',
                        y_title='Индекс, у.е. (1 км кабеля 8F)', x_title='Показатель цены k: цена ~ (F/8)^k')
for s in ch.series:
    s.smooth = False
    s.marker = Marker(symbol='circle', size=6)
LINE_COLORS = [base.ACCENT_WARNING, base.PRIMARY, base.ACCENT_POSITIVE]
for s, col in zip(ch.series, LINE_COLORS):
    s.graphicalProperties.line = LineProperties(solidFill=col, w=22000)
ws.add_chart(ch, f'G{CH_HDR}')

ws.freeze_panes = 'C5'
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0

# =========================================================== МЕТОДИКА =======
ws4 = wb['Методика']
# идемпотентность: удалить старую секцию 7, если есть
r7 = None
for row in range(5, ws4.max_row + 1):
    if ws4.cell(row=row, column=3).value == '7. Проверка волокно-км централизованной схемы':
        r7 = row
        break
if r7 is not None and ws4.max_row >= r7:
    ws4.delete_rows(r7, ws4.max_row - r7 + 1)

r4 = ws4.max_row + 1
ws4.cell(row=r4, column=3, value='7. Проверка волокно-км централизованной схемы')
for c in range(2, 5):
    cell = ws4.cell(row=r4, column=c)
    cell.fill = sect_fill()
    cell.font = sect_font()
    cell.alignment = Alignment(horizontal='left', vertical='center')
ws4.row_dimensions[r4].height = 24
r4 += 1

M7 = [
    ('Перепроверка',
     'Показатель волокно-км централизованной схемы (4 375,1 км) подтверждён независимой перепроверкой (обход дерева DFS, '
     'отдельный код): по всем 6 СНП значения книги и пересчёта совпадают; также сверены ДХ, муфты, длины магистрали и '
     'дропов, ёмкости кабеля. Лист «Проверка волокно-км», блок А.'),
    ('Причина',
     'Волокно-км велик из-за архитектуры: каждому ДХ выделяется собственное волокно на всей трассе ОРШ -> муфта '
     '(в среднем 1 361 м, медиана до 1 819 м, p90 до 2 827 м). Декомпозиция: база 3 175 км (73 %) + резерв 25 % '
     '(826 км) + минимум 8 волокон (131 км) + стандартные ёмкости (243 км). В каскадах ёмкость участка задаётся числом '
     'РОР, поэтому волокон в 3,5–4,9 раза меньше.'),
    ('Индекс стоимости',
     'волокно-км — не стоимость: цена кабеля растёт ~ √F (96F в 3,0–3,5 раза дороже 8F). Ориентировочный индекс '
     '(у.е. = 1 км кабеля 8F, цена ~ (F/8)^0,5, оборудование по коэффициентам): централизованная 596, каскад 1:8+1:8 — '
     '499, каскад 1:4+1:16 — 482 у.е. Оценка для сравнения схем, не для сметы.'),
    ('Чувствительность',
     'При k = 0 (цена не зависит от ёмкости) дешевле централизованная (520 у.е.); при реалистичных k >= 0,3 — каскады; '
     'точка безразличия k* ≈ 0,16. При k = 1 (пропорционально волокно-км) централизованная 955 против 459 у.е. у схемы C.'),
    ('Вывод',
     'Централизованная схема лучшая по длине (205,2 км; дропы 95,8 км) и удобна в эксплуатации (39 портов OLT, сплиттеры '
     'только в ОРШ), но при реалистичных ценах кабеля дороже каскада 1:4+1:16 на ~24 % (каскад дешевле на 19 %). '
     'Рекомендация сохраняется: каскад 1:4+1:16 — по стоимости; централизованная — при приоритете длины и эксплуатации.'),
]
n4 = 25
for name, desc in M7:
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
print(f'Лист «Проверка волокно-км»: блок А {A_FIRST}-{A_LAST} (итог {A_LAST+1}), '
      f'блок Б {B_FIRST}-{B_LAST} (итог {B_LAST+1}), блок В {V_FIRST}-{V_LAST}, '
      f'блок Г1 {G1_FIRST}-{G1_LAST} (итог {G_TOT}), блок Г2 {G2_FIRST}-{G2_LAST}, '
      f'график (данные {CH_FIRST}-{CH_LAST})')
print(f'Методика: секция 7 добавлена, пункты 26-{n4}')
