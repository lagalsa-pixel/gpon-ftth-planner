# -*- coding: utf-8 -*-
"""
Шаг 2e. Уточнение bbox для Пригородного и Алтайского: связный рост от центра камеры
по OSM-зданиям (шаг <=260 м) в пределах допустимой зоны; +300 м запас.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json

def pad(bbox, m, lat):
    pl = m / 111320; po = m / (111320 * math.cos(math.radians(lat)))
    return [bbox[0] - po, bbox[1] - pl, bbox[2] + po, bbox[3] + pl]

def bbox_of(pts):
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    return [min(lons), min(lats), max(lons), max(lats)]

def grow(key, hard_zone, hop=260, seed_r=300):
    v = [x for x in VILLAGES if x['key'] == key][0]
    d = load_json(f'{vdir(key)}/osm.json')
    blds = [tuple(b['center']) for b in d['buildings']
            if hard_zone[0] <= b['center'][1] <= hard_zone[2] and hard_zone[1] <= b['center'][0] <= hard_zone[3]]
    clat, clon = v['lat'], v['lon']
    def dm(p, q):
        return math.hypot((p[0]-q[0])*111320, (p[1]-q[1])*111320*math.cos(math.radians(p[0])))
    # seed
    pts = [p for p in blds if math.hypot((p[0]-clat)*111320, (p[1]-clon)*111320*math.cos(math.radians(clat))) < seed_r]
    if not pts:
        pts = [min(blds, key=lambda p: math.hypot((p[0]-clat)*111320, (p[1]-clon)*111320))]
    rest = [p for p in blds if p not in pts]
    changed = True
    while changed and rest:
        changed = False
        add = []
        for p in rest:
            if any(dm(p, q) < hop for q in pts):
                add.append(p)
        if add:
            pts.extend(add)
            rest = [p for p in rest if p not in add]
            changed = True
    return v, pts, rest

# Пригородное: жёсткая зона по VLM (колонки E..H-край, строки 3..5)
zone_p = [83.5115, 50.3209, 83.5477, 50.3498]
v, pts, rest = grow('prigorodnoe', zone_p)
fb = pad(bbox_of(pts), 300, v['lat'])
w = (fb[2]-fb[0])*111320*math.cos(math.radians(v['lat']))/1000; h = (fb[3]-fb[1])*111320/1000
print(f"Пригородное: связный массив {len(pts)} зданий (за зоной/отрезано: {len(rest)}), bbox {fb[0]:.4f},{fb[1]:.4f}-{fb[2]:.4f},{fb[3]:.4f} ({w:.2f}x{h:.2f} км)")

# Алтайский: зона вокруг камеры +-2 км (долина) с ростом
zone_a = [82.3300, 50.2300, 82.3750, 50.2650]
v, pts, rest = grow('altaiskiy', zone_a, hop=300, seed_r=350)
fb = pad(bbox_of(pts), 300, v['lat'])
w = (fb[2]-fb[0])*111320*math.cos(math.radians(v['lat']))/1000; h = (fb[3]-fb[1])*111320/1000
print(f"Алтайский: связный массив {len(pts)} зданий (отрезано: {len(rest)}), bbox {fb[0]:.4f},{fb[1]:.4f}-{fb[2]:.4f},{fb[3]:.4f} ({w:.2f}x{h:.2f} км)")

final = load_json('/home/z/my-project/work/bboxes_final.json')
for key, fbx in (('prigorodnoe', fb),):
    pass
save_json(f'{vdir("prigorodnoe")}/bbox_grow.json', dict(bbox=[round(x, 6) for x in fb], n=len(pts)))
save_json(f'{vdir("altaiskiy")}/bbox_grow.json', dict(bbox=[round(x, 6) for x in fb], n=len(pts)))
