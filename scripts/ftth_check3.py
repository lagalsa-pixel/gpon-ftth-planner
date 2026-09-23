#!/usr/bin/env python3
"""Контроль качества design3: ёмкость ОРШ <= 32, уникальность меток, дропы
заканчиваются на контуре построек (не в центроидах), корректность нумерации."""
import json, math, os, sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
HH_DIR = os.path.join(BASE, 'ftth_out')
sys.path.insert(0, BASE)
from ftth_households import VILLAGES


def local_frame(lat0):
    return 111132.0, 111320.0 * math.cos(math.radians(lat0))


def pt_poly_dist(plat, plon, poly, ky, kx):
    """Расстояние от точки до контура полигона."""
    px, py = plon * kx, plat * ky
    best = 1e18
    ring = list(poly) + [poly[0]]
    for a, b in zip(ring[:-1], ring[1:]):
        ax, ay = a[1] * kx, a[0] * ky
        bx, by = b[1] * kx, b[0] * ky
        dx, dy = bx - ax, by - ay
        dd = dx * dx + dy * dy
        t = 0.0 if dd < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dd))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


ok_all = True
for v in VILLAGES:
    key = v['key']
    d = json.load(open(os.path.join(HH_DIR, f'{key}_design3.json')))
    hhj = json.load(open(os.path.join(HH_DIR, f'{key}_hh_full.json')))
    hh_by_n = {h['n']: h for h in hhj['households']}
    ky, kx = local_frame(d['anchor'][0])

    labels = [h['label'] for h in d['households']]
    n_dup = len(labels) - len(set(labels))
    loads = [s['hh'] for s in d['splitters']]
    over = [x for x in loads if x > 32]
    # дропы: конечная точка на контуре главного дома (для выявленных ДХ)
    on_facade = 0
    off_facade = []
    for dp in d['drops']:
        h = hh_by_n[dp['n']]
        if not h.get('polygons'):
            continue
        dd = min(pt_poly_dist(dp['to'][0], dp['to'][1], p, ky, kx) for p in h['polygons'])
        if dd <= 0.6:
            on_facade += 1
        else:
            off_facade.append(round(dd, 1))
    # нумерация ОРШ сквозная 1..N
    nums = sorted(s['num'] for s in d['splitters'])
    seq_ok = nums == list(range(1, len(nums) + 1))
    ports_ok = all(1 <= h['port'] <= next(s['hh'] for s in d['splitters']
                                          if s['num'] == h['spl'])
                   for h in d['households'])
    status = 'OK' if (n_dup == 0 and not over and seq_ok and ports_ok and not off_facade) else 'ПРОБЛЕМЫ'
    if status != 'OK':
        ok_all = False
    print(f"{v['name']:<20} ОРШ {len(loads):>3} (макс. загрузка {max(loads)}), "
          f"метки: дублей {n_dup}, нумерация {'сквозная' if seq_ok else 'СБОЙ'}, "
          f"порты {'OK' if ports_ok else 'СБОЙ'}, "
          f"дропы на фасадах {on_facade}/{sum(1 for dp in d['drops'] if hh_by_n[dp['n']].get('polygons'))}"
          + (f", отклонения {off_facade[:5]}" if off_facade else '') + f" -> {status}")
print('\nИТОГ:', 'ВСЁ КОРРЕКТНО' if ok_all else 'ЕСТЬ ПРОБЛЕМЫ')
