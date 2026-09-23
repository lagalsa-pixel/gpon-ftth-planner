#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сводная Excel-таблица по проектированию FTTH (Лоты 12, СНП ВКО)."""
import json, math, os, sys

XLSX_SKILL_DIR = "/home/z/my-project/skills/xlsx"
for sub in [XLSX_SKILL_DIR, os.path.join(XLSX_SKILL_DIR, "templates")]:
    if sub not in sys.path:
        sys.path.insert(0, sub)

import base
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

WORK = '/home/z/my-project/work'
OUT = '/home/z/my-project/download/snp_vko/00_Сводка_FTTH_Лоты12.xlsx'

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)
NETS = {s['name']: json.load(open(f'{WORK}/net/{s["name"]}.json')) for s in SNPS}

wb = Workbook()
wb.properties.creator = "Z.ai"

# ============ Лист 1: Сводка ============
ws = wb.active
ws.title = "Сводка"

headers = ['№', 'Населённый пункт', 'Район', 'Сельский округ', 'КАТО',
           'ДХ по лоту', 'ДХ определено', 'Покрытие, %', 'Объекты*',
           'Сеть, км', 'Муфт разветв.', 'Муфт терм.', 'Муфт всего',
           'Дропов, шт', 'Дропы, км', 'Ср. дроп, м', 'Макс дроп, м', 'PON-портов 1:32']
LAST = len(headers) + 1  # последний столбец (B-индексация)

base.setup_sheet(ws, title='Проектирование FTTH (GPON) — сельские населённые пункты ВКО, «Лоты 12»', last_col=LAST)

for ci, h in enumerate(headers, 2):
    ws.cell(row=4, column=ci, value=h)
base.style_header_row(ws, 4, 2, LAST)

r = 5
for i, s in enumerate(SNPS, 1):
    st = NETS[s['name']]['stats']
    orsh = NETS[s['name']]['orsh']
    vals = [i, s['name'], s['district'] or 'г. Риддер', s['okrug'] or '—', str(s['kato']),
            s['households'], st['households'], None, st['objects'],
            round(st['tree_len_m'] / 1000, 2), st['muftas_branch'], st['muftas_terminal'], None,
            st['drops_n'], round(st['drops_total_m'] / 1000, 2), st['drop_avg_m'], st['drop_max_m'],
            st['pon_ports']]
    for ci, v in enumerate(vals, 2):
        ws.cell(row=r, column=ci, value=v)
    # формулы: покрытие, муфт всего
    ws.cell(row=r, column=9).value = f"=IFERROR(ROUND(H{r}/G{r}*100,1),0)"
    ws.cell(row=r, column=14).value = f"=L{r}+M{r}"
    base.style_data_row(ws, r, 2, LAST, r - 5)
    r += 1

# итоговая строка
tr = r
ws.cell(row=tr, column=2, value='ИТОГО')
ws.cell(row=tr, column=3, value='6 СНП')
for ci, letter in [(7, 'G'), (8, 'H'), (10, 'J'), (11, 'K'), (12, 'L'), (13, 'M'), (14, 'N'),
                   (15, 'O'), (16, 'P'), (19, 'S')]:
    ws.cell(row=tr, column=ci).value = f"=SUM({letter}5:{letter}{tr-1})"
ws.cell(row=tr, column=17).value = f"=IFERROR(ROUND(P{tr}/O{tr},0),0)"
ws.cell(row=tr, column=18).value = f"=MAX(R5:R{tr-1})"
base.style_total_row(ws, tr, 2, LAST)

# числовые форматы
for row in range(5, tr + 1):
    for ci, fmt in [(2, '0'), (7, '0'), (8, '0'), (9, '0.0'), (10, '0'), (11, '0.00'),
                    (12, '0'), (13, '0'), (14, '0'), (15, '0'), (16, '0.00'),
                    (17, '0'), (18, '0'), (19, '0')]:
        ws.cell(row=row, column=ci).number_format = fmt

widths = {2: 4, 3: 20, 4: 16, 5: 20, 6: 12, 7: 10, 8: 12, 9: 11, 10: 9, 11: 12, 12: 11,
          13: 11, 14: 11, 15: 10, 16: 10, 17: 11, 18: 12, 19: 13}
for ci, w in widths.items():
    ws.column_dimensions[get_column_letter(ci)].width = w
ws.freeze_panes = 'D5'
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0

note_r = tr + 2
ws.cell(row=note_r, column=2,
        value='* Объекты — школы, администрации и иные нежилые здания, учтённые как абоненты сети. '
              'Дропы рассчитаны с коэффициентом запаса 1,2 (подъём по стене, обход препятствий).')
ws.cell(row=note_r, column=2).font = base.font_caption()
ws.merge_cells(start_row=note_r, start_column=2, end_row=note_r, end_column=LAST)

# ============ Лист 2: Волоконность ============
ws2 = wb.create_sheet('Волоконность')
FIBS = ['8', '12', '16', '24', '32', '48', '64', '72', '96', '144', '192']
headers2 = ['Населённый пункт'] + [f'{f} вол.' for f in FIBS] + ['Итого, км']
LAST2 = len(headers2) + 1
base.setup_sheet(ws2, title='Протяжённость распределительной сети по ёмкости кабеля (км)', last_col=LAST2)
for ci, h in enumerate(headers2, 2):
    ws2.cell(row=4, column=ci, value=h)
base.style_header_row(ws2, 4, 2, LAST2)

r = 5
for s in SNPS:
    fk = NETS[s['name']]['stats'].get('fiber_km', {})
    ws2.cell(row=r, column=2, value=s['name'])
    for ci, f in enumerate(FIBS, 3):
        ws2.cell(row=r, column=ci, value=fk.get(f, 0))
    ws2.cell(row=r, column=len(FIBS) + 3).value = f"=ROUND(SUM(C{r}:M{r}),2)"
    base.style_data_row(ws2, r, 2, LAST2, r - 5)
    for ci in range(3, LAST2 + 1):
        ws2.cell(row=r, column=ci).number_format = '0.00'
    r += 1
tr2 = r
ws2.cell(row=tr2, column=2, value='ИТОГО')
for ci in range(3, LAST2 + 1):
    letter = get_column_letter(ci)
    ws2.cell(row=tr2, column=ci).value = f"=ROUND(SUM({letter}5:{letter}{tr2-1}),2)"
    ws2.cell(row=tr2, column=ci).number_format = '0.00'
base.style_total_row(ws2, tr2, 2, LAST2)
ws2.column_dimensions['B'].width = 20
for ci in range(3, LAST2 + 1):
    ws2.column_dimensions[get_column_letter(ci)].width = 9
ws2.freeze_panes = 'C5'

# ============ Лист 3: Методика и примечания ============
ws3 = wb.create_sheet('Методика')
base.setup_sheet(ws3, title='Методика проектирования и примечания', last_col=8)
notes = [
    ('Архитектура', 'Централизованная древовидная топология: один ОРШ на населённый пункт, '
     'от него по улично-дорожной сети расходится дерево распределительных кабелей; '
     'в каждом узле разветвления установлена муфта, на концах ветвей — терминальные муфты, '
     'от которых дроп-кабели заведены в домохозяйства. Выносные РОР не применяются: '
     'все оптические сплиттеры (1:32) централизованы в ОРШ.'),
    ('Размещение ОРШ', 'Геометрическая медиана домохозяйств (алгоритм Вейцфельда) с привязкой '
     'к ближайшей улице — точка, минимизирующая суммарную длину кабельной сети.'),
    ('Трассы кабеля', 'Прокладка по фактической улично-дорожной сети (данные OpenStreetMap); '
     'минимальное остовное дерево терминалов в метрике графа (алгоритм Дейкстры + Прима); '
     'бесполезные листья отсечены. Кратчайшие трассы дропов: каждый дом подключён '
     'к ближайшей терминальной муфте (группировка дропов ≤ 70 м).'),
    ('Домохозяйства', 'Определены по космоснимкам высокого разрешения (Google, z18, ~0,38 м/px) '
     'с использованием эталонной разметки зданий OSM и автоматической детекции неразмеченных крыш; '
     'многоквартирные дома учтены числом квартир. Отдельно стоящие усадьбы (фермы) '
     'в 500 м и далее от ближайшего соседа в расчёт сети не включены.'),
    ('Сопоставление с лотом', 'Верхнеберезовка 100%, Солнечное 97%, Перевальное 99%, Винное 109%, '
     'Пригородное 125% (в границы включена часть пригородной застройки), Алтайский 48% — '
     'на снимке заметно меньше строений, чем заявлено домохозяйств по лоту (716); '
     'вероятно, расхождение объясняется учётом квартир в многоквартирном фонде и выбытием застройки.'),
    ('Источник данных лота', 'СНП ВКО.xlsx, лист «Лоты 12»: 6 СНП, 3216 домохозяйств.'),
]
r = 4
for k, v in notes:
    ws3.cell(row=r, column=2, value=k).font = base.font_subheader()
    c = ws3.cell(row=r + 1, column=2, value=v)
    c.font = base.font_body()
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws3.merge_cells(start_row=r + 1, start_column=2, end_row=r + 1, end_column=8)
    ws3.row_dimensions[r + 1].height = 58
    r += 3
ws3.column_dimensions['B'].width = 26
for ci in range(3, 9):
    ws3.column_dimensions[get_column_letter(ci)].width = 18

wb.save(OUT)
print("Сохранено:", OUT)
