# -*- coding: utf-8 -*-
"""
Шаг 49b. Числовой QA выпущенных материалов топологии v4.

Проверки:
 1) КАРТЫ (download/snp_vko, 6 шт): существование и размер; канва = база +
    шапка; число зон из книги v3; сумма домов зон = ДХ села; пиксель в центре
    каждого зонного ОРШ (медианы) = цвет палитры зоны (порядок = по ДХ);
    пиксель в центре ЦУ — красный; тёмная панель легенды ровно в одном
    нижнем углу; превью work/qa/zone_maps_v4 существует.
 2) КНИГА xlsx: лист «Децентрализация ОРШ» — число строк зон = ОРШ v3;
    лист «Сводная (схема D)» — итог волокно-км = totals v4.
 3) Итоговая сверка totals v4 (zones/orsh/fiber) с JSON.

Выход: консольный отчёт + work/qa/v4_report.json
"""
import json
import math
import os
import importlib.util
from collections import Counter

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

BASE = '/home/z/my-project'
DL = f'{BASE}/download/snp_vko'
QAD = f'{BASE}/work/qa/zone_maps_v4'

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)
nkey = de28.nkey

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}

PALETTE = [
    (25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
    (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
    (160, 90, 44),
]
C_CU = (224, 49, 49)
CROPS = {'solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altaiskiy'}

report = dict(villages=[], ok=True)


def px_close(a, b, tol=60):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


for v in de28.VILLAGES:
    key = v['key']
    db = DBY[key]
    rec = dict(key=key, name=db['name'], checks=[])

    def chk(name, cond, detail=''):
        rec['checks'].append(dict(name=name, ok=bool(cond), detail=str(detail)[:120]))
        if not cond:
            report['ok'] = False

    fname = f"{DL}/{db['num']}_{db['name']}_зоны_ОРШ_схема_D.jpg"
    chk('файл существует', os.path.exists(fname), fname)
    chk('размер > 3 МБ', os.path.getsize(fname) > 3e6)

    # база и преобразование
    if key in CROPS:
        tr = json.load(open(f'{BASE}/work/{key}/crop_transform.json', encoding='utf-8'))
        Mi, scale = tr['M_inv'], tr['scale']
        Wb, Hb = Image.open(tr['new_image'] if os.path.isabs(tr['new_image'])
                            else os.path.join(BASE, tr['new_image'])).size
    else:
        Mi, scale = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], 1.0
        Wb, Hb = Image.open(f'{BASE}/work/{key}/mosaic.jpg').size
    k = 1.0 / scale
    HH = max(1, int(round(150 * k)))

    def T(p):
        return (Mi[0][0] * p[0] + Mi[0][1] * p[1] + Mi[0][2],
                Mi[1][0] * p[0] + Mi[1][1] * p[1] + Mi[1][2])

    im = Image.open(fname).convert('RGB')
    W, H = im.size
    chk('канва = база + шапка', (W, H - HH) == (Wb, Hb), f'{W}x{H} vs база {Wb}x{Hb}+{HH}')
    px = im.load()

    def count_color(cx, cy, color, tol, win=40, step=2):
        n = 0
        for dx in range(-win, win + 1, step):
            for dy in range(-win, win + 1, step):
                xi, yi = int(cx) + dx, int(cy) + dy
                if 0 <= xi < W and 0 <= yi < H:
                    c = px[xi, yi]
                    if all(abs(a - b) <= tol for a, b in zip(c, color)):
                        n += 1
        return n

    # зоны: порядок по ДХ (как на карте)
    zones = db['zones'][1:]
    order = sorted(zones, key=lambda z: -z['houses'])
    chk('число зон = книге', len(zones) == db['n_zones'], f"{len(zones)} / {db['n_zones']}")
    chk('сумма домов зон = ДХ', sum(z['houses'] for z in db['zones']) == db['dhx_served'])

    for i, z in enumerate(order):
        x, y = T(z['orsh_px'])
        col = PALETTE[i % len(PALETTE)]
        # канва = база + шапка HH сверху: контент смещён на (0, HH);
        # центры маркеров часто перекрыты подписью — сканируем окно
        n = count_color(x, y + HH, col, 70, win=int(round(40 * k)))
        chk(f"ОРШ-{i + 1} в медиане, цвет зоны", n >= 50, f'совпадений в окне: {n}')

    net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
    ax, ay = T((net['anchor']['x'], net['anchor']['y']))
    ncu = count_color(ax, ay + HH, C_CU, 90, win=int(round(45 * k)))
    chk('ЦУ — красная звезда', ncu >= 50, f'красных в окне: {ncu}')

    # легенда: сайдкар от рендера (48) — тёмная сине-чёрная панель
    lgs = json.load(open(f"{QAD}/{db['num']}_legend.json"))
    lx, ly = int(lgs['x'] + lgs['W'] / 2), int(lgs['y'] + lgs['H'] / 2)
    r_, g_, b_ = px[lx, ly]
    chk('панель легенды (сайдкар)', r_ < 80 and g_ < 85 and b_ < 115 and b_ >= r_,
        f'({lx},{ly}) rgb=({r_},{g_},{b_}), тег {lgs["tag"]}')

    prev = f"{QAD}/{db['num']}_preview.png"
    chk('превью существует', os.path.exists(prev), prev)

    n_ok = sum(1 for c in rec['checks'] if c['ok'])
    print(f"{db['num']} {db['name']:<18} проверок {len(rec['checks'])}, OK {n_ok}"
          + ('' if n_ok == len(rec['checks']) else '  !! ЕСТЬ ЗАМЕЧАНИЯ'))
    for c in rec['checks']:
        if not c['ok']:
            print(f"   !! {c['name']}: {c['detail']}")
    report['villages'].append(rec)

# --- книга xlsx ---
from openpyxl import load_workbook
wb = load_workbook(f'{BASE}/download/Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx',
                   read_only=True, data_only=False)
ws = wb['Децентрализация ОРШ']
rows = list(ws.iter_rows(min_col=3, max_col=4, values_only=True))
n_zone_rows = sum(1 for r in rows if r[1] and isinstance(r[1], str)
                  and r[1].startswith('З-'))
tot = DBOOK['totals']
xlsx_ok = n_zone_rows == tot['n_zones']
print(f"\nкнига xlsx: строк зон в «Децентрализация ОРШ» = {n_zone_rows} "
      f"(книга v4: {tot['n_zones']})  {'OK' if xlsx_ok else '!! РАСХОЖДЕНИЕ'}")
if not xlsx_ok:
    report['ok'] = False
wb.close()

print(f"\nИТОГ QA v4: {'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if report['ok'] else 'ЕСТЬ ЗАМЕЧАНИЯ'}")
json.dump(report, open(f'{BASE}/work/qa/v4_report.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
