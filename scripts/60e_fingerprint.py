#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60e: геометрический отпечаток скриншота altay3 по ДАННЫМ (без пикселей):
  - квадрат зоны 1 (крупнейшая НЕ-ЦУ зона Алтайского);
  - дроп: короткая ~10-22 м, муфта почти строго СЕВЕРНЕЕ квадрата
    (|dx| < 6 м), последний сегмент вертикальный вниз;
  - квадрат НЕ скрыт МЖД-значком (иначе на карте значок, а не квадрат);
  - муфта ТЕРМИНАЛЬНАЯ: фидер не продолжается восточнее муфты
    (на скриншоте кабель идёт запада и обрывается на муфте);
  - здание: горизонтальное, вытянутое ~2-4:1, L 25-60 м, квадрат у
    южного края в восточной части.
Вывод: шорт-лист + кропы карты 06 вокруг каждого кандидата (с шапкой +300!)."""
import json, math, sys, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
HH = 300
ZOOM = 1.55           # оценка: квадрат 25/17, муфта 34/21, дроп 7/4.3

def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
Tree, nkey = de28.Tree, de28.nkey
DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}


def main():
    v = next(v for v in de28.VILLAGES if v['key'] == KEY)
    db = DBY[KEY]
    t = Tree(v)
    cuts = [tuple(l['node']) for l in db['cut_log']]
    cs = set(cuts)
    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cs else zr[t.parent[u]]
    net = json.load(open(f'{BASE}/work/{KEY}/network_hh3.json'))
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    cbn = {c['node']: c for c in net['couplers']}

    def zone_of_drop(d):
        kk = ck.get(d['coupler'])
        if kk is None or kk not in zr:
            return t.root
        return zr[kk]

    zone_dh = defaultdict(int)
    for node, dh in t.homes.items():
        zone_dh[zr[node]] += dh
    order = sorted(cuts, key=lambda c: -zone_dh[c])
    z1 = order[0]

    # МЖД-скрытые квадраты
    hidden = set()
    mg = json.load(open(f'{BASE}/work/{KEY}/mzd_groups.json'))
    for g in mg:
        if g.get('kind') == 'apartment':
            hidden.update(g['hh_ids'])

    # граф фидера: соседние муфты по рёбрам
    adj = defaultdict(set)
    for e in net['feeder_edges']:
        a = (round(e[0][0], 1), round(e[0][1], 1))
        b = (round(e[1][0], 1), round(e[1][1], 1))
        adj[a].add(b)
        adj[b].add(a)

    mpp = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]['mpp']
    osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
    blds = []
    for b in osm['buildings']:
        pts = [((lo - 0) * 0, 0) for la, lo in b['poly']]
        # мозаичные координаты через geo
        geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
        pts = [((lo - geo['west']) * 111320 * math.cos(math.radians(la)) / mpp,
                (geo['north'] - la) * 111320 / mpp) for la, lo in b['poly']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        blds.append(dict(bid=b['id'], x0=min(xs), x1=max(xs), y0=min(ys),
                         y1=max(ys), area=b.get('area', 0),
                         lv=b.get('tags', {}).get('building:levels')))

    z1_drops = [d for d in net['drops'] if zone_of_drop(d) == z1]
    print(f'зона 1: {len(z1_drops)} дропов (скрытых МЖД в зоне 1: '
          f'{sum(1 for d in z1_drops if d["hh_id"] in hidden)})')

    shortlist = []
    for d in z1_drops:
        if d['hh_id'] in hidden:
            continue
        ex, ey = d['poly'][-1]
        c = cbn[d['coupler']]
        dx, dy = ex - c['x'], ey - c['y']
        dist = math.hypot(dx, dy)
        # муфта севернее, почти на одной вертикали
        north_col = (dy > 8) and (abs(dx) * mpp < 6.0)
        if not north_col:
            continue
        # дроп 10-22 м
        if not (8.0 <= d['length_m'] <= 24.0):
            continue
        # терминальность: нет соседней муфты/продолжения фидера восточнее
        kk = (round(c['x'], 1), round(c['y'], 1))
        east_cont = any(b[0] > c['x'] + 6 for b in adj.get(kk, ()))
        # здание рядом с квадратом
        best = None
        for b in blds:
            ddx = max(b['x0'] - ex, ex - b['x1'], 0)
            ddy = max(b['y0'] - ey, ey - b['y1'], 0)
            dd = math.hypot(ddx, ddy) * mpp
            if best is None or dd < best[0]:
                best = (dd, b)
        dd, b = best
        w_m = (b['x1'] - b['x0']) * mpp
        h_m = (b['y1'] - b['y0']) * mpp
        L, Wd = max(w_m, h_m), min(w_m, h_m)
        shortlist.append(dict(
            hh_id=d['hh_id'], sq=(round(ex), round(ey)),
            coup=dict(label=c['label'], x=round(c['x']), y=round(c['y'])),
            drop_len=round(d['length_m'], 1), dist_c2s=round(dist * mpp, 1),
            east_cont=east_cont, bld=dict(bid=b['bid'], dist_m=round(dd, 1),
                                          L=round(L, 1), W=round(Wd, 1),
                                          ar=round(L / Wd, 2),
                                          rot='H' if w_m > h_m else 'V',
                                          lv=b['lv'], area=round(b['area'], 1),
                                          x0=round(b['x0']), x1=round(b['x1']),
                                          y0=round(b['y0']), y1=round(b['y1']))))

    print(f'\nшорт-лист (муфта севернее, |dx|<6м, дроп 8-24м): {len(shortlist)}')
    for r in sorted(shortlist, key=lambda r: (r['east_cont'],
                                              r['bld']['dist_m'])):
        b = r['bld']
        print(f"  hh{r['hh_id']} sq={r['sq']} {r['coup']['label']}"
              f"{(r['coup']['x'], r['coup']['y'])} c2s={r['dist_c2s']}м "
              f"len={r['drop_len']}м фидерВосток={'ДА' if r['east_cont'] else 'нет'} | "
              f"bld {b['bid']} {b['dist_m']}м {b['L']}x{b['W']} {b['rot']} "
              f"ar={b['ar']} lv={b['lv']} S={b['area']}")
    json.dump(shortlist, open(f'{BASE}/work/altay3/t60_shortlist.json', 'w'),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
