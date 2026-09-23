# -*- coding: utf-8 -*-
"""Шаг 2h. Фиксация ФИНАЛЬНЫХ bbox всех 6 сёл."""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json

def pad(bbox, m, lat):
    pl = m / 111320; po = m / (111320 * math.cos(math.radians(lat)))
    return [bbox[0] - po, bbox[1] - pl, bbox[2] + po, bbox[3] + pl]

def bbox_of(pts):
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    return [min(lons), min(lats), max(lons), max(lats)]

final = {}
for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    blds = [b['center'] for b in d['buildings']]
    if key == 'solnechnoe':
        # расширенный bbox из 02d (вытянутое село, включая юго-западную часть)
        fb = [82.7031, 50.0350, 82.7404, 50.0586]
        nb = sum(1 for la, lo in blds if fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3])
    elif key == 'prigorodnoe':
        R = 1100.0
        clat, clon = v['lat'], v['lon']
        pts = [(la, lo) for la, lo in blds
               if math.hypot((la-clat)*111320, (lo-clon)*111320*math.cos(math.radians(clat))) < R]
        fb = pad(bbox_of(pts), 300, v['lat'])
        nb = len(pts)
    elif key == 'altaiskiy':
        fb = load_json(f'{vdir(key)}/bbox_grow.json')['bbox']
        nb = sum(1 for la, lo in blds if fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3])
    else:
        fb = load_json(f'{vdir(key)}/bbox_final.json')['bbox']
        nb = sum(1 for la, lo in blds if fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3])
    w = (fb[2]-fb[0])*111320*math.cos(math.radians(v['lat']))/1000
    h = (fb[3]-fb[1])*111320/1000
    final[key] = dict(bbox=[round(x, 6) for x in fb], n_osm_bld=nb)
    print(f"{v['name']}: {fb[0]:.4f},{fb[1]:.4f} - {fb[2]:.4f},{fb[3]:.4f} ({w:.2f}x{h:.2f} км), OSM-зданий: {nb} / {v['hh']} ДХ")

save_json('/home/z/my-project/work/bboxes_final.json', final)
print("Сохранено: work/bboxes_final.json")
