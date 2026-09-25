#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60b: кандидаты «многоквартирный дом» в селе Алтайский (правка
заказчика altay3: здание ИЗ АЛТАЙСКОГО, а не Пригородного — Task 59 был
ложным срабатыванием из-за сэмпла цвета без сдвига шапки +300px).

Методика (по скриншоту altay3 + VLM-разбору 60a):
  - вытянутое здание ~3:1, горизонтальное;
  - тёмно-синий квадрат зоны 1 (PALETTE[0], крупнейшая НЕ-ЦУ зона) БЕЗ бейджа;
  - дроп идёт от муфты СВЕРХУ (север) ВНИЗ к квадрату у здания;
  - кабель проходит севернее здания;
  - 1-3 ДХ у здания (квадрат на скриншоте один, но кроп мог обрезать).

Зоны воспроизводятся ТОЧНО как в рендере 48b (zr/zone_of_drop/PALETTE).
Выход: work/altay3/t60_candidates.json + кропы work/altay3/t60_cand_<bid>.png
"""
import json, math, os, sys, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
HH_OFFSET = 300          # шапка карты: HH = S(150), k=2 => 300 px (не забыть!)

def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
Tree, nkey = de28.Tree, de28.nkey

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}
PALETTE = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
           (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
           (160, 90, 44)]


def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)


def main():
    v = next(v for v in de28.VILLAGES if v['key'] == KEY)
    db = DBY[KEY]
    t = Tree(v)
    cuts = [tuple(l['node']) for l in db['cut_log']]
    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cutset(cuts) else zr[t.parent[u]]

    net = json.load(open(f'{BASE}/work/{KEY}/network_hh3.json'))
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    coupler_by_node = {c['node']: c for c in net['couplers']}

    def zone_of_drop(d):
        kk = ck.get(d['coupler'])
        if kk is None or kk not in zr:
            return t.root
        return zr[kk]

    zone_dh = defaultdict(int)
    for node, dh in t.homes.items():
        zone_dh[zr[node]] += dh
    order = sorted(cuts, key=lambda c: -zone_dh[c])
    z1 = order[0]                      # зона 1 = PALETTE[0]
    print(f'зона 1 (PALETTE[0]): узел {z1}, ДХ={zone_dh[z1]}; всего зон {len(cuts)}+ЦУ')

    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
    mpp = geo['mpp']
    osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
    drops = net['drops']

    # билдинг по bbox
    cands = []
    for b in osm['buildings']:
        pts = [geo_to_px(la, lo, geo['west'], geo['north'], mpp)
               for la, lo in b['poly']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w_m, h_m = (x1 - x0) * mpp, (y1 - y0) * mpp
        L, Wd = max(w_m, h_m), min(w_m, h_m)
        if Wd < 6 or L < 25 or L > 140 or L / Wd < 2.0:
            continue
        tol = 15.0 / mpp
        near = []
        for d in drops:
            ex, ey = d['poly'][-1]
            dx = max(x0 - ex, ex - x1, 0)
            dy = max(y0 - ey, ey - y1, 0)
            if math.hypot(dx, dy) <= tol:
                near.append(d)
        if not (1 <= len(near) <= 3):
            continue
        # зона каждого дропа
        zones = [zone_of_drop(d) for d in near]
        has_z1 = z1 in zones
        # геометрия по скриншоту: дроп зоны-1 идёт СВЕРХХУ ВНИЗ (муфта севернее
        # квадрата), квадрат у ПРАВОГО края горизонтального здания
        geom_ok = False
        z1_drop = None
        if has_z1:
            z1_drop = near[zones.index(z1)]
            ex, ey = z1_drop['poly'][-1]
            c = coupler_by_node[z1_drop['coupler']]
            coup_north = c['y'] < ey            # муфта выше (севернее) квадрата
            bld_h = w_m > h_m
            right_part = ex > (x0 + x1) / 2 - 0.1 * (x1 - x0)
            geom_ok = coup_north and bld_h and right_part
        cands.append(dict(
            bid=b['id'], cx=round((x0 + x1) / 2), cy=round((y0 + y1) / 2),
            x0=round(x0), x1=round(x1), y0=round(y0), y1=round(y1),
            L=round(L, 1), W=round(Wd, 1), ar=round(L / Wd, 2),
            area=round(b.get('area', 0), 1),
            lv=b.get('tags', {}).get('building:levels'),
            n_dh=len(near), hh_ids=[d['hh_id'] for d in near],
            zones=[('Z1' if z == z1 else ('CU' if z == t.root else f'Z{order.index(z)+1}'))
                   for z in zones],
            drop_lens=[round(d['length_m'], 1) for d in near],
            has_z1=has_z1, geom_ok=geom_ok,
            rot='H' if w_m > h_m else 'V'))

    print(f'\nкандидатов (вытянутые 1-3 ДХ): {len(cands)}')
    for c in sorted(cands, key=lambda c: (not (c['has_z1'] and c['geom_ok']),
                                          not c['has_z1'], -c['L'])):
        flag = ' <<<' if (c['has_z1'] and c['geom_ok']) else (' <<Z1' if c['has_z1'] else '')
        print(f"  bid={c['bid']} {c['L']}x{c['W']} ar={c['ar']} {c['rot']} "
              f"n_dh={c['n_dh']} zones={c['zones']} hh={c['hh_ids']} "
              f"drop={c['drop_lens']} lv={c['lv']} S={c['area']}{flag}")
    json.dump(dict(zone1_node=list(z1), zone1_dh=zone_dh[z1],
                   n_zones=len(cuts), candidates=cands),
              open(f'{BASE}/work/altay3/t60_candidates.json', 'w'),
              ensure_ascii=False, indent=1)
    return 0


def cutset(cuts):
    return set(cuts)


if __name__ == '__main__':
    sys.exit(main())
