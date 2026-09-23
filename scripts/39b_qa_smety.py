# -*- coding: utf-8 -*-
"""
Шаг 39b. QA пересчитанных смет: арифметика (G = round(F x E)), итоги,
структура (А4 удалён, ОКА-А48 есть, нумерация подряд), согласованность
ведомости со сметой (канат/зажим/подвес), трудоёмкость, шапка.
Запуск: python3 39b_qa_smety.py
"""
import openpyxl

BASE = '/home/z/my-project'
SRC = f'{BASE}/download/Сметы_прокладка_схема_D'
FILES = ['ЛС_Алтайский_716.xlsx', 'ЛС_Верхнеберезовское_940.xlsx',
         'ЛС_Винное_490.xlsx', 'ЛС_Перевально_339.xlsx',
         'ЛС_Пригородное_365.xlsx', 'ЛС_Солнечное_366.xlsx']

CODE_A4 = '274-303-0902-0054'
CODE_OKA48 = '274-305-0103-0032'


def code_of(b):
    return str(b).split('\n')[0].strip() if b else None


ok_all = True
for fn in FILES:
    wb = openpyxl.load_workbook(f'{SRC}/{fn}')
    ws = wb['Смета']
    errs = []

    # 1. Арифметика позиций и под-позиций
    tops = []
    for row in ws.iter_rows(min_row=30, max_row=ws.max_row):
        a, c = row[0].value, row[2].value
        e, f, g = row[4].value, row[5].value, row[6].value
        if isinstance(a, int) and c:
            tops.append((a, code_of(row[1].value), e, f, g))
        if isinstance(e, (int, float)) and isinstance(f, (int, float)) \
                and isinstance(g, (int, float)):
            if abs(round(f * e) - g) > 1:
                errs.append(f'r{row[0].row}: G {g} != F*E {round(f * e)}')
        if e is None and isinstance(f, (int, float)) and isinstance(g, (int, float)):
            # строка «в том числе»: G = F * E_родителя — проверим ниже
            pass

    # 2. Структура
    codes = [t[1] for t in tops]
    if CODE_A4 in codes:
        errs.append('А4 не удалён')
    if CODE_OKA48 not in codes:
        errs.append('ОКА-А48 отсутствует')
    nums = [t[0] for t in tops]
    if nums != list(range(1, len(nums) + 1)):
        errs.append(f'нумерация не подряд: {nums}')

    # 3. Итоги
    tot = sum(t[4] for t in tops)
    if abs(tot - ws['G22'].value) > 1:
        errs.append(f'G22 {ws["G22"].value} != Σ позиций {tot}')
    ch = sum(row[4].value for row in ws.iter_rows(min_row=30, max_row=ws.max_row)
             if row[3].value == 'чел.-ч' and isinstance(row[4].value, (int, float)))
    if abs(round(ch) - ws['E29'].value) > 1:
        errs.append(f'E29 {ws["E29"].value} != Σчел-ч {round(ch)}')
    if abs(round(ws['G22'].value / 1000, 3) - ws['F15'].value) > 0.001:
        errs.append('F15 != G22/1000')
    if abs(round(ch / 1000, 3) - ws['F17'].value) > 0.001:
        errs.append('F17 != E29/1000')

    # 4. Согласованность ведомости: канат/зажим/подвес
    wsv = wb['ведомость']
    sm = {}
    for row in ws.iter_rows(min_row=30, max_row=ws.max_row):
        c, d, e = str(row[2].value or ''), row[3].value, row[4].value
        if d in ('м', 'кг', 'т') and isinstance(e, (int, float)):
            key = c[:24]
            sm[key] = sm.get(key, 0) + e
    for row in wsv.iter_rows(min_row=10, max_row=wsv.max_row):
        c = str(row[2].value or '')
        e, f, g = row[4].value, row[5].value, row[6].value
        if isinstance(e, (int, float)) and isinstance(f, (int, float)):
            if abs(round(f * e) - g) > 1:
                errs.append(f'ведомость r{row[0].row}: G != F*E')
        for key, val in sm.items():
            if c.startswith(key) and key.startswith(('Канат', 'Зажим', 'Подвес')):
                if abs(e - val) > 0.01:
                    errs.append(f'ведомость {key[:12]}: {e} != смета {val}')

    # 5. Муфты не изменились: сравним итоги муфтовых позиций с оригиналом
    wbo = openpyxl.load_workbook(f'{BASE}/work/smety/extracted/{fn}')
    wso = wbo['Смета']
    def mufty_total(w):
        s = 0
        for row in w.iter_rows(min_row=30, max_row=w.max_row):
            b = code_of(row[1].value)
            if b and (b.startswith('274-309') or b.startswith('261-302')
                      or b.startswith('1310-0904')):
                if isinstance(row[0].value, int):
                    s += row[6].value or 0
        return s
    if abs(mufty_total(ws) - mufty_total(wso)) > 1:
        errs.append('муфты изменились!')

    st = 'OK ' if not errs else 'ERR'
    if errs:
        ok_all = False
    print(f'{st} {fn}: позиций {len(tops)}, ВСЕГО {ws["G22"].value:,} тг, '
          f'трудоёмкость {ws["E29"].value} чел-ч, F16 {ws["F16"].value}')
    for e in errs:
        print('   !!', e)

print('\n' + ('ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok_all else 'ЕСТЬ ОШИБКИ'))
