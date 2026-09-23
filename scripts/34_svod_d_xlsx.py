# -*- coding: utf-8 -*-
"""
Шаг 34. Лист «Сводная (схема D)» в книге каскадной сводной таблицы.

Полная сводная таблица материалов децентрализованной схемы D (зонные ОРШ 1:64,
единый узел OLT, S_MIN = 15) — в формате листа «Сводная» (схема C):
4 секции, 24 позиции, графы 6 СНП + ИТОГО (живые формулы SUM).

Вставляется сразу после «Сводной» (индекс 1). Существующие листы не меняются.
Плюс секция 9 «Сводная материалов и карты зон схемы D» в «Методике».
Скрипт идемпотентен. Источник: work/boq_decentral_data.json (шаг 29).
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

BASE_DIR = '/home/z/my-project'
OUT = f'{BASE_DIR}/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx'
DATE = '18.09.2026'

DBOOK = json.load(open(f'{BASE_DIR}/work/boq_decentral_data_v4.json', encoding='utf-8'))
V = DBOOK['villages']
VN = [v['name'] for v in V]

# ---------------------------------------------------------------- стили ----
F_INT = '#,##0'
F_KM = '#,##0.0'


def sect_font():
    return Font(name=base.FONT_NAME, size=11, bold=base.HEADER_BOLD, color=base.PRIMARY)


def sect_fill():
    return PatternFill('solid', fgColor=base.SECONDARY)


def cap_font():
    return Font(name=base.FONT_NAME, size=9, color=base.NEUTRAL_600)


def write_headers(ws, headers, row, col_start=2):
    for i, h in enumerate(headers, start=col_start):
        ws.cell(row=row, column=i, value=h)
    base.style_header_row(ws, row_num=row, col_start=col_start,
                          col_end=col_start + len(headers) - 1)


def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


# ============================================================ ЛИСТ ==========
wb = load_workbook(OUT)
if 'Сводная (схема D)' in wb.sheetnames:
    del wb['Сводная (схема D)']
ws = wb.create_sheet('Сводная (схема D)', 1)      # сразу после «Сводной»

HDRS = ['№', 'Наименование', 'Ед. изм.', 'Расчёт / норма'] + VN + ['ИТОГО']
LAST = 1 + len(HDRS)          # 12 (L)
base.setup_sheet(ws, title='Сводная таблица материалов — FTTH (GPON), децентрализованная схема D: зонные ОРШ 1:64 при едином узле OLT, 6 СНП Восточно-Казахстанской области',
                 last_col=LAST)
ws['B3'] = ('Схема D (v3): топология сетей, муфты и дропы — без изменений (как в схемах A/B/C); сплиттеры 1:64 — в зонных ОРШ (S_MIN = 15 волокно-км на шкаф, зона ≥ 48 ДХ), шкафы — в центрах секторов; '
            'фидер от ЦУ — кратчайший путь (Дейкстра) в границе НП, межселённый транспорт — за рамками расчёта • карты зон — download/snp_vko/*_зоны_ОРШ_схема_D.jpg • '
            'допущения — лист «Методика» • сравнение схем — лист «Сравнение схем» • подготовлено ' + DATE)
ws['B3'].font = cap_font()
ws.row_dimensions[3].height = 14

write_headers(ws, HDRS, row=4)
set_widths(ws, {'A': 3, 'B': 5, 'C': 46, 'D': 9, 'E': 30,
                'F': 13, 'G': 12.5, 'H': 12.5, 'I': 12.5, 'J': 12.5, 'K': 12.5, 'L': 12.5})

# позиции: (имя, ед., норма, ключ или функция села, тип формата)
SECTIONS = [
    ('А. Оборудование и узлы', [
        ('Шкаф оптический распределительный (ОРШ) центральный — в здании ЦУ', 'шт',
         '1 на СНП (здание по проекту)', lambda v: 1, 'int'),
        ('Шкаф зонный ОРШ уличный (под сплиттеры 1:64)', 'шт',
         '1 на зону — в центре сектора (медиана зоны, зона ≥ 48 ДХ)', lambda v: v['n_zones'], 'int'),
        ('Сплиттер PLC 1×64 (в ОРШ: ЦУ и зонных)', 'шт',
         'ceil(ДХ зоны / 64), заполнение 75-100%', 'splitters', 'int'),
        ('Пигтейль SC/UPC для кросса ОРШ', 'шт',
         'ДХ + 2 × сплиттеры 1:64', 'pigtails', 'int'),
        ('Порт PON OLT — справочно (активное оборудование, единый узел OLT)', 'шт',
         'по числу сплиттеров 1:64', 'olt_ports', 'int'),
    ]),
    ('Б. Кабельная продукция (длины с запасом на монтаж 10 %)', [
        ('Кабель оптический самонесущий, 8 волокон', 'км',
         'распределение зоны max(8; 1,25 × ДХ потока) + фидер ceil(1,25 × сплиттеры зоны)', 'cable_8', 'km'),
        ('Кабель оптический самонесущий, 12 волокон', 'км', 'то же', 'cable_12', 'km'),
        ('Кабель оптический самонесущий, 16 волокон', 'км', 'то же', 'cable_16', 'km'),
        ('Кабель оптический самонесущий, 24 волокна', 'км', 'то же', 'cable_24', 'km'),
        ('Кабель оптический самонесущий, 32 волокна', 'км', 'то же', 'cable_32', 'km'),
        ('Кабель оптический самонесущий, 48 волокон', 'км', 'то же', 'cable_48', 'km'),
        ('Кабель оптический самонесущий, 64 волокна', 'км', 'то же', 'cable_64', 'km'),
        ('Кабель оптический самонесущий, 72 волокна', 'км', 'то же', 'cable_72', 'km'),
        ('Кабель оптический самонесущий, 96 волокон', 'км', 'то же', 'cable_96', 'km'),
        ('Кабель дроп-кабельный самонесущий, 2 волокна (1 раб. + 1 рез.)', 'км',
         'дропы × 1,05 (без подводок — дроп от муфты напрямую)', 'drop_cable_km', 'km'),
        ('Справочно: суммарная ёмкость магистрального кабеля', 'волокно-км',
         'Σ (длина участка × волокна)', 'fiber_km', 'km'),
    ]),
    ('В. Пассивные узлы', [
        ('Муфта оптическая (ветвления магистрали)', 'шт',
         'узлы ветвления кроме точек врезов зонных ОРШ; транзит — неразрезным кабелем', 'mufty', 'int'),
    ]),
    ('Г. Материалы для монтажа', [
        ('Бокс абонентский оптический с адаптером SC/UPC', 'шт', '1 на ДХ', 'abonent_boxes', 'int'),
        ('Коннектор оптический механический SC/UPC', 'шт', 'ДХ × 1,1 (абонентский бокс)', 'fast_conn', 'int'),
        ('Сварное соединение (оценка объёма работ)', 'шт',
         '(2 × ДХ + 2 × сплиттеры 1:64) × 1,1', 'splices', 'int'),
        ('Гильза КДЗС, 60 мм', 'шт', 'по числу сварных соединений', 'kdzs', 'int'),
        ('Комплект подвеса магистрального кабеля (кронштейн + спиральный зажим)', 'компл',
         '30 на 1 км кабеля', 'suspend_kits', 'int'),
        ('Анкерный зажим дроп-кабеля', 'шт', '2 на ДХ', 'drop_anchors', 'int'),
        ('Крепёж дроп-кабеля (скобы / хомуты)', 'шт', '6 на ДХ', 'drop_fix', 'int'),
    ]),
]

row = 5
num = 0
for sect_title, items in SECTIONS:
    ws.cell(row=row, column=3, value=sect_title)
    for c in range(2, LAST + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = sect_fill()
        cell.font = sect_font()
        cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[row].height = 24
    row += 1
    for idx, (name, unit, norma, mkey, kind) in enumerate(items):
        num += 1
        ws.cell(row=row, column=2, value=num)
        ws.cell(row=row, column=3, value=name)
        ws.cell(row=row, column=4, value=unit)
        ws.cell(row=row, column=5, value=norma)
        for vi, v in enumerate(V):
            m = dict(v['materials'])
            m['fiber_km'] = v['fiber_km']
            val = mkey(v) if callable(mkey) else m.get(mkey)
            if val in (0, 0.0):
                val = None
            ws.cell(row=row, column=6 + vi, value=val)
        ws.cell(row=row, column=LAST, value=f'=SUM(F{row}:K{row})')
        fill = base.fill_data_row(idx)
        for c in range(2, LAST + 1):
            cell = ws.cell(row=row, column=c)
            cell.fill = fill
            cell.font = base.font_body()
            if c == 2:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            elif c in (3, 5):
                cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            elif c == 4:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='right', vertical='center')
                cell.number_format = F_KM if kind == 'km' else F_INT
        ws.cell(row=row, column=LAST).font = base.font_subheader()
        ws.row_dimensions[row].height = 24
        row += 1

row += 1
notes = [
    'Значения в графах сел — потребность по проекту; графа «ИТОГО» — сумма по шести СНП. Единицы измерения разнородны, итог по столбцам не приводится.',
    'Схема D (уточнённая детекция ДХ, полная VLM-верификация): 28 зон + 6 ЦУ = 34 ОРШ; заполнение сплиттеров 1:64 — 75-100%; ср. волоконный маршрут ДХ 304 м (против 1361 м в централизованной). Карты зон ОРШ по всем СНП — download/snp_vko.',
    'Солнечное: зонные ОРШ не образуются (село компактное, экономия волокна ниже порога S_MIN) — вся нагрузка на ЦУ.',
]
for t in notes:
    ws.cell(row=row, column=2, value=t).font = cap_font()
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=LAST)
    ws.row_dimensions[row].height = 14
    row += 1

ws.freeze_panes = 'F5'
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.print_title_rows = '4:4'

# --- контроль сумм против JSON (v3) ---
mt = DBOOK['materials_total']
sums = {}
for vi, v in enumerate(V):
    for k, val in v['materials'].items():
        sums[k] = sums.get(k, 0) + val
sums['fiber_km'] = sum(v['fiber_km'] for v in V)
assert sums['splitters'] == mt['splitters'] == 58
assert sums['mufty'] == mt['mufty'] == 1112
assert abs(sums['drop_cable_km'] - mt['drop_cable_km']) < 0.05
assert abs(sums['fiber_km'] - DBOOK['totals']['fiber_km']) < 0.05
assert sum(1 for v in V) == 6 and sum(v['n_zones'] for v in V) == DBOOK['totals']['n_zones'] == 28

# ============================================================ МЕТОДИКА ======
ws4 = wb['Методика']
r9 = None
for rowm in range(5, ws4.max_row + 1):
    val = ws4.cell(row=rowm, column=3).value
    if isinstance(val, str) and val.startswith('9. Сводная материалов и карты'):
        r9 = rowm
        break
if r9 is not None and ws4.max_row >= r9:
    ws4.delete_rows(r9, ws4.max_row - r9 + 1)

n_max = 0
for rowm in range(5, ws4.max_row + 1):
    val = ws4.cell(row=rowm, column=2).value
    if isinstance(val, (int, float)):
        n_max = max(n_max, int(val))

r4 = ws4.max_row + 1
ws4.cell(row=r4, column=3, value='9. Сводная материалов и карты зон схемы D')
for c in range(2, 5):
    cell = ws4.cell(row=r4, column=c)
    cell.fill = sect_fill()
    cell.font = sect_font()
    cell.alignment = Alignment(horizontal='left', vertical='center')
ws4.row_dimensions[r4].height = 24
r4 += 1

M9 = [
    ('Состав позиций',
     'Лист «Сводная (схема D)» повторяет формат сводной схемы C: 4 секции, 24 позиции, графы шести СНП и ИТОГО (формулы SUM). '
     'Отличия от каскадной схемы: нет РОР и сплиттеров 2-й ступени; добавлены зонные уличные шкафы (26 шт.) отдельной позицией; '
     'дроп-кабель без подводок РОР→ДХ (95,8 км — как в централизованной, дроп идёт от муфты напрямую); коннекторы 1,1 × ДХ.'),
    ('Нормы схемы D',
     'Волокна участка = распределительные max(8; ceil(1,25 × ДХ потока зоны)) от ОРШ-медианы + фидерные ceil(1,25 × сплиттеры зоны) '
     'на кратчайшем пути ЦУ → зонный ОРШ (Дейкстра в границе НП); разложение 8-96 волокон. Сварки = (2 × ДХ + 2 × сплиттеры 1:64) × 1,1; пигтейли = ДХ + 2 × сплиттеры; '
     'подвесы 30/км магистрали. Ёмкости и длины кабелей — из расчёта топологии v4 (boq_decentral_data_v4.json: уточнённая детекция ДХ — сблокированные дома по крышам/заборам, квартиры многоэтажек), '
     'инварианты к схемам A/B/C по ДХ, дропам и трассе соблюдены.'),
    ('Карты зон ОРШ',
     'Шесть карт download/snp_vko/<NN>_<СНП>_зоны_ОРШ_схема_D.jpg (спутник Google z18): цветная зона каждого ОРШ — оболочка '
     'обслуживаемых ДХ; ствол сети — серым; распределительная сеть зоны — цветом зоны; фидер ЦУ → зонный ОРШ — пунктиром цвета '
     'зоны по кратчайшей трассе; граница НП — белым пунктиром; дропы — жёлтым; муфты — бирюзовые квадраты; зонные ОРШ — цветные '
     'шкафы в центрах секторов с подписью «ОРШ-N, N ДХ»; ЦУ — красная звезда. '
     'Совмещение сети со спутником проверено (NCC 0 px, визуальный контроль).'),
]
n9 = n_max
for name, desc in M9:
    n9 += 1
    ws4.cell(row=r4, column=2, value=n9)
    ws4.cell(row=r4, column=3, value=name)
    ws4.cell(row=r4, column=4, value=desc)
    fill = base.fill_data_row(n9)
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
print(f'Лист «Сводная (схема D)»: 24 позиции, ИТОГО формулами SUM; контроль сумм с JSON пройден')
print(f'Методика: секция 9 добавлена, пункты {n_max + 1}-{n9}')
