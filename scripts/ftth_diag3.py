#!/usr/bin/env python3
"""Диагностика v2-топологии перед оптимизацией v3:
- распределение длин дропов (сейчас: от снапа на дороге до ЦЕНТРОИДА дома);
- потенциал сокращения при привязке дропа к ФАСАДУ (ближайшая точка контура
  главного жилого дома);
- качество размещения ОРШ: евклидовы дистанции шкаф -> абоненты, доля ОРШ
  на пересечениях (нужен граф — оценим по разбросу членов), aerial-fallback."""
import json, math, os, sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
HH_DIR = os.path.join(BASE, 'ftth_out')


def local_frame(lat0):
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(lat0))
    return ky, kx


def pt_seg_dist(p, a, b):
    """Расстояние от точки p до отрезка ab + ближайшая точка на отрезке."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    dd = dx * dx + dy * dy
    t = 0.0 if dd < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dd))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy), (qx, qy)


def main():
    from ftth_households import VILLAGES
    print(f"{'Село':<20}{'N':>5}{'дроп ср':>9}{'мед':>7}{'p90':>7}{'макс':>8}{'>60м':>6}"
          f"{'фасад ср':>10}{'выгода%':>9}{'ОРШ':>5}{'ОРШ->аб ср':>11}{'ОРШ->аб макс':>13}{'аэр':>5}")
    tot = dict(n=0, drop=0.0, facade=0.0)
    for v in VILLAGES:
        key = v['key']
        d = json.load(open(os.path.join(HH_DIR, f'{key}_design2.json')))
        hhj = json.load(open(os.path.join(HH_DIR, f'{key}_hh_full.json')))
        ky, kx = local_frame(d['anchor'][0])

        hh_by_n = {h['n']: h for h in hhj['households']}
        drops_now, drops_fac = [], []
        for dp in d['drops']:
            h = hh_by_n[dp['n']]
            sx, sy = dp['snap'][1] * kx, dp['snap'][0] * ky
            hx, hy = dp['to'][1] * kx, dp['to'][0] * ky
            d_now = math.hypot(hx - sx, hy - sy)
            drops_now.append(d_now)
            # фасад: ближайшая точка контура главного дома к снапу
            best = d_now
            if h.get('polygons'):
                # главный полигон = тот, чей центроид совпадает с lat/lon ДХ
                main_poly = None
                best_cd = 1e18
                for poly in h['polygons']:
                    cx = sum(p[1] for p in poly) / len(poly) * kx
                    cy = sum(p[0] for p in poly) / len(poly) * ky
                    cd = math.hypot(cx - hx, cy - hy)
                    if cd < best_cd:
                        best_cd, main_poly = cd, poly
                ring = main_poly + [main_poly[0]]
                for a, b in zip(ring[:-1], ring[1:]):
                    A = (a[1] * kx, a[0] * ky)
                    B = (b[1] * kx, b[0] * ky)
                    dd, _ = pt_seg_dist((sx, sy), A, B)
                    if dd < best:
                        best = dd
            drops_fac.append(best)

        now = np.array(drops_now); fac = np.array(drops_fac)
        # ОРШ -> абоненты (евклид)
        spl_xy = np.array([(s['lat'] * ky, s['lon'] * kx) for s in d['splitters']])
        hh_xy = np.array([(h['lat'] * ky, h['lon'] * kx) for h in d['households']])
        d_spl_hh = []
        for h in d['households']:
            j = h['spl'] - 1
            d_spl_hh.append(math.hypot(*(hh_xy[d['households'].index(h)] - spl_xy[j])))
        dsh = np.array(d_spl_hh)
        n_aer = len(d.get('aerial', []))

        print(f"{v['name']:<20}{len(now):>5}{now.mean():>9.1f}{np.median(now):>7.1f}"
              f"{np.percentile(now, 90):>7.1f}{now.max():>8.1f}{int((now > 60).sum()):>6}"
              f"{fac.mean():>10.1f}{(1 - fac.sum() / now.sum()) * 100:>9.1f}"
              f"{len(spl_xy):>5}{dsh.mean():>11.1f}{dsh.max():>13.1f}{n_aer:>5}")
        tot['n'] += len(now); tot['drop'] += now.sum(); tot['facade'] += fac.sum()

    print(f"\nИТОГО: N={tot['n']}, дропы(геом) {tot['drop']/1000:.2f} км, "
          f"до фасадов {tot['facade']/1000:.2f} км, "
          f"выигрыш от фасадов {100*(1-tot['facade']/tot['drop']):.1f}%")
    # вклад постоянного ввода 15 м
    print(f"Ввод 15 м/дом: {tot['n']*15/1000:.1f} км из учтённых дропов; "
          f"при вводе 10 м: {tot['n']*10/1000:.1f} км (экономия {tot['n']*5/1000:.1f} км)")


if __name__ == '__main__':
    main()
