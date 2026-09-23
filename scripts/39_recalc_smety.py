# -*- coding: utf-8 -*-
"""
Шаг 39. Пересчёт локальных смет (НДЦС РК 8.01-08-2022, Форма 4) под новые
объёмы кабелей проекта FTTH ВКО — схема D (зонные ОРШ, сплиттеры 1:64,
единый узел OLT; объёмы идентичны централизованной схеме A).

ИСХОДНЫЕ СМЕТЫ (upload/Сметы на прокладку кабелей.7z -> work/smety/extracted):
объёмы заложены по грубой прикидке на все ДХ по статистике СНП (3216),
дроп 72-91 м/ДХ. Наш проект (спутниковая геометрия, 2334 обслуживаемых ДХ,
сводная FTTH ВКО, схема D) даёт уточнённые объёмы.

ПРАВИЛА ПЕРЕСЧЁТА (расценки, коды ССЦ/ЭСН, единичные цены F — БЕЗ ИЗМЕНЕНИЙ):
  поз.1 Дроп-кабель (243-503-0402):        E = drop_cable_km x 1000 (закупка)
  поз.2 Подвешивание дропа (1310-0902-1003 #1): E = drop_km x 1000 (физика);
        под-позиции (чел-ч, маш-ч, канат, зажим, подвес) масштабируются k=E/E0
  Кабельные позиции ССЦ (замена объёмов по ёмкости, вверх до доступной):
        наши 8 вол  -> А8   (274-303-0902-0057, 249 тг/м)
        наши 12     -> А12  (274-303-0902-0058, 288)
        наши 16, 24 -> ОКА-А24 (274-305-0103-0029, 423)
        наши 32, 48, 64, 72, 96 -> ОКА-А48 (274-305-0103-0032, 566)
        позиция А4 (274-303-0902-0054) в схеме D не применяется -> удаляется
  поз.N Подвешивание магистрали (1310-0902-1003 #2): E = total_cable_km x 1000
  Муфты и их монтаж: БЕЗ ИЗМЕНЕНИЙ (объёмы зависят от схемы ветвлений
        исходной сметы, а не от длин кабелей)
Итоги (ВСЕГО, труд/машины/материалы, трудоёмкость, шапка) пересчитываются.
Ведомость материалов согласуется с позициями сметы.

Выход: download/Сметы_прокладка_схема_D/ЛС_*.xlsx (6 файлов)
       + в каждом файле лист «Пересчёт (схема D)» с методикой и было/стало.
Запуск: python3 39_recalc_smety.py
"""
import copy
import json
import os
import re
import shutil

import openpyxl
from openpyxl.utils import get_column_letter

BASE = '/home/z/my-project'
SRC = f'{BASE}/work/smety/extracted'
OUT = f'{BASE}/download/Сметы_прокладка_схема_D'

# --------------------------------------------------------------- данные ----
DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}

FILES = {  # файл сметы -> ключ BoQ
    'ЛС_Алтайский_716.xlsx': 'altaiskiy',
    'ЛС_Верхнеберезовское_940.xlsx': 'verhneberezovka',
    'ЛС_Винное_490.xlsx': 'vinnoe',
    'ЛС_Перевально_339.xlsx': 'perevalnoe',
    'ЛС_Пригородное_365.xlsx': 'prigorodnoe',
    'ЛС_Солнечное_366.xlsx': 'solnechnoe',
}

CODE_DROP = '243-503-0402'
CODE_SUSP = '1310-0902-1003'
CODE_A4 = '274-303-0902-0054'
CODE_A8 = '274-303-0902-0057'
CODE_A12 = '274-303-0902-0058'
CODE_OKA24 = '274-305-0103-0029'
CODE_OKA48 = '274-305-0103-0032'

NAME_OKA48 = ('Кабель оптический подвесной самонесущий, Кабель оптический '
              'подвесной самонесущий, растягивающее усилие 7.0 кН типа '
              'ОКА-М4П-А48-7.0, количество оптических волокон 48, допустимое')
B_OKA48 = '274-305-0103-0032 \nССЦ РК 8.04-08-2025'


def volumes(key):
    """Новые объёмы (м) по схеме D."""
    v = DBY[key]
    m = v['materials']
    return {
        'drop_mat': round(m['drop_cable_km'] * 1000, 2),      # закупка дропа
        'drop_work': round(v['drop_km'] * 1000, 2),           # физика дропов
        'c8': round(m['cable_8'] * 1000, 2),
        'c12': round(m['cable_12'] * 1000, 2),
        'c24': round((m['cable_16'] + m['cable_24']) * 1000, 2),
        'c48': round((m['cable_32'] + m['cable_48'] + m['cable_64']
                      + m['cable_72'] + m['cable_96']) * 1000, 2),
        'mag_work': round(v['total_cable_km'] * 1000, 2),     # физика магистрали
    }


# ------------------------------------------------------------ разбор -------
def code_of(bval):
    if not bval:
        return None
    return str(bval).split('\n')[0].strip()


def parse_positions(ws, first_row=22):
    """Позиции верхнего уровня (A=int) с их строками-блоками.
    В блок попадают ВСЕ строки до следующей позиции — включая строки
    без номера A («в том числе оплата…», «в т.ч. машинисты…»)."""
    tops = []          # [{row, a, code, e, f, g, block:[rows]}]
    cur = None
    for row in ws.iter_rows(min_row=first_row, max_row=ws.max_row):
        a, b, c = row[0].value, row[1].value, row[2].value
        r = row[0].row
        if a is not None and isinstance(a, int) and c is not None:
            cur = {'row': r, 'a': a, 'code': code_of(b), 'c': str(c),
                   'e': row[4].value, 'f': row[5].value, 'g': row[6].value,
                   'block': []}
            tops.append(cur)
        elif cur is not None and r > cur['row']:
            cur['block'].append(r)
    return tops


def cell(ws, r, c):
    return ws.cell(r, c)


# ------------------------------------------------- операции со строками ----
def shift_merged(ws, ops):
    """ops = [(row, +1/-1)] — УЖЕ применённые вставки/удаления строк.
    Прямая правка границ merged ranges (unmerge после delete_rows
    ломается на сдвинутых MergedCell)."""
    for rng in list(ws.merged_cells.ranges):
        r0, r1 = rng.min_row, rng.max_row
        d0 = sum(d for p, d in ops if (d > 0 and p <= r0) or (d < 0 and p < r0))
        d1 = sum(d for p, d in ops if (d > 0 and p <= r1) or (d < 0 and p < r1))
        if d0 or d1:
            rng.min_row = r0 + d0
            rng.max_row = r1 + d1


def copy_row_style(ws, src, dst, ncols=7):
    ws.row_dimensions[dst].height = ws.row_dimensions[src].height
    for c in range(1, ncols + 1):
        s, d = ws.cell(src, c), ws.cell(dst, c)
        d.font = copy.copy(s.font)
        d.fill = copy.copy(s.fill)
        d.border = copy.copy(s.border)
        d.alignment = copy.copy(s.alignment)
        d.number_format = s.number_format


def recalc_block(ws, pos, new_e):
    """Блок расценки подвешивания: E позиция -> new_e; под-строки линейно."""
    k = new_e / pos['e']
    pos['e_new'] = new_e
    cell(ws, pos['row'], 5).value = round(new_e, 2)
    cell(ws, pos['row'], 7).value = round(pos['f'] * new_e)
    for r in pos['block']:
        e = cell(ws, r, 5).value
        f = cell(ws, r, 6).value
        if isinstance(e, (int, float)):
            e2 = e * k
            cell(ws, r, 5).value = round(e2, 4)
            if isinstance(f, (int, float)):
                cell(ws, r, 7).value = round(f * e2)
        elif e is None and isinstance(f, (int, float)):
            cell(ws, r, 7).value = round(f * new_e)


def set_material(ws, pos, new_e):
    """Материальная позиция: E, G=F*E."""
    pos['e_new'] = new_e
    cell(ws, pos['row'], 5).value = round(new_e, 2)
    cell(ws, pos['row'], 7).value = round(pos['f'] * new_e)


def block_materials(ws, pos):
    """Суммарные материалы (канат/зажим/подвес) блока расценки — словарь."""
    out = {}
    for r in pos['block']:
        c = str(cell(ws, r, 3).value or '')
        e = cell(ws, r, 5).value
        if isinstance(e, (int, float)) and cell(ws, r, 4).value in ('м', 'кг', 'т'):
            out[c[:24]] = e
    return out


# ------------------------------------------------------------ смета --------
def recalc_smeta(ws, vol, report):
    tops = parse_positions(ws)
    susp = [p for p in tops if p['code'] == CODE_SUSP]
    assert len(susp) == 2, f'ожидалось 2 расценки подвешивания, найдено {len(susp)}'
    p_drop_mat = next(p for p in tops if p['code'] == CODE_DROP)
    p_susp_drop, p_susp_mag = susp[0], susp[1]
    p_a4 = next((p for p in tops if p['code'] == CODE_A4), None)
    p_a8 = next(p for p in tops if p['code'] == CODE_A8)
    p_a12 = next(p for p in tops if p['code'] == CODE_A12)
    p_oka24 = next(p for p in tops if p['code'] == CODE_OKA24)
    p_oka48 = next((p for p in tops if p['code'] == CODE_OKA48), None)

    # --- объёмы (сначала ОБЕ расценки и их материалы — до возможной
    #     вставки ОКА-А48, которая сдвигает строки ниже) ---
    set_material(ws, p_drop_mat, vol['drop_mat'])
    recalc_block(ws, p_susp_drop, vol['drop_work'])
    recalc_block(ws, p_susp_mag, vol['mag_work'])
    mat_drop = block_materials(ws, p_susp_drop)
    mat_mag = block_materials(ws, p_susp_mag)

    set_material(ws, p_a8, vol['c8'])
    set_material(ws, p_a12, vol['c12'])
    set_material(ws, p_oka24, vol['c24'])
    if p_oka48 is None:
        p_oka48 = insert_oka48(ws, p_oka24['row'])
    set_material(ws, p_oka48, vol['c48'])

    # --- удаление А4 ---
    del_row = p_a4['row'] if p_a4 else None

    report['rows'] = [
        ('Дроп-кабель, м', p_drop_mat['e'], vol['drop_mat']),
        ('Подвешивание дроп-кабеля, м', p_susp_drop['e'], vol['drop_work']),
        ('Кабель ОК/Т-Т-А4 (4 вол.), м', p_a4['e'] if p_a4 else 0, 0),
        ('Кабель ОК/Т-Т-А8 (8 вол.), м', p_a8['e'], vol['c8']),
        ('Кабель ОК/Т-Т-А12 (12 вол.), м', p_a12['e'], vol['c12']),
        ('Кабель ОКА-М4П-А24 (24 вол.), м', p_oka24['e'], vol['c24']),
        ('Кабель ОКА-М4П-А48 (48 вол.), м',
         p_oka48['e'] if p_oka48['e'] else 0, vol['c48']),
        ('Подвешивание магистр. кабеля, м', p_susp_mag['e'], vol['mag_work']),
    ]
    report['del_row'] = del_row
    report['insert_row'] = None if p_oka48 is None else p_oka48.get('inserted')
    report['old_total'] = cell(ws, 22, 7).value
    return del_row, mat_drop, mat_mag


def insert_oka48(ws, after_row):
    """Вставка позиции ОКА-А48 после строки ОКА-А24 (в сметах, где её нет)."""
    ins = after_row + 2          # после тонкого разделителя
    ws.insert_rows(ins, 1)
    shift_merged(ws, [(ins, +1)])
    copy_row_style(ws, after_row, ins)
    cell(ws, ins, 1).value = 99          # временный номер — renumber перенумерует
    cell(ws, ins, 2).value = B_OKA48
    cell(ws, ins, 3).value = NAME_OKA48
    cell(ws, ins, 4).value = 'м'
    cell(ws, ins, 5).value = 0
    cell(ws, ins, 6).value = 566
    cell(ws, ins, 7).value = 0
    return {'row': ins, 'code': CODE_OKA48, 'e': 0, 'f': 566, 'g': 0,
            'block': [], 'inserted': ins}


# ------------------------------------------------------------- итоги -------
def recalc_totals(ws):
    """Пересчёт итогов сметы и шапки (строки 22-29, 15-17)."""
    g24 = g25 = g26 = g27 = g28 = 0.0
    ch = 0.0
    tops = set()
    for row in ws.iter_rows(min_row=30, max_row=ws.max_row):
        a, c, d = row[0].value, str(row[2].value or ''), row[3].value
        e, f, g = row[4].value, row[5].value, row[6].value
        r = row[0].row
        if isinstance(a, int) and c:
            tops.add(g or 0)
        if c.startswith('затраты на труд рабочих') and r > 30:
            g24 += g or 0
        elif c.startswith('в том числе оплата труда рабочих') and r > 30:
            g25 += g or 0
        elif c.startswith('машины и механизмы') and r > 30:
            g26 += g or 0
        elif c.startswith('в том числе оплата труда машинистов') and r > 30:
            g27 += g or 0
        elif c.startswith('материалы, изделия') and r > 30:
            g28 += g or 0
        if d == 'чел.-ч' and isinstance(e, (int, float)):
            ch += e
    total = round(sum(tops))
    old_f16 = ws['F16'].value
    old_opl = ws['G25'].value + ws['G27'].value
    ws['G22'].value = total
    ws['G24'].value = round(g24)
    ws['G25'].value = round(g25)
    ws['G26'].value = round(g26)
    ws['G27'].value = round(g27)
    ws['G28'].value = round(g28)
    ws['E29'].value = round(ch)
    ws['F15'].value = round(total / 1000, 3)
    ws['F16'].value = round(old_f16 * (g25 + g27) / old_opl, 1) if old_opl else old_f16
    ws['F17'].value = round(ch / 1000, 3)
    return total


# --------------------------------------------------------- ведомость -------
def recalc_vedomost(ws, vol, mat_drop, mat_mag, kanat_key='Канат стальной двойной'):
    """Обновление ведомости: дроп, кабели, канат, зажим, подвес; А4 удалить."""
    # суммы материалов из блоков расценок (уже пересчитаны)
    def find(pred):
        out = []
        for row in ws.iter_rows(min_row=10, max_row=ws.max_row):
            if row[0].value is None:
                continue
            if pred(row):
                out.append(row[0].row)
        return out

    def bycode(code):
        return find(lambda r: code_of(r[1].value) == code
                    and str(r[0].value).isdigit())

    del_row = None
    for code, new_e in ((CODE_DROP, vol['drop_mat']), (CODE_A8, vol['c8']),
                        (CODE_A12, vol['c12']), (CODE_OKA24, vol['c24']),
                        (CODE_OKA48, vol['c48'])):
        rows = bycode(code)
        if not rows and code == CODE_OKA48:
            r24 = bycode(CODE_OKA24)[0]
            ws.insert_rows(r24 + 1, 1)
            shift_merged(ws, [(r24 + 1, +1)])
            copy_row_style(ws, r24, r24 + 1)
            cell(ws, r24 + 1, 1).value = 99   # временный номер для renumber
            cell(ws, r24 + 1, 2).value = B_OKA48
            cell(ws, r24 + 1, 3).value = NAME_OKA48
            cell(ws, r24 + 1, 4).value = 'м'
            cell(ws, r24 + 1, 5).value = round(new_e, 2)
            cell(ws, r24 + 1, 6).value = 566
            cell(ws, r24 + 1, 7).value = round(566 * new_e)
            continue
        for r in rows:
            f = cell(ws, r, 6).value
            cell(ws, r, 5).value = round(new_e, 2)
            cell(ws, r, 7).value = round(f * new_e)

    a4 = bycode(CODE_A4)
    if a4:
        del_row = a4[0]

    # канат, зажим, подвес: суммы из пересчитанных блоков
    if mat_drop or mat_mag:
        keys = {}
        for src in (mat_drop, mat_mag):
            for name, e in src.items():
                keys[name] = keys.get(name, 0) + e
        for row in ws.iter_rows(min_row=10, max_row=ws.max_row):
            c = str(row[2].value or '')
            for name, e in keys.items():
                if c.startswith(name):
                    f = row[5].value
                    row[4].value = round(e, 4)
                    row[6].value = round(f * e)
    return del_row


def redo_vedomost_totals(ws):
    total = 0
    for row in ws.iter_rows(min_row=10, max_row=ws.max_row):
        a = row[0].value
        if isinstance(a, int) and isinstance(row[6].value, (int, float)):
            total += row[6].value
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        c = str(row[2].value or '')
        if c.startswith('Итого материальные ресурсы') or c.startswith('Всего по ведомости'):
            row[6].value = round(total)
    return total


# ---------------------------------------------------- перенумерация --------
def renumber(ws, first_row=22):
    """Перенумерация позиций верхнего уровня и под-позиций после удаления."""
    n = 0
    for row in ws.iter_rows(min_row=first_row, max_row=ws.max_row):
        a = row[0].value
        c = row[2].value
        if a is None or c is None:
            continue
        if isinstance(a, int):
            n += 1
            if a != n:
                row[0].value = n
        elif isinstance(a, str) and re.fullmatch(r'\d+(\.\d+)+', a):
            pref = a.split('.')[0]
            if int(pref) != n and n > 0:
                row[0].value = re.sub(r'^\d+', str(n), a)


# ------------------------------------------------------ лист Пересчёт ------
def add_recalc_sheet(wb, key, report, new_total):
    v = DBY[key]
    if 'Пересчёт (схема D)' in wb.sheetnames:
        del wb['Пересчёт (схема D)']
    ws = wb.create_sheet('Пересчёт (схема D)')
    ws.sheet_view.showGridLines = False
    for col, w in zip('ABCDEFG', (46, 16, 16, 14, 14, 14, 14)):
        ws.column_dimensions[col].width = w

    bold = openpyxl.styles.Font(bold=True, size=11)
    title = openpyxl.styles.Font(bold=True, size=14)
    small = openpyxl.styles.Font(size=9, italic=True, color='555555')
    fill = openpyxl.styles.PatternFill('solid', fgColor='E8EEF7')
    fill2 = openpyxl.styles.PatternFill('solid', fgColor='F5F8FC')
    border = openpyxl.styles.Border(
        bottom=openpyxl.styles.Side(style='thin', color='BBBBBB'))

    ws['A1'] = ('Пересчёт локальной сметы под объёмы проекта FTTH — '
                'схема D (зонные ОРШ, сплиттеры 1:64, единый узел OLT)')
    ws['A1'].font = title
    ws['A2'] = (f"Объект: с. {v['name']} · {v['raion']} · "
                f"обслуживаемых ДХ: {v['dhx_served']} из {v['dhx_excel']} по СНП")
    ws['A2'].font = small
    ws['A3'] = ('Источник объёмов: сводная таблица материалов FTTH ВКО '
                '(сеть по спутниковой подложке; длины по фактической '
                'геометрии трасс). Расценки, коды ССЦ/ЭСН и единичные '
                'цены — без изменений.')
    ws['A3'].font = small

    r = 5
    ws.cell(r, 1).value = 'Позиции сметы (объёмы)'
    ws.cell(r, 1).font = bold
    for j, h in enumerate(('Позиция', 'Было, м', 'Стало, м', 'Δ, %'), start=1):
        cc = ws.cell(r + 1, j)
        cc.value = h
        cc.font = bold
        cc.fill = fill
        cc.border = border
    r += 2
    for name, old, new in report['rows']:
        ws.cell(r, 1).value = name
        ws.cell(r, 2).value = round(old, 1) if old else 0
        ws.cell(r, 3).value = round(new, 1)
        d = (new / old - 1) * 100 if old else None
        ws.cell(r, 4).value = f'{d:+.0f}%' if d is not None and abs(d) < 1e9 else '—'
        for j in range(1, 5):
            ws.cell(r, j).border = border
            if r % 2 == 0:
                ws.cell(r, j).fill = fill2
        r += 1
    r += 1
    ws.cell(r, 1).value = 'Сметная стоимость (ВСЕГО по смете)'
    ws.cell(r, 1).font = bold
    ws.cell(r, 2).value = report['old_total']
    ws.cell(r, 3).value = new_total
    ws.cell(r, 4).value = f'{(new_total / report["old_total"] - 1) * 100:+.0f}%'
    ws.cell(r, 2).number_format = '# ##0'
    ws.cell(r, 3).number_format = '# ##0'
    for j in range(1, 5):
        ws.cell(r, j).font = bold
        ws.cell(r, j).fill = fill
    r += 3
    notes = (
        'Правила пересчёта:',
        '1. Дроп-кабель (поз.1) — закупочная длина по сводной (запас ~5%); '
        'подвешивание (расценка 1310-0902-1003, блок 1) — физическая длина '
        'дроп-линий.',
        '2. Подвешивание магистральных кабелей (блок 2) — физическая длина '
        'магистральных трасс; нормы расхода ресурсов расценки (чел.-ч, маш.-ч, '
        'канат, зажимы, подвесы) пересчитаны пропорционально объёму.',
        '3. Кабели по ёмкости волокон (сводная схема D -> позиции ССЦ '
        'исходной сметы): 8 вол. -> ОК/Т-Т-А8; 12 -> А12; 16 и 24 -> '
        'ОКА-М4П-А24; 32, 48, 64, 72, 96 -> ОКА-М4П-А48 (ближайшая большая '
        'ёмкость среди позиций исходной сметы).',
        '4. Кабель ОК/Т-Т-А4 (4 вол.) в схеме D не применяется — позиция '
        'удалена.',
        '5. Муфты волоконно-оптические и работы по их монтажу — без '
        'изменений (объёмы определяются схемой ветвлений исходной сметы, '
        'а не длинами кабелей).',
        '6. Показатель «Средства на оплату труда» пересчитан пропорционально '
        'фонду оплаты труда расценок.',
        '7. Итоги (ВСЕГО по смете, затраты на труд, машины и механизмы, '
        'материалы, нормативная трудоёмкость) пересчитаны по позициям.',
    )
    for t in notes:
        ws.cell(r, 1).value = t
        ws.cell(r, 1).font = bold if t.endswith(':') else openpyxl.styles.Font(size=10)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        ws.cell(r, 1).alignment = openpyxl.styles.Alignment(
            wrap_text=True, vertical='top')
        ws.row_dimensions[r].height = 30 if len(t) > 90 else 15
        r += 1


# ------------------------------------------------------------- main --------
def process(fname, key):
    vol = volumes(key)
    report = {}
    wb = openpyxl.load_workbook(f'{SRC}/{fname}')
    ws = wb['Смета']
    del_row, mat_drop, mat_mag = recalc_smeta(ws, vol, report)

    wsv = wb['ведомость']
    del_row_v = recalc_vedomost(wsv, vol, mat_drop, mat_mag)
    redo_vedomost_totals(wsv)

    # удаление позиции А4 (смета + ведомость) со сдвигом merged
    ops_s, ops_v = [], []
    if del_row:
        ws.delete_rows(del_row, 1)
        ops_s.append((del_row, -1))
        shift_merged(ws, ops_s)
    if del_row_v:
        wsv.delete_rows(del_row_v, 1)
        ops_v.append((del_row_v, -1))
        shift_merged(wsv, ops_v)

    renumber(ws, first_row=22)
    renumber(wsv, first_row=10)

    total = recalc_totals(ws)
    add_recalc_sheet(wb, key, report, total)

    os.makedirs(OUT, exist_ok=True)
    out_path = f'{OUT}/{fname}'
    wb.save(out_path)
    return total, report, out_path


def main():
    summary = []
    grand_old = grand_new = 0
    for fname, key in FILES.items():
        total, report, out = process(fname, key)
        v = DBY[key]
        old = report['old_total']
        summary.append((v['num'], v['name'], old, total, out))
        grand_old += old
        grand_new += total
        print(f"{v['num']} {v['name']:<20s} {old/1e6:>8.2f} -> {total/1e6:>8.2f} "
              f"млн тг ({total/old - 1:+.1%})", flush=True)
    print(f'\nИТОГО: {grand_old/1e6:.2f} -> {grand_new/1e6:.2f} млн тг '
          f'({grand_new/grand_old - 1:+.1%})')
    print('Выход:', OUT)
    json.dump({'villages': [{'num': n, 'name': nm, 'old': o, 'new': t}
                            for n, nm, o, t, _ in summary],
               'grand_old': grand_old, 'grand_new': grand_new},
              open(f'{BASE}/work/smety_recalc_summary.json', 'w'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
