# -*- coding: utf-8 -*-
"""
Шаг 2d. Финальные bbox всех сёл:
- Солнечное: + безымянные кластеры, смежные (<=500 м) с именованными 'Солнечное'
- Пригородное: зона E-G / стр.3-5 по VLM-разметке вокруг центра камеры
- Алтайский: основной линейный массив (отсечение одиночек перцентили)
- остальные: как в 02b
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json

def pad(bbox, m, lat):
    pl = m / 111320; po = m / (111320 * math.cos(math.radians(lat)))
    return [bbox[0] - po, bbox[1] - pl, bbox[2] + po, bbox[3] + pl]

def clusters_of(d, size_m=250.0):
    grid = {}
    for b in d['buildings']:
        la, lo = b['center']
        gk = (round(la / (size_m / 111320)), round(lo / (size_m / (111320 * math.cos(math.radians(la))))))
        grid.setdefault(gk, []).append((la, lo))
    return grid

def bbox_of(pts):
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    return [min(lons), min(lats), max(lons), max(lats)]

final = {}
for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    blds = [b['center'] for b in d['buildings']]
    if key == 'prigorodnoe':
        # зона села по VLM: колонки E..G (83.5115..83.5477), строки 3..5 (50.3209..50.3498),
        # но строки 3 ограничим снизу 50.3402 только для колонок E..F; берём компактную зону
        zone = [83.5115, 50.3209, 83.5477, 50.3450]
        pts = [(la, lo) for la, lo in blds if zone[0] <= lo <= zone[2] and zone[1] <= la <= zone[3]]
        fb = pad(bbox_of(pts), 300, v['lat'])
    elif key == 'solnechnoe':
        grid = clusters_of(d)
        # именованные ранее: ядра Солнечного; добавим безымянные кластеры в пределах 600 м от любого здания ядра
        core = load_json(f'{vdir(key)}/bbox_final.json')['bbox']
        core_pts = [(la, lo) for la, lo in blds
                    if core[0] - 0.005 <= lo <= core[2] + 0.005 and core[1] - 0.005 <= la <= core[3] + 0.005]
        def near_core(pt, dist=600):
            for la, lo in core_pts:
                if math.hypot((la - pt[0]) * 111320, (lo - pt[1]) * 111320 * math.cos(math.radians(la))) < dist:
                    return True
            return False
        pts = [p for p in blds if near_core(p)]
        # расширение: кластеры вдоль юго-западного направления (само село вытянуто)
        changed = True
        while changed:
            changed = False
            for p in blds:
                if p in pts:
                    continue
                if any(math.hypot((q[0]-p[0])*111320, (q[1]-p[1])*111320*math.cos(math.radians(p[0]))) < 450
                       for q in pts):
                    pts.append(p); changed = True
        fb = pad(bbox_of(pts), 300, v['lat'])
    elif key == 'altaiskiy':
        # основной массив: кластеры >=3 зданий, отсечь хвосты (перцентиль 1..99 по каждой оси)
        grid = clusters_of(d)
        pts = [p for gk, ps in grid.items() if len(ps) >= 3 for p in ps]
        lons = sorted(p[1] for p in pts); lats = sorted(p[0] for p in pts)
        n = len(lons)
        lo0, lo1 = lons[int(0.005 * n)], lons[int(0.995 * n)]
        la0, la1 = lats[int(0.005 * n)], lats[int(0.995 * n)]
        pts = [p for p in pts if lo0 <= p[1] <= lo1 and la0 <= p[0] <= la1]
        fb = pad(bbox_of(pts), 300, v['lat'])
    else:
        fb = load_json(f'{vdir(key)}/bbox_final.json')['bbox']

    w = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(v['lat'])) / 1000
    h = (fb[3] - fb[1]) * 111320 / 1000
    nb = sum(1 for la, lo in blds if fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3])
    final[key] = dict(bbox=[round(x, 6) for x in fb], n_osm_bld=nb)
    print(f"{v['name']}: bbox {fb[0]:.4f},{fb[1]:.4f} - {fb[2]:.4f},{fb[3]:.4f}  ({w:.2f} x {h:.2f} км), зданий OSM в bbox: {nb} / {v['hh']} ДХ")

save_json('/home/z/my-project/work/bboxes_final.json', final)
