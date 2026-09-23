# -*- coding: utf-8 -*-
"""Прототип detect_bbox v2: замыкание сетки + компоненты с порогом застройки.

Проверка на: Бобровка (линейное село, проблема v1) + ВКО эталоны (bboxes_final.json).
"""
import json
import math
from collections import Counter

BASE = '/home/z/my-project'
URBAN_ROADS = {'residential', 'living_street', 'service', 'unclassified', 'road', 'tertiary', 'secondary'}


def detect_bbox_v2(lat_c, lon_c, roads, buildings, probe, grid_m=50.0, margin_m=300.0,
                   close_cells=3, min_bld=15, keep_frac=0.65):
    feats = []
    for r in roads:
        if r['hw'] in URBAN_ROADS:
            feats.extend(r['pts'])
    n_road_pts = len(feats)
    feats.extend([b['center'] for b in buildings])
    if not feats:
        return list(probe)
    lats = [p[0] for p in feats]
    lons = [p[1] for p in feats]
    dlat = grid_m / 111320.0
    dlon = grid_m / (111320.0 * math.cos(math.radians(lat_c)))

    def cell_of(la, lo):
        return (int(math.floor((la - min(lats)) / dlat)),
                int(math.floor((lo - min(lons)) / dlon)))

    # ячейки: >=1 объекта (здания + точки городских дорог)
    filled = set()
    for la, lo in feats:
        filled.add(cell_of(la, lo))
    # здания по ячейкам (для подсчёта застройки компоненты)
    bcnt = Counter(cell_of(b['center'][0], b['center'][1]) for b in buildings)

    # замыкание: дилатация close_cells, компоненты, эрозия обратно не нужна для bbox
    dil = set()
    for (r_, c_) in filled:
        for dr in range(-close_cells, close_cells + 1):
            for dc in range(-close_cells, close_cells + 1):
                if dr * dr + dc * dc <= close_cells * close_cells + 1:
                    dil.add((r_ + dr, c_ + c_))

    # компоненты связности по dil
    seen = set()
    comps = []
    for cell in dil:
        if cell in seen:
            continue
        stack = [cell]
        comp = set()
        while stack:
            x = stack.pop()
            if x in seen or x not in dil:
                continue
            seen.add(x)
            comp.add(x)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    stack.append((x[0] + dr, x[1] + dc))
        comps.append(comp)

    # застройка компоненты = здания в её исходных ячейках (filled ∩ comp)
    def comp_buildings(comp):
        return sum(bcnt.get(c2, 0) for c2 in comp if c2 in filled)

    # фильтр: застройка и близость к точке заказа
    probe_half_w = (probe[2] - probe[0]) * 111320.0 * math.cos(math.radians(lat_c)) / 2
    probe_half_h = (probe[3] - probe[1]) * 111320.0 / 2
    r_max = keep_frac * math.hypot(probe_half_w, probe_half_h)
    kept = []
    for comp in comps:
        nb = comp_buildings(comp)
        if nb < min_bld:
            continue
        cla = sum((min(lats) + (c2[0] + 0.5) * dlat) for c2 in comp) / len(comp)
        clo = sum((min(lons) + (c2[1] + 0.5) * dlon) for c2 in comp) / len(comp)
        distm = math.hypot((cla - lat_c) * 111320,
                           (clo - lon_c) * 111320 * math.cos(math.radians(lat_c)))
        if distm <= r_max:
            kept.append(comp)
    if not kept:
        kept = [max(comps, key=comp_buildings)]
    cells = set().union(*kept)

    rmin = min(c2[0] for c2 in cells); rmax = max(c2[0] for c2 in cells)
    cmin = min(c2[1] for c2 in cells); cmax = max(c2[1] for c2 in cells)
    lat_min = min(lats) + rmin * dlat - margin_m / 111320.0
    lat_max = min(lats) + (rmax + 1) * dlat + margin_m / 111320.0
    lon_min = min(lons) + cmin * dlon - margin_m / (111320.0 * math.cos(math.radians(lat_c)))
    lon_max = min(lons) + (cmax + 1) * dlon + margin_m / (111320.0 * math.cos(math.radians(lat_c)))
    fb = (max(lon_min, probe[0]), max(lat_min, probe[1]),
          min(lon_max, probe[2]), min(lat_max, probe[3]))
    return list(fb), len(kept), sum(comp_buildings(c2) for c2 in kept), n_road_pts


def probe_of(lat, lon, radius):
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


print('=== Бобровка (линейное, v1 дал 0.7x0.9 км) ===')
d = json.load(open(f'{BASE}/work/bobrovka_test/work/bobrovka/osm.json'))
fb, nk, nb, nr = detect_bbox_v2(50.1677890, 82.7206420, d['roads'], d['buildings'],
                                 probe_of(50.1677890, 82.7206420, 3500))
w = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(50.1678)) / 1000
h = (fb[3] - fb[1]) * 111320 / 1000
print(f'  bbox {fb[0]:.4f},{fb[1]:.4f} - {fb[2]:.4f},{fb[3]:.4f} ({w:.2f} x {h:.2f} км),'
      f' компонент {nk}, зданий в зоне {nb}')

print('=== Эталоны ВКО (bboxes_final) ===')
bfinal = json.load(open(f'{BASE}/work/bboxes_final.json'))
geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))
VIL = [('verhneberezovka', 50.28420545, 82.20951200, 2529),
       ('solnechnoe', 50.05177550, 82.71438134, 2193),
       ('perevalnoe', 50.24139084, 82.28314297, 3081),
       ('vinnoe', 50.05844487, 82.82687999, 2853),
       ('prigorodnoe', 50.32198100, 83.52094976, 2602),
       ('altaiskiy', 50.24399825, 82.36103064, 4095)]
for key, lat, lon, rng in VIL:
    d = json.load(open(f'{BASE}/work/{key}/osm.json'))
    fb, nk, nb, nr = detect_bbox_v2(lat, lon, d['roads'], d['buildings'],
                                     probe_of(lat, lon, rng + 900))
    ref = bfinal[key]['bbox']
    w = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(lat)) / 1000
    h = (fb[3] - fb[1]) * 111320 / 1000
    # IoU с эталоном
    ix0, iy0 = max(fb[0], ref[0]), max(fb[1], ref[1])
    ix1, iy1 = min(fb[2], ref[2]), min(fb[3], ref[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    a1 = (fb[2] - fb[0]) * (fb[3] - fb[1])
    a2 = (ref[2] - ref[0]) * (ref[3] - ref[1])
    iou = inter / (a1 + a2 - inter) if (a1 + a2 - inter) > 0 else 0
    print(f'  {key:<18} v2: {w:.2f}x{h:.2f} км, комп. {nk}, зданий {nb:4d} |'
          f' IoU с эталоном {iou:.2f}')
