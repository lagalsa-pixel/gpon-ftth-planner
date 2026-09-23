# -*- coding: utf-8 -*-
"""Прототип detect_bbox v3: только здания + замыкание сетки, дороги не участвуют.

Подбор close_cells: Бобровка (полное покрытие линейного села) + ВКО эталоны (IoU).
"""
import json
import math
from collections import Counter

BASE = '/home/z/my-project'


def detect_bbox_v3(lat_c, lon_c, buildings, probe, grid_m=50.0, margin_m=300.0,
                   close_cells=4, min_bld=15, keep_frac=0.65):
    if not buildings:
        return list(probe), 0, 0
    lats = [b['center'][0] for b in buildings]
    lons = [b['center'][1] for b in buildings]
    dlat = grid_m / 111320.0
    dlon = grid_m / (111320.0 * math.cos(math.radians(lat_c)))
    bcnt = Counter()
    for b in buildings:
        la, lo = b['center']
        bcnt[(int(math.floor((la - min(lats)) / dlat)),
              int(math.floor((lo - min(lons)) / dlon)))] += 1
    filled = set(bcnt)

    dil = set()
    for (r_, c_) in filled:
        for dr in range(-close_cells, close_cells + 1):
            for dc in range(-close_cells, close_cells + 1):
                if dr * dr + dc * dc <= close_cells * close_cells + 1:
                    dil.add((r_ + dr, c_ + dc))

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

    def comp_buildings(comp):
        return sum(bcnt.get(c2, 0) for c2 in comp if c2 in filled)

    probe_half_w = (probe[2] - probe[0]) * 111320.0 * math.cos(math.radians(lat_c)) / 2
    probe_half_h = (probe[3] - probe[1]) * 111320.0 / 2
    r_max = keep_frac * math.hypot(probe_half_w, probe_half_h)
    kept = []
    for comp in comps:
        if comp_buildings(comp) < min_bld:
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
    return list(fb), len(kept), sum(comp_buildings(c2) for c2 in kept)


def probe_of(lat, lon, radius):
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


bfinal = json.load(open(f'{BASE}/work/bboxes_final.json'))
VIL = [('verhneberezovka', 50.28420545, 82.20951200, 2529),
       ('solnechnoe', 50.05177550, 82.71438134, 2193),
       ('perevalnoe', 50.24139084, 82.28314297, 3081),
       ('vinnoe', 50.05844487, 82.82687999, 2853),
       ('prigorodnoe', 50.32198100, 83.52094976, 2602),
       ('altaiskiy', 50.24399825, 82.36103064, 4095)]

for cc in (2, 3, 4, 6):
    print(f'--- close_cells = {cc} (радиус ~{cc*50} м) ---')
    d = json.load(open(f'{BASE}/work/bobrovka_test/work/bobrovka/osm.json'))
    fb, nk, nb = detect_bbox_v3(50.1677890, 82.7206420, d['buildings'],
                                probe_of(50.1677890, 82.7206420, 3500), close_cells=cc)
    w = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(50.1678)) / 1000
    h = (fb[3] - fb[1]) * 111320 / 1000
    print(f'  Бобровка:        {w:.2f} x {h:.2f} км, компонент {nk}, зданий {nb}')
    for key, lat, lon, rng in VIL:
        d = json.load(open(f'{BASE}/work/{key}/osm.json'))
        fb, nk, nb = detect_bbox_v3(lat, lon, d['buildings'],
                                    probe_of(lat, lon, rng + 900), close_cells=cc)
        ref = bfinal[key]['bbox']
        w = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(lat)) / 1000
        h = (fb[3] - fb[1]) * 111320 / 1000
        ix0, iy0 = max(fb[0], ref[0]), max(fb[1], ref[1])
        ix1, iy1 = min(fb[2], ref[2]), min(fb[3], ref[3])
        inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        a1 = (fb[2] - fb[0]) * (fb[3] - fb[1])
        a2 = (ref[2] - ref[0]) * (ref[3] - ref[1])
        iou = inter / (a1 + a2 - inter) if (a1 + a2 - inter) > 0 else 0
        print(f'  {key:<18} {w:.2f}x{h:.2f} км, зданий {nb:4d}, IoU {iou:.2f}')
