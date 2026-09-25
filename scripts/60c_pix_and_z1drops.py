#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60c: пиксельный разбор скриншота altay3 (img_9_p1.png).
Найти: квадрат ДХ (его точный цвет и размер), жёлтый дроп (направление),
муфту, кабель. Плюс все зоны-1 дропы Алтайского (включая вне-OSM дома)."""
import json, math, sys, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
import cv2
import numpy as np

def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
Tree, nkey = de28.Tree, de28.nkey
DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}
KEY = 'altaiskiy'


def part1_screenshot():
    img = cv2.imread(f'{BASE}/work/altay3/img_9_p1.png')
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    # насыщенные цветные блобы (квадраты ДХ, кабели, дропы)
    m = (s > 120) & (v > 80)
    # синие/тёмно-синие пиксели (квадрат зоны 1 = (25,113,194) BGR(194,113,25))
    blue = m & (h > 100) & (h < 130) & (s > 140)
    # жёлтые (дроп)
    yellow = m & (h > 20) & (h < 35)
    # циан (муфта)
    cyan = m & (h > 80) & (h < 100)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(
        (blue * 255).astype(np.uint8), 8)
    print('== синие блобы (квадраты/кабель) ==')
    for i in range(1, n):
        x, y, w2, hh, a = stats[i]
        if a < 60:
            continue
        mask = (lab == i)
        bgr = img[mask].mean(axis=0).astype(int)
        # однородность цвета
        std = img[mask].std(axis=0).mean()
        print(f'  blob{i}: bbox=({x},{y},{w2}x{hh}) area={a} '
              f'rgb=({bgr[2]},{bgr[1]},{bgr[0]}) std={std:.0f}')
    n2, lab2, st2, c2 = cv2.connectedComponentsWithStats(
        (yellow * 255).astype(np.uint8), 8)
    print('== жёлтые (дропы) ==')
    for i in range(1, n2):
        x, y, w2, hh, a = st2[i]
        if a < 100:
            continue
        ys, xs = np.where(lab2 == i)
        print(f'  y-blob{i}: bbox=({x},{y},{w2}x{hh}) area={a} '
              f'from({xs.min()},{ys.min()}) to({xs.max()},{ys.max()})')
    n3, lab3, st3, c3 = cv2.connectedComponentsWithStats(
        (cyan * 255).astype(np.uint8), 8)
    print('== циан (муфты) ==')
    for i in range(1, n3):
        x, y, w2, hh, a = st3[i]
        if a < 40:
            continue
        print(f'  c-blob{i}: bbox=({x},{y},{w2}x{hh}) area={a}')
    return 0


def part2_zone1_drops():
    v = next(v for v in de28.VILLAGES if v['key'] == KEY)
    db = DBY[KEY]
    t = Tree(v)
    cuts = [tuple(l['node']) for l in db['cut_log']]
    cutset_ = set(cuts)
    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cutset_ else zr[t.parent[u]]
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
    z1 = order[0]

    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
    mpp = geo['mpp']
    osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
    # bbox всех OSM зданий
    blds = []
    for b in osm['buildings']:
        pts = [((lo - geo['west']) * 111320 * math.cos(math.radians(la)) / mpp,
                (geo['north'] - la) * 111320 / mpp) for la, lo in b['poly']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        blds.append(dict(bid=b['id'], x0=min(xs), x1=max(xs),
                         y0=min(ys), y1=max(ys),
                         tags=b.get('tags', {}), area=b.get('area', 0)))

    z1_drops = [d for d in net['drops'] if zone_of_drop(d) == z1]
    print(f'\n== {KEY}: зон {len(cuts)}+ЦУ; зона 1 = {zone_dh[z1]} ДХ, '
          f'дропов зоны 1: {len(z1_drops)} ==')
    out = []
    for d in z1_drops:
        ex, ey = d['poly'][-1]
        c = coupler_by_node[d['coupler']]
        # ближайшее OSM здание
        best = None
        for b in blds:
            dx = max(b['x0'] - ex, ex - b['x1'], 0)
            dy = max(b['y0'] - ey, ey - b['y1'], 0)
            dist = math.hypot(dx, dy) * mpp
            if best is None or dist < best[0]:
                best = (dist, b)
        dist, b = best
        w_m = (b['x1'] - b['x0']) * mpp
        h_m = (b['y1'] - b['y0']) * mpp
        L, Wd = max(w_m, h_m), min(w_m, h_m)
        coup_south = c['y'] > ey
        out.append(dict(
            hh_id=d['hh_id'], ex=round(ex), ey=round(ey),
            coupler=dict(label=c['label'], x=round(c['x']), y=round(c['y'])),
            drop_len=round(d['length_m'], 1),
            coup_north=not coup_south,
            nearest_bld=dict(bid=b['bid'], dist_m=round(dist, 1),
                             L=round(L, 1), W=round(Wd, 1), ar=round(L / Wd, 2),
                             rot='H' if w_m > h_m else 'V',
                             lv=b['tags'].get('building:levels'),
                             area=round(b['area'], 1))))
    # сортировка: дроп с севера (муфта выше), здание близко и горизонтальное
    def score(r):
        nb = r['nearest_bld']
        s = 0
        s += 3 if r['coup_north'] else 0
        s += 3 if nb['dist_m'] < 12 else (1 if nb['dist_m'] < 25 else 0)
        s += 2 if nb['rot'] == 'H' else 0
        s += 2 if nb['ar'] >= 2.0 else (1 if nb['ar'] >= 1.5 else 0)
        return -s
    for r in sorted(out, key=score):
        nb = r['nearest_bld']
        print(f"  hh{r['hh_id']} sq=({r['ex']},{r['ey']}) coup {r['coupler']['label']}"
              f"({r['coupler']['x']},{r['coupler']['y']})"
              f" {'СВЕРХУ' if r['coup_north'] else 'снизу'} "
              f"len={r['drop_len']}м | блия={nb['bid']} {nb['dist_m']}м "
              f"{nb['L']}x{nb['W']} {nb['rot']} ar={nb['ar']} "
              f"lv={nb['lv']} S={nb['area']}")
    json.dump(out, open(f'{BASE}/work/altay3/t60_z1drops.json', 'w'),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    part1_screenshot()
    part2_zone1_drops()
