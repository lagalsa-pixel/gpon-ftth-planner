#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 58a: аудит групп квартирных ДХ (МЖД) по всем сёлам.

Заказчик: «по многоэтажкам: давай заменим группу абонентов в МЖД одним
значком с указанием их количества и не будем прорисовывать для них дропы
и этажные распределительные коробки, но расчет оставим».

Скрипт находит здания, у которых >= 2 дропов (группа квартирных ДХ):
- здания OSM (work/<key>/osm.json, полигоны) + сетка для Пригородного;
- дропы network_hh3.json (конечная точка полигона дропа);
- дроп вне OSM приписывается ближайшему зданию в допуске R_TOL (эти
  случаи отдельно помечаются cv=1 — cv-детекция без полигона OSM).

Выход: work/<key>/mzd_groups.json
  [{bid, cx, cy, w, h, n, hh_ids: [...], cv: bool, kind: 'apartment'|'split'}, ...]
  kind='apartment' (МЖД, n>=4 — формула квартир: уровни/площадь) — на карте
  заменяются ОДНИМ значком с числом квартир (дропы не прорисованы, расчёт
  сохранён — заказчик, Task 58); kind='split' (n=2..3 — дуплексы, дворовые
  кластеры, сплиты крыш) — прорисовываются как прежде, отдельные дропы.
  + сводка в консоль.
"""
import json
import math
import sys
from pathlib import Path

BASE = Path('/home/z/my-project')
sys.path.insert(0, str(BASE / 'scripts'))
from common import VILLAGES, load_json, save_json  # noqa: E402

R_TOL_M = 14.0          # допуск привязки дропа к зданию (от контура)
CV_GROUP_TOL_M = 8.0    # кластеризация дропов вне OSM (cv-группы)
APT_MIN_N = 4           # МЖД-значок: формула квартир даёт >=4 ДХ на здание
                        # (дуплексы/сплиты n=2 и дворовые кластеры n=3 —
                        # 1-этажные, остаются с отдельными дропами)

KEYS = [v['key'] for v in VILLAGES]


def g2p(la, lo, west, north, mpp):
    return ((lo - west) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (north - la) * 111132.0 / mpp)


def poly_area_centroid(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    # shoelace
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0, cx, cy


def dist_to_poly(px, py, pts):
    """Расстояние от точки до полигона (0 внутри)."""
    def seg(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        qx, qy = ax + t * dx, ay + t * dy
        return math.hypot(px - qx, py - qy)
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py) and \
           px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    if inside:
        return 0.0
    return min(seg(px, py, *pts[i], *pts[(i + 1) % n]) for i in range(n))


def main():
    grand = {}
    for key in KEYS:
        vdir = BASE / 'work' / key
        net = load_json(vdir / 'network_hh3.json')
        geo = load_json(BASE / 'work' / 'mosaic_geo.json')[key]
        mpp, west, north = geo['mpp'], geo['west'], geo['north']
        osm = load_json(vdir / 'osm.json')

        # здания OSM в пикселах мозаики
        blds = []
        for b in osm['buildings']:
            pts = [g2p(la, lo, west, north, mpp) for la, lo in b['poly']]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            area_px, cx, cy = poly_area_centroid(pts)
            blds.append(dict(bid=b['id'], pts=pts,
                             cx=cx, cy=cy,
                             w=(max(xs) - min(xs)) * mpp,
                             h=(max(ys) - min(ys)) * mpp,
                             area_m2=area_px * mpp * mpp))
        tol_px = R_TOL_M / mpp

        # привязка дропов к зданиям
        bld_drops = {i: [] for i in range(len(blds))}   # idx -> [drop]
        orphans = []
        for d in net['drops']:
            px, py = d['poly'][-1]
            best, bd = None, 1e18
            for i, b in enumerate(blds):
                dd = dist_to_poly(px, py, b['pts'])
                if dd < bd:
                    best, bd = i, dd
            if best is not None and bd <= tol_px:
                bld_drops[best].append(d)
            else:
                orphans.append(d)

        # группы: здания OSM с >=2 дропами
        groups = []
        for i, b in enumerate(blds):
            ds = bld_drops[i]
            if len(ds) >= 2:
                groups.append(dict(
                    bid=b['bid'], cx=round(b['cx'], 1), cy=round(b['cy'], 1),
                    w=round(b['w'], 1), h=round(b['h'], 1),
                    area_m2=round(b['area_m2']), n=len(ds),
                    hh_ids=sorted(d['hh_id'] for d in ds), cv=False,
                    kind='apartment' if len(ds) >= APT_MIN_N else 'split'))

        # cv-группы: дропы вне OSM, кластеризуем конечные точки
        cv_groups = []
        used = [False] * len(orphans)
        for i, d in enumerate(orphans):
            if used[i]:
                continue
            px, py = d['poly'][-1]
            mem = [d]
            used[i] = True
            for j in range(i + 1, len(orphans)):
                if used[j]:
                    continue
                qx, qy = orphans[j]['poly'][-1]
                if math.hypot(px - qx, py - qy) <= CV_GROUP_TOL_M / mpp:
                    mem.append(orphans[j])
                    used[j] = True
            if len(mem) >= 2:
                cv_groups.append(dict(
                    bid=f'cv_{d["hh_id"]}', cx=round(px, 1), cy=round(py, 1),
                    w=0, h=0, area_m2=0, n=len(mem),
                    hh_ids=sorted(m['hh_id'] for m in mem), cv=True,
                    kind='apartment' if len(mem) >= APT_MIN_N else 'split'))

        all_g = groups + cv_groups
        apt = [g for g in all_g if g['kind'] == 'apartment']
        n_dh_hidden = sum(g['n'] for g in apt)
        save_json(vdir / 'mzd_groups.json', all_g)
        grand[key] = dict(groups=len(all_g), apt_groups=len(apt),
                          dh_hidden=n_dh_hidden, drops=len(net['drops']),
                          orphans=len(orphans))
        print(f'{key:18s} дропов {len(net["drops"]):4d} | вне-OSM {len(orphans):3d} | '
              f'групп {len(all_g):3d} из них МЖД {len(apt):3d} | '
              f'ДХ под значками МЖД {n_dh_hidden}')
        if key == 'altaiskiy':
            for g in sorted(apt, key=lambda g: -g['n']):
                print(f'    МЖД bid={g["bid"]} ({g["w"]:.0f}x{g["h"]:.0f} м, '
                      f'S={g["area_m2"]} м2): n={g["n"]} cv={g["cv"]}')
    print()
    print('ИТОГО ВКО: МЖД-значков', sum(g['apt_groups'] for g in grand.values()),
          '| ДХ под значками', sum(g['dh_hidden'] for g in grand.values()),
          '| всех дропов', sum(g['drops'] for g in grand.values()))
    save_json(BASE / 'work' / 'mzd_audit.json', grand)


if __name__ == '__main__':
    main()
