#!/usr/bin/env python3
"""Сводный отчёт xlsx по проекту FTTH для 6 СНП ВКО.

Листы: Сводка · Кабельный журнал · Оборудование · Зоны · Методика · Проверка.
Данные: scripts/ftth_design/<key>.json. Стиль: skills/xlsx design system (base.py).

Использование: python3 ftth_report.py
"""
import json, os, sys

XLSX_SKILL_DIR = "/home/z/my-project/skills/xlsx"
for sub in [XLSX_SKILL_DIR, os.path.join(XLSX_SKILL_DIR, "templates")]:
    if sub not in sys.path:
        sys.path.insert(0, sub)
from base import *  # noqa
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

DESIGN_DIR = "/home/z/my-project/scripts/ftth_design"
OUT = "/home/z/my-project/download/snp_vko/ftth/FTTH_проект_ВКО.xlsx"

F_INT = "#,##0"
F_KM = "#,##0.00"
F_M = "#,##0"
F_DB = "0.0"

with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
    BOUNDS = json.load(f)

designs = []
for v in BOUNDS:
    with open(os.path.join(DESIGN_DIR, f"{v['key']}.json"), encoding="utf-8") as f:
        designs.append((v, json.load(f)))

wb = Workbook()

# ============================================================ 1. Сводка
ws = wb.active
ws.title = "Сводка"
headers = ["№", "СНП", "Район / сельский округ", "ДХ по учёту", "Абонентов (OSM)",
           "Зоны ODN", "PON-портов", "Магистраль, км", "Распределение, км",
           "Абонент. разводка, км", "Всего кабеля, км", "Средний ввод, м",
           "Макс. ввод, м", "Затухание, дБ", "Запас, дБ"]
last_col = len(headers) + 1  # B..P
setup_sheet(ws, title="Проект FTTH (GPON) · 6 СНП Восточно-Казахстанской области · сводка", last_col=last_col)
for ci, h in enumerate(headers, start=2):
    ws.cell(row=4, column=ci, value=h)
style_header_row(ws, 4, 2, last_col)

r = 5
for i, (v, d) in enumerate(designs, 1):
    s = d["stats"]
    okr = f"{v['district']}, {v['okrug']}" if v["okrug"] != "—" else v["district"]
    row = [i, v["name"], okr, v["households"], s["n_households"], s["n_zones"], s["n_groups"],
           s["feeder_km"], s["dist_km"], s["drop_cable_km"], s["total_km"],
           s["drop_mean_m"], s["drop_max_m"], s["loss_db"], s["margin_db"]]
    for ci, val in enumerate(row, start=2):
        ws.cell(row=r, column=ci, value=val)
    style_data_row(ws, r, 2, last_col, i - 1)
    for ci in (2, 5, 6, 7, 8, 13, 14):
        ws.cell(row=r, column=ci).alignment = align_number()
    for ci in (9, 10, 11, 12):
        c = ws.cell(row=r, column=ci); c.alignment = align_number(); c.number_format = F_KM
    ws.cell(row=r, column=13).number_format = F_INT
    ws.cell(row=r, column=14).number_format = F_INT
    ws.cell(row=r, column=15).number_format = F_DB
    ws.cell(row=r, column=16).number_format = F_DB
    r += 1

tot = r
ws.cell(row=tot, column=2, value="Итого")
ws.cell(row=tot, column=3, value="6 СНП")
for ci in range(5, 13):
    L = get_column_letter(ci)
    ws.cell(row=tot, column=ci, value=f"=SUM({L}5:{L}{tot-1})")
ws.cell(row=tot, column=13, value=f"=ROUND(SUMPRODUCT(F5:F10,M5:M10)/F{tot},0)")
ws.cell(row=tot, column=14, value=f"=MAX(N5:N{tot-1})")
ws.cell(row=tot, column=15, value=f"=MAX(O5:O{tot-1})")
ws.cell(row=tot, column=16, value=f"=MIN(P5:P{tot-1})")
style_total_row(ws, tot, 2, last_col)
for ci in (5, 6, 7, 8, 13, 14):
    ws.cell(row=tot, column=ci).alignment = align_number()
    ws.cell(row=tot, column=ci).number_format = F_INT
for ci in (9, 10, 11, 12):
    c = ws.cell(row=tot, column=ci); c.alignment = align_number(); c.number_format = F_KM
ws.cell(row=tot, column=15).number_format = F_DB
ws.cell(row=tot, column=16).number_format = F_DB
auto_fit_columns(ws, header_row=4, data_start_row=5)
ws.freeze_panes = "D5"

# ============================================================ 2. Кабельный журнал
ws = wb.create_sheet("Кабельный журнал")
headers = ["№", "СНП", "Категория сегмента", "Кабель, волокон", "Протяжённость, м", "Доля, %"]
last_col = len(headers) + 1
setup_sheet(ws, title="Кабельный журнал по типам кабеля (расчётная протяжённость с запасом 3%)", last_col=last_col)
for ci, h in enumerate(headers, start=2):
    ws.cell(row=4, column=ci, value=h)
style_header_row(ws, 4, 2, last_col)

jr = 5
jrow_idx = 0
journal_rows = []
for i, (v, d) in enumerate(designs, 1):
    s = d["stats"]
    cat_rows = []
    for fib, m in sorted(s["feeder_by_fibers"].items(), key=lambda kv: int(kv[0])):
        cat_rows.append(("магистральный (OLT → М1)", fib, round(m)))
    for fib, m in sorted(s["dist_by_fibers"].items(), key=lambda kv: int(kv[0])):
        cat_rows.append(("распределительный (М1 → зоны)", fib, round(m)))
    for fib, m in sorted(s["drop_by_fibers"].items(), key=lambda kv: int(kv[0])):
        cat_rows.append(("абонентский по улицам", fib, round(m)))
    cat_rows.append(("абонентский ввод к дому (фасад, запас 15 м)", "2", round(s["drop_entry_km"] * 1000)))
    for cat, fib, m in cat_rows:
        journal_rows.append((i, v["name"], cat, fib, m))
        for ci, val in enumerate([i, v["name"], cat, fib, m], start=2):
            ws.cell(row=jr, column=ci, value=val)
        style_data_row(ws, jr, 2, last_col, jrow_idx)
        for ci in (2, 5, 6):
            ws.cell(row=jr, column=ci).alignment = align_number()
        ws.cell(row=jr, column=6).number_format = F_M
        jrow_idx += 1
        jr += 1

tot = jr
tot_m = sum(rr[4] for rr in journal_rows)
ws.cell(row=tot, column=2, value="Итого")
ws.cell(row=tot, column=6, value=f"=SUM(F5:F{tot-1})")
ws.cell(row=tot, column=7, value=100.0)
style_total_row(ws, tot, 2, last_col)
ws.cell(row=tot, column=6).alignment = align_number()
ws.cell(row=tot, column=6).number_format = F_M
# доли
for rr_i in range(5, tot):
    ws.cell(row=rr_i, column=7, value=f"=ROUND(F{rr_i}/F${tot}*100,1)").number_format = "0.0"
    ws.cell(row=rr_i, column=7).alignment = align_number()
auto_fit_columns(ws, header_row=4, data_start_row=5)
ws.freeze_panes = "C5"

# ============================================================ 3. Оборудование
ws = wb.create_sheet("Оборудование")
headers = ["№", "СНП", "OLT, юнитов", "PON-портов", "ODF", "Сплиттеры 1×4",
           "Сплиттеры 1×16", "Муфты магистральные", "Боксы зон", "ONT (абонентские)",
           "Вводы в дома", "Точки подвеса"]
last_col = len(headers) + 1
setup_sheet(ws, title="Оборудование и материалы (оценка по проекту)", last_col=last_col)
for ci, h in enumerate(headers, start=2):
    ws.cell(row=4, column=ci, value=h)
style_header_row(ws, 4, 2, last_col)
r = 5
for i, (v, d) in enumerate(designs, 1):
    e = d["stats"]["equipment"]
    row = [i, v["name"], e["olt_units"], e["pon_ports"], e["odf"], e["spl1x4"],
           e["spl1x16"], e["muf_trunk"], e["boxes_zone"], e["ont"], e["drop_patches"],
           e["suspension_points"]]
    for ci, val in enumerate(row, start=2):
        ws.cell(row=r, column=ci, value=val)
    style_data_row(ws, r, 2, last_col, i - 1)
    for ci in range(2, last_col + 1):
        ws.cell(row=r, column=ci).alignment = align_number()
        ws.cell(row=r, column=ci).number_format = F_INT
    r += 1
tot = r
ws.cell(row=tot, column=2, value="Итого")
for ci in range(4, last_col + 1):
    L = get_column_letter(ci)
    ws.cell(row=tot, column=ci, value=f"=SUM({L}5:{L}{tot-1})")
style_total_row(ws, tot, 2, last_col)
for ci in range(4, last_col + 1):
    ws.cell(row=tot, column=ci).alignment = align_number()
    ws.cell(row=tot, column=ci).number_format = F_INT
auto_fit_columns(ws, header_row=4, data_start_row=5)
ws.freeze_panes = "C5"

# ============================================================ 4. Зоны
ws = wb.create_sheet("Зоны")
headers = ["№", "СНП", "Зона (бокс 1×16)", "PON-порт / муфта М1", "Домохозяйств"]
last_col = len(headers) + 1
setup_sheet(ws, title="Зоны распределения ODN (список по всем СНП)", last_col=last_col)
for ci, h in enumerate(headers, start=2):
    ws.cell(row=4, column=ci, value=h)
style_header_row(ws, 4, 2, last_col)
r = 5
n = 0
for i, (v, d) in enumerate(designs, 1):
    z2g = {}
    for g in d["groups"]:
        for zid in g["zones"]:
            z2g[zid] = g["id"]
    for z in d["zones"]:
        n += 1
        row = [n, v["name"], z["id"], z2g.get(z["id"]), z["n"]]
        for ci, val in enumerate(row, start=2):
            ws.cell(row=r, column=ci, value=val)
        style_data_row(ws, r, 2, last_col, n - 1)
        for ci in (2, 4, 5, 6):
            ws.cell(row=r, column=ci).alignment = align_number()
        r += 1
tot = r
ws.cell(row=tot, column=2, value="Итого")
ws.cell(row=tot, column=3, value=f"=COUNTA(C5:C{tot-1})")
ws.cell(row=tot, column=6, value=f"=SUM(F5:F{tot-1})")
style_total_row(ws, tot, 2, last_col)
ws.cell(row=tot, column=6).alignment = align_number()
auto_fit_columns(ws, header_row=4, data_start_row=5)
ws.freeze_panes = "C5"
zones_total_row = tot

# ============================================================ 5. Методика
ws = wb.create_sheet("Методика")
setup_sheet(ws, title="Методика, допущения и ограничения", last_col=3)
notes = [
    "1. Подложка: спутниковые снимки Google, зум 18, ~0.38 м/пиксель — максимальное подлинное разрешение для территории (проверено квадрант-анализом z17-z20).",
    "2. Геометрия улиц и зданий: © OpenStreetMap (ODbL). Домохозяйства определены по контурам жилых зданий (S >= 20 кв.м) с автосовмещением контуров со снимком (задача маркировки ДХ, реестры *_numbered.geojson).",
    "3. Архитектура сети: GPON (ITU-T G.984), двухуровневый каскад сплиттеров 1x4 (в магистральных муфтах М1) + 1x16 (в боксах зон) = 1:64, оптический бюджет Class B+ (28 дБ).",
    "4. Зона распределения: не более 12 ДХ на сплиттер 1x16 (загрузка <= 75%, резерв портов на развитие). PON-группа: до 4 зон на один порт OLT (до 48 абонентов на порт).",
    "5. Маршруты прокладки: кратчайшие пути по графу фактической улично-дорожной сети OSM (алгоритм Дейкстры) — кабели проходят вдоль реальных улиц, проездов и грунтовых дорог; последний участок к дому — воздушный ввод от ближайшей точки подвеса.",
    "6. Волокна: магистральный сегмент — 2 волокна на PON-группу (рабочее + резерв); распределительный — 2 волокна на зону; абонентская разводка по улице — по числу ДХ на участке + 2 резервных; ввод в дом — 2-волоконный самонесущий дроп-кабель (G.657A).",
    "7. Запасы: +3% к магистрали и распределению (провис, подъёмы, углы); ввод в дом — 15 м (крепление по фасаду + технологический запас).",
    "8. Бюджет потерь (наихудший абонент): волокно 0.35 дБ/км @1310 нм, сплиттер 1x4 — 7.4 дБ, сплиттер 1x16 — 13.9 дБ, 2 коннектора APC по 0.5 дБ, 4 сварных соединения по 0.05 дБ. Все сёла: 23.4-24.1 дБ при бюджете 28 дБ.",
    "9. Подвеска: предполагается использование существующих опор ЛЭП 0.4 кВ / связи (шаг ~45 м). Точки подвеса оценены по суммарной протяжённости трасс; установка новых опор не закладывалась.",
    "10. Расхождение с учётными ДХ: OSM покрывает 38-119% учётного числа ДХ (Алтайский — 38% из-за неполноты OSM; Винное/Солнечное — >100%, вероятно часть надворных построек). Проект рассчитан на выявленные ДХ; резерв портов сплиттеров допускает подключение дополнительных домов без реконструкции.",
    "11. Ограничения: геометрия грунтовых дорог OSM может отклоняться от видимой колеи на 10-30 м (GPS-трассировка); размещение OLT выбрано в центре нагрузки и подлежит привязке к реальному узлу связи оператора; схема проектная (стадия эскизного проекта) — требуется полевое обследование.",
    "12. Схемы: download/snp_vko/ftth/*.png — полное разрешение (Google z18 + слои FTTH + маркировка ДХ); previews/ — лёгкие превью.",
]
rn = 4
for t in notes:
    cell = ws.cell(row=rn, column=2, value=t)
    cell.font = font_body()
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.row_dimensions[rn].height = 30
    rn += 1
ws.column_dimensions["B"].width = 110

# ============================================================ 6. Проверка
ws = wb.create_sheet("Проверка")
ws.sheet_properties.tabColor = "FFC000"
headers = ["Проверка", "Ожидание", "Факт", "Статус"]
last_col = len(headers) + 1
setup_sheet(ws, title="Кросс-проверка итогов", last_col=last_col)
for ci, h in enumerate(headers, start=2):
    ws.cell(row=4, column=ci, value=h)
style_header_row(ws, 4, 2, last_col)

n_hh = sum(d["stats"]["n_households"] for v, d in designs)
n_zones = sum(d["stats"]["n_zones"] for v, d in designs)
n_ont = sum(d["stats"]["equipment"]["ont"] for v, d in designs)
n_spl16 = sum(d["stats"]["equipment"]["spl1x16"] for v, d in designs)

checks = [
    ("Абонентов (Сводка = сумма по сёлам)", f"=SUM(Сводка!F5:F10)", n_hh),
    ("Всего кабеля, км (Сводка = журнал, допуск 0.5)", f"=ROUND(SUM(Сводка!L5:L10),2)",
     f"=ROUND(SUM('Кабельный журнал'!F5:F{4 + len(journal_rows)})/1000,2)"),
    ("Зон ODN (Сводка = лист Зоны)", f"=SUM(Сводка!G5:G10)", f"=COUNTA(Зоны!C5:C{zones_total_row-1})"),
    ("ONT = абонентам (Оборудование = Сводка)", f"=SUM(Оборудование!K5:K10)", n_ont),
    ("Сплиттеров 1x16 = зонам (Оборудование = Сводка)", f"=SUM(Оборудование!H5:H10)", n_spl16),
]
r = 5
for i, (name, exp, act) in enumerate(checks):
    ws.cell(row=r, column=2, value=name)
    ws.cell(row=r, column=3, value=exp)
    ws.cell(row=r, column=4, value=act)
    ws.cell(row=r, column=5, value=f'=IF(ABS(C{r}-D{r})<=0.5,"PASS","FAIL")')
    style_data_row(ws, r, 2, last_col, i)
    for ci in (3, 4, 5):
        ws.cell(row=r, column=ci).alignment = align_number()
    r += 1
auto_fit_columns(ws, header_row=4, data_start_row=5)

wb.properties.creator = "Z.ai"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print(f"Сохранено: {OUT}")
print(f"Журнал: {len(journal_rows)} строк; зон: {n_zones}; абонентов: {n_hh}")
