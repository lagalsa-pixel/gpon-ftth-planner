#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 58c: применение правок оператора (corrections.json) к сети ДХ.

Этап «ручная корректировка оператором» (запрос заказчика, Task 58) —
второй шаг после операторской страницы 58b (HTML-редактор):
  1) 58b: оператор сверяет ДХ по спутнику, выгружает corrections.json;
  2) 58c (этот скрипт): правки применяются к work/<key>/network_hh2.json
     ИДЕМПОТЕНТНО (повторный запуск тех же правок — no-op), с бэкапом;
  3) конвейер пересчитывает материалы: 52d <key> -> 54 (FTTH_NET_OVERRIDE=
     network_hh3.json) -> 47_sync -> 48b -> 30/34 -> 38 -> 40 -> 49b QA.

Формат corrections.json (все поля op-специфичны, note/ts необязательны):
  {"village": "altaiskiy", "edits": [
    {"op": "add_hh",  "x": 3652.0, "y": 7920.0, "note": "пропущенный дом"},
    {"op": "remove_hh", "hh_id": 326, "note": "руины"},
    {"op": "set_mzd", "bid": 637127295, "n": 8, "note": "многоэтажка"},
    {"op": "set_mzd", "x": 3733.0, "y": 7826.0, "w": 33, "h": 34, "n": 2}
  ]}
Координаты — мозаичные пикселы (та же система, что в network_hh2.json).

Запуск: python3 58c_apply_corrections.py <key> <corrections.json> [--dry-run]
"""
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
sys.path.insert(0, str(BASE / 'scripts'))
from common import VILLAGES  # noqa: E402

NEAR_M = 3.0        # add_hh: идемпотентность — дроп ближе 3 м = «уже добавлен»
BLD_TOL_M = 14.0    # set_mzd: допуск привязки дропов к зданию
SPACING_MAX_M = 6.0  # расстояние между квартирными ДХ вдоль фасада


def g2p(la, lo, west, north, mpp):
    return ((lo - west) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (north - la) * 111132.0 / mpp)


def load_buildings(key):
    geo = json.load(open(BASE / 'work/mosaic_geo.json'))[key]
    mpp, west, north = geo['mpp'], geo['west'], geo['north']
    osm = json.load(open(BASE / f'work/{key}/osm.json'))
    out = {}
    for b in osm['buildings']:
        pts = [g2p(la, lo, west, north, mpp) for la, lo in b['poly']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out[b['id']] = dict(
            pts=pts, poly=Polygon(pts), mpp=mpp,
            cx=sum(xs) / len(xs), cy=sum(ys) / len(ys),
            x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys))
    return out


def axis_positions(cx, cy, x0, x1, y0, y1, mpp, n):
    """N позиций вдоль длинной оси (как 53m/54q: spacing <= 6 м)."""
    w, h = x1 - x0, y1 - y0
    horiz = w >= h
    long_m = (w if horiz else h) * mpp
    spacing = min(SPACING_MAX_M, long_m / (n + 1)) / mpp
    return [((cx + (i - (n - 1) / 2.0) * spacing, cy) if horiz else
             (cx, cy + (i - (n - 1) / 2.0) * spacing)) for i in range(n)]


def apply_corrections(key, corr, net, BLD, log):
    drops = net['drops']
    max_id = max(d['hh_id'] for d in drops)
    max_hh = max(d['hh'] for d in drops)
    n_add = n_rm = n_mzd = n_skip = 0

    for e in corr.get('edits', []):
        op = e.get('op')
        if op == 'add_hh':
            x, y = float(e['x']), float(e['y'])
            if any(math.hypot(d['poly'][-1][0] - x, d['poly'][-1][1] - y)
                   * BLD_MPP <= NEAR_M for d in drops):
                log(f"  SKIP add_hh ({x:.0f},{y:.0f}): дроп ближе {NEAR_M} м уже есть")
                n_skip += 1
                continue
            max_id += 1
            max_hh += 1
            drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                              poly=[[x, y], [x, y]], length_m=0.0))
            n_add += 1
            log(f"  + ДХ hh_id={max_id} ({x:.1f},{y:.1f})"
                + (f" — «{e['note']}»" if e.get('note') else ''))

        elif op == 'remove_hh':
            hh_id = int(e['hh_id'])
            before = len(drops)
            drops[:] = [d for d in drops if d['hh_id'] != hh_id]
            if len(drops) == before:
                log(f"  SKIP remove_hh hh_id={hh_id}: уже отсутствует")
                n_skip += 1
            else:
                n_rm += 1
                log(f"  - ДХ hh_id={hh_id}"
                    + (f" — «{e['note']}»" if e.get('note') else ''))

        elif op == 'set_mzd':
            n = int(e['n'])
            if 'bid' in e and e['bid'] in BLD:
                b = BLD[e['bid']]
                cx, cy, mpp = b['cx'], b['cy'], b['mpp']
                x0, x1, y0, y1 = b['x0'], b['x1'], b['y0'], b['y1']
                near = [d for d in drops
                        if b['poly'].distance(Point(d['poly'][-1])) * mpp <= BLD_TOL_M]
                where = f"здание {e['bid']}"
            else:
                cx, cy = float(e['x']), float(e['y'])
                w_px = float(e.get('w', 20)) / BLD_MPP
                h_px = float(e.get('h', 12)) / BLD_MPP
                x0, x1, y0, y1 = cx - w_px / 2, cx + w_px / 2, cy - h_px / 2, cy + h_px / 2
                mpp = BLD_MPP
                near = [d for d in drops
                        if math.hypot(d['poly'][-1][0] - cx, d['poly'][-1][1] - cy)
                        * mpp <= BLD_TOL_M + max(w_px, h_px) * mpp / 2]
                where = f"бокс ({cx:.0f},{cy:.0f}) {e.get('w', 20)}x{e.get('h', 12)} м"
            if len(near) == n:
                log(f"  SKIP set_mzd {where}: уже {n} ДХ")
                n_skip += 1
                continue
            near.sort(key=lambda d: d['hh_id'])
            keep = near[0] if near else None
            for d in near[1:]:
                drops.remove(d)
            pos = axis_positions(cx, cy, x0, x1, y0, y1, mpp, n)
            if keep is not None:
                new_pos = pos[1:]
            else:
                new_pos = pos
            for p in new_pos:
                max_id += 1
                max_hh += 1
                drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                                  poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))
            n_mzd += 1
            log(f"  ~ МЖД {where}: {len(near)} -> {n} ДХ "
                f"(сохранён hh_id={keep['hh_id'] if keep else None})"
                + (f" — «{e['note']}»" if e.get('note') else ''))
        else:
            log(f"  ?? неизвестный op: {op} — пропущен")
            n_skip += 1
    return n_add, n_rm, n_mzd, n_skip


def main():
    key = sys.argv[1]
    corr_path = Path(sys.argv[2])
    dry = '--dry-run' in sys.argv
    assert key in [v['key'] for v in VILLAGES], f'нет села {key}'

    corr = json.load(open(corr_path, encoding='utf-8'))
    assert corr.get('village', key) == key, \
        f"corrections для {corr.get('village')}, запрошено {key}"

    np = BASE / f'work/{key}/network_hh2.json'
    net = json.load(open(np))
    n0 = len(net['drops'])
    global BLD_MPP
    geo = json.load(open(BASE / 'work/mosaic_geo.json'))[key]
    BLD_MPP = geo['mpp']
    BLD = load_buildings(key)

    lines = []
    log = lines.append
    log(f'== {key}: corrections ({corr_path.name}'
        + (', DRY-RUN' if dry else '') + ') ==')
    log(f'дропов до: {n0}')
    n_add, n_rm, n_mzd, n_skip = apply_corrections(key, corr, net, BLD, log)

    out = '\n'.join(lines)
    print(out)
    print(f'ИТОГО: +{n_add} / -{n_rm} / МЖД {n_mzd} / skip {n_skip} '
          f'=> дропов {n0} -> {len(net["drops"])}')

    if dry:
        print('DRY-RUN: network_hh2.json не изменён')
        return

    shutil.copy(np, np.with_suffix('.json.bak_corr'))
    net['drops'] = net['drops']
    st = net.get('stats', {})
    st['served'] = len(net['drops'])
    st['remark_task58'] = (f'правки оператора {corr_path.name}: '
                           f'+{n_add} / -{n_rm} / МЖД {n_mzd} / skip {n_skip}')
    net['stats'] = st
    json.dump(net, open(np, 'w'), ensure_ascii=False)
    print(f'сохранено: {np} (бэкап .json.bak_corr)')
    print('далее конвейер: 52d %s -> 54 (FTTH_NET_OVERRIDE=network_hh3.json) '
          '-> 47_sync -> 48b -> 30/34 -> 38 -> 40 -> 49b' % key)


if __name__ == '__main__':
    main()
