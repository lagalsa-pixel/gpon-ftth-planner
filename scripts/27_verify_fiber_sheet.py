# -*- coding: utf-8 -*-
"""
Шаг 27. Семантическая проверка листа «Проверка волокно-км» (после QA-пайплайна).

Сверяет значения листа (включая кэш recalc для формул) с источниками:
  - work/boq_data.json            — книга (централизованная схема);
  - work/centralized_recheck.json — независимый пересчёт + индекс стоимости;
  - work/boq_cascade_data.json / boq_cascade16_data.json — каскады (волокно-км).

Проверяет: блоки А/Б/В/Г1/Г2, график, порядок листов, пункты «Методики» 26-30,
неизменность остальных листов (спот-чек «Сводной»).
"""
import json
from openpyxl import load_workbook

BASE = '/home/z/my-project'
OUT = f'{BASE}/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx'

RC = json.load(open(f'{BASE}/work/centralized_recheck.json', encoding='utf-8'))
BOOK = json.load(open(f'{BASE}/work/boq_data.json', encoding='utf-8'))
C88 = json.load(open(f'{BASE}/work/boq_cascade_data.json', encoding='utf-8'))
C416 = json.load(open(f'{BASE}/work/boq_cascade16_data.json', encoding='utf-8'))
BV = {v['key']: v for v in BOOK['villages']}
RE_V = RC['recheck']['villages']
COST = RC['cost']['base']
SENS = RC['cost']['sensitivity']
INST = RC['installed_with_margin']

wb = load_workbook(OUT, data_only=True)          # кэш recalc (формулы уже вычислены)
wbf = load_workbook(OUT)                          # формулы
ws = wb['Проверка волокно-км']
wsf = wbf['Проверка волокно-км']

fails = []
checked = 0


def chk(desc, actual, expected, tol=0.051):
    global checked
    checked += 1
    ok = (abs(actual - expected) <= tol) if isinstance(expected, (int, float)) \
        else (actual == expected)
    if not ok:
        fails.append(f'{desc}: лист={actual!r} vs ожидалось={expected!r}')


def chkf(desc, cell_ref, expected, tol=0.051):
    """Сверка значения формулы по кэшу recalc + presence формулы."""
    global checked
    checked += 1
    val = ws[cell_ref].value
    frm = wsf[cell_ref].value
    ok = (abs(val - expected) <= tol) if isinstance(expected, (int, float)) \
        else (val == expected)
    if not ok or not (isinstance(frm, str) and frm.startswith('=')):
        fails.append(f'{desc} [{cell_ref}]: кэш={val!r}, формула={frm!r}, ожидалось={expected!r}')


# ---------- порядок листов ----------
ORDER = ['Сводная', 'Параметры сетей', 'Сравнение схем', 'Оптимум по длине',
         'Проверка волокно-км', 'Методика']
chk('порядок листов', wbf.sheetnames, ORDER)

# ---------- блок А: перепроверка (строки 7-12, итог 13) ----------
for i, v in enumerate(RE_V):
    r = 7 + i
    b = BV[v['key']]
    chk(f'А: {v["name"]} ДХ', ws.cell(row=r, column=4).value, v['dhx'], 0)
    chk(f'А: {v["name"]} волокно-км книга', ws.cell(row=r, column=5).value, b['fiber_km'])
    chk(f'А: {v["name"]} волокно-км пересчёт', ws.cell(row=r, column=6).value, v['fiber_km'])
    chkf(f'А: {v["name"]} расхождение', f'G{r}', 0.0, 0.001)
    chk(f'А: {v["name"]} статус', ws.cell(row=r, column=8).value, 'совпадает')
chk('А: ИТОГО ДХ', ws.cell(row=13, column=4).value, 2334, 0)
chk('А: ИТОГО книга', ws.cell(row=13, column=5).value, 4375.1)
chk('А: ИТОГО пересчёт', ws.cell(row=13, column=6).value, 4375.1)
chk('А: ИТОГО расхождение', ws.cell(row=13, column=7).value, 0.0, 0.001)
chk('А: ИТОГО статус', ws.cell(row=13, column=8).value, 'совпадает')

# ---------- блок Б: декомпозиция (строки 18-23, итог 24) ----------
for i, v in enumerate(RE_V):
    r = 18 + i
    dc = v['decomp']
    chk(f'Б: {v["name"]} база', ws.cell(row=r, column=5).value, dc['base'])
    chkf(f'Б: {v["name"]} итого=std', f'I{r}', dc['std'])
    chk(f'Б: {v["name"]} ср.маршрут', ws.cell(row=r, column=10).value, v['routes']['avg_m'], 0.51)
    chk(f'Б: {v["name"]} медиана', ws.cell(row=r, column=11).value, v['routes']['med_m'], 0.51)
    chk(f'Б: {v["name"]} p90', ws.cell(row=r, column=12).value, v['routes']['p90_m'], 0.51)
td = RC['recheck']['totals']['decomp']
chk('Б: ИТОГО база', ws.cell(row=24, column=5).value, td['base'])
chk('Б: ИТОГО резерв', ws.cell(row=24, column=6).value, round(td['reserve'] - td['base'], 1), 0.15)
chk('Б: ИТОГО мин8', ws.cell(row=24, column=7).value, round(td['min8'] - td['reserve'], 1), 0.15)
chk('Б: ИТОГО стандарт', ws.cell(row=24, column=8).value, round(td['std'] - td['min8'], 1), 0.15)
chk('Б: ИТОГО волокно-км', ws.cell(row=24, column=9).value, td['std'])
chk('Б: ИТОГО ср.маршрут', ws.cell(row=24, column=10).value, RC['recheck']['totals']['avg_route_m'], 1.1)

# ---------- блок В: три схемы (строки 29-31) ----------
V_MAP = [(29, 'A_centr', 'Централизованная'), (30, 'B_cascade88', 'Каскад B'),
         (31, 'C_cascade416', 'Каскад C')]
for r, tag, lab in V_MAP:
    chk(f'В: {lab} волокно-км', ws.cell(row=r, column=4).value, COST[tag]['fiber_km'])
    chk(f'В: {lab} ёмкость BoQ', ws.cell(row=r, column=5).value, INST[tag], 1.1)
    chkf(f'В: {lab} на 1 ДХ', f'F{r}', round(COST[tag]['fiber_km'] / 2334, 2), 0.005)

# ---------- блок Г1: индекс стоимости (строки 38-40, итог 41, Δ 42) ----------
G1_MAP = [(38, 'cable'), (39, 'drop'), (40, 'hw')]
sheet_totals = {}
for j, tag in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
    col = chr(68 + j)
    ssum = 0.0
    for r, key in G1_MAP:
        exp = sum(COST[tag]['hw'].values()) if key == 'hw' else COST[tag][key]
        ssum += round(exp, 1)
    sheet_totals[tag] = round(ssum, 1)          # SUM округлённых компонент листа
for r, key in G1_MAP:
    for j, tag in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
        exp = sum(COST[tag]['hw'].values()) if key == 'hw' else COST[tag][key]
        chk(f'Г1: {key} {tag}', ws.cell(row=r, column=4 + j).value, round(exp, 1))
for j, tag in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
    col = chr(68 + j)
    chkf(f'Г1: ИТОГО {tag}', f'{col}41', sheet_totals[tag])
best_sheet = min(sheet_totals.values())
for j, tag in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
    col = chr(68 + j)
    chkf(f'Г1: Δ {tag}', f'{col}42', sheet_totals[tag] / best_sheet - 1, 0.001)

# ---------- блок Г2: чувствительность (строки 45-51) ----------
K_ORDER = ['0.0', '0.3', '0.4', '0.5', '0.6', '0.7', '1.0']
for i, k in enumerate(K_ORDER):
    r = 45 + i
    s = SENS[k]
    chk(f'Г2: k={k}', ws.cell(row=r, column=3).value, float(k), 0.001)
    chk(f'Г2: A k={k}', ws.cell(row=r, column=4).value, s['A_centr'])
    chk(f'Г2: B k={k}', ws.cell(row=r, column=5).value, s['B_cascade88'])
    chk(f'Г2: C k={k}', ws.cell(row=r, column=6).value, s['C_cascade416'])
    m = min(s['A_centr'], s['B_cascade88'], s['C_cascade416'])
    best_lab = 'A' if s['A_centr'] == m else ('B' if s['B_cascade88'] == m else 'C')
    chk(f'Г2: лучшая k={k}', ws.cell(row=r, column=7).value, best_lab)

# ---------- график (данные 63-69) ----------
for i, k in enumerate(K_ORDER):
    r = 63 + i
    s = SENS[k]
    chk(f'график: k={k}', ws.cell(row=r, column=2).value, float(k), 0.001)
    for j, tag in enumerate(('A_centr', 'B_cascade88', 'C_cascade416')):
        chk(f'график: {tag} k={k}', ws.cell(row=r, column=3 + j).value, s[tag])

# ---------- сопоставимость с каскадными книгами ----------
chk('В: волокно-км B = boq_cascade_data', COST['B_cascade88']['fiber_km'], C88['totals']['fiber_km'])
chk('В: волокно-км C = boq_cascade16_data', COST['C_cascade416']['fiber_km'], C416['totals']['fiber_km'])

# ---------- Методика: пункты 26-30 ----------
ws4 = wb['Методика']
M7 = {26: 'Перепроверка', 27: 'Причина', 28: 'Индекс стоимости',
      29: 'Чувствительность', 30: 'Вывод'}
for n, name in M7.items():
    row = next((r for r in range(5, ws4.max_row + 1)
                if ws4.cell(row=r, column=2).value == n), None)
    checked += 1
    if row is None or ws4.cell(row=row, column=3).value != name:
        fails.append(f'Методика: пункт {n} «{name}» не найден (строка {row})')

# ---------- неизменность остальных листов ----------
# «Параметры сетей»: строка ИТОГО / справочно (11), волокно-км — столбец M
ws2 = wb['Параметры сетей']
fk_c = round(sum(v['fiber_km'] for v in C416['villages']), 1)
chk('«Параметры сетей» ИТОГО волокно-км (не изменён)', ws2.cell(row=11, column=13).value, fk_c)
chk('«Параметры сетей» ИТОГО ДХ (не изменён)', ws2.cell(row=11, column=6).value, 2334, 0)
# «Сравнение схем»: волокно-км трёх схем присутствует (не изменён)
ws3 = wb['Сравнение схем']
vals3 = [c.value for row in ws3.iter_rows() for c in row if isinstance(c.value, (int, float))]
for target, lab in [(4375.1, 'A'), (1256.1, 'B'), (889.2, 'C')]:
    chk(f'«Сравнение схем»: волокно-км {lab} присутствует',
        1 if any(abs(v - target) < 0.05 for v in vals3) else 0, 1, 0)

print(f'Проверено значений: {checked}')
if fails:
    print(f'ОШИБКИ ({len(fails)}):')
    for f in fails:
        print(' -', f)
    raise SystemExit(1)
print('ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: лист «Проверка волокно-км» полностью сходится с источниками')
