# -*- coding: utf-8 -*-
"""
Шаг 52 (прототип). Проверка CV-критериев сплита на Пригородном:
- кейс hh215 (пользователь) должен попасть в кандидаты;
- подсчёт кандидатов A (сплит полигона), B (кластерный), C (многоэтажки);
- диагностические кропы нескольких кандидатов и некандидатов.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, save_json
import numpy as np
import cv2
from importlib import import_module

BASE = '/home/z/my-project'
lib = import_module('52_hh_refine_lib')


def render_crop(mos, poly_list, mpp, path, labels=None, pad_m=18):
    """Кроп с полигонами (px мозаики) для VLM/диагностики."""
    allpts = [p for poly in poly_list for p in poly]
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    pad = pad_m / mpp
    x0 = int(max(0, min(xs) - pad)); y0 = int(max(0, min(ys) - pad))
    x1 = int(min(mos.shape[1], max(xs) + pad)); y1 = int(min(mos.shape[0], max(ys) + pad))
    crop = mos[y0:y1, x0:x1].copy()
    UP = 3
    crop = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_LANCZOS4)
    for i, poly in enumerate(poly_list):
        pts = np.array([[(p[0] - x0) * UP, (p[1] - y0) * UP] for p in poly], dtype=np.int32)
        cv2.polylines(crop, [pts], True, (255, 60, 60), 3)
        if labels:
            cx = int(np.mean([p[0] for p in poly]) - x0) * UP
            cy = int(np.mean([p[1] for p in poly]) - y0) * UP
            cv2.putText(crop, labels[i], (cx - 20, cy - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 60, 60), 2, cv2.LINE_AA)
    cv2.imwrite(path, crop)
    return path


def main():
    key = 'prigorodnoe'
    R = lib.reproduce_04f(key)
    mos, mpp, blds = R['mos'], R['mpp'], R['blds']
    print(f'{key}: зданий {len(blds)}, кластеров-ДХ {len(R["yards_hh"])}')

    candA, candB, candC = [], [], []
    nA_tested = 0
    for yinfo in R['yards_hh']:
        yard, hid, mi = yinfo['yard'], yinfo['hh_id'], yinfo['main']
        main_b = blds[mi]
        # --- A: сплит главного здания по хроматике ---
        area_m2 = main_b['w'] * main_b['h'] * mpp * mpp
        if area_m2 >= lib.MIN_POLY_M2 and hid is not None:
            nA_tested += 1
            info = lib.roof_split_info(mos, main_b['poly'], mpp)
            if info:
                candA.append(dict(hh_id=hid, bld=mi, area_m2=round(area_m2, 1), **info))
        # --- B: кластер с 2+ дом-размерными зданиями ---
        bigs = [j for j in yard
                if blds[j]['w'] * blds[j]['h'] * mpp * mpp >= lib.CLUSTER_BLD_M2]
        if len(bigs) >= 2:
            pairs = []
            for a in range(len(bigs)):
                for b in range(a + 1, len(bigs)):
                    ba, bb = blds[bigs[a]], blds[bigs[b]]
                    d = math.hypot(ba['cx'] - bb['cx'], ba['cy'] - bb['cy']) * mpp
                    if d >= lib.B_MIN_SEP_M:
                        pairs.append((bigs[a], bigs[b], round(d, 1)))
            if pairs:
                # хроматика крыш каждого крупного здания
                chromas = {}
                for j in bigs:
                    ch = lib.roof_chroma(mos, blds[j]['poly'], mpp)
                    if ch:
                        chromas[j] = ch
                candB.append(dict(hh_id=hid, yard=list(yard), bigs=bigs, pairs=pairs,
                                  chromas={str(j): [round(x, 1) for x in c]
                                           for j, c in chromas.items()}))

    # --- C: многоэтажки по всем OSM-зданиям в зоне ---
    for j, b in enumerate(blds):
        if b['src'] != 'osm':
            continue
        t = b.get('tags', {})
        try:
            lv = float(t.get('building:levels', 1) or 1)
        except ValueError:
            lv = 1
        area_m2 = b['w'] * b['h'] * mpp * mpp
        is_ms = (t.get('building') == 'apartments'
                 or (lv >= 3)
                 or (lv >= lib.MS_LEVELS_MIN and area_m2 >= lib.MS_AREA_MIN)
                 or (area_m2 >= lib.MS_AREA_ANY))
        if is_ms:
            candC.append(dict(bld=j, area_m2=round(area_m2, 1), lv=lv,
                              tag=t.get('building'), name=t.get('name', '')))

    print(f'A (сплит полигона): {len(candA)} кандидатов (тестировали {nA_tested} полигонов >= {lib.MIN_POLY_M2:.0f} м²)')
    print(f'B (кластерный сплит): {len(candB)} кандидатов')
    print(f'C (многоэтажки): {len(candC)} кандидатов')

    # кейс пользователя
    for c in candA:
        if c['hh_id'] == 215:
            print('КЕЙС hh215 ПОПАЛ В КАНДИДАТЫ:', json.dumps(c, ensure_ascii=False))
    if not any(c['hh_id'] == 215 for c in candA):
        print('!!! КЕЙС hh215 НЕ НАЙДЕН — критерии надо ослаблять')

    # диагностические кропы: первые 6 кандидатов A + hh215 + 2 примера "не кандидата"
    os.makedirs(f'{BASE}/work/hh2_proto', exist_ok=True)
    shown = 0
    for c in candA:
        if shown >= 6 and c['hh_id'] != 215:
            continue
        b = blds[c['bld']]
        render_crop(mos, [b['poly']], mpp, f'{BASE}/work/hh2_proto/A_hh{c["hh_id"]}.png',
                    labels=[f'hh{c["hh_id"]} dE={c["dE_ab"]}'])
        shown += 1
        if shown > 8:
            break
    # некандидаты для контроля FP-фильтров (обычные двускатные дома)
    nonc = 0
    for yinfo in R['yards_hh']:
        if yinfo['hh_id'] is None:
            continue
        b = blds[yinfo['main']]
        if b['w'] * b['h'] * mpp * mpp < lib.MIN_POLY_M2:
            continue
        if any(c['hh_id'] == yinfo['hh_id'] for c in candA):
            continue
        info = lib.roof_split_info(mos, b['poly'], mpp)
        if info is None:
            render_crop(mos, [b['poly']], mpp, f'{BASE}/work/hh2_proto/NEG_hh{yinfo["hh_id"]}.png')
            nonc += 1
            if nonc >= 3:
                break
    for c in candC:
        b = blds[c['bld']]
        render_crop(mos, [b['poly']], mpp, f'{BASE}/work/hh2_proto/C_{c["tag"]}_{c["area_m2"]:.0f}m2_lv{c["lv"]:.0f}.png',
                    labels=[f'{c["tag"]}/lv{c["lv"]:.0f}'])
    print('кропы: work/hh2_proto/')
    save_json(f'{BASE}/work/hh2_proto/prigorodnoe_cands.json',
              dict(candA=candA, candB=[dict(hh_id=c['hh_id']) for c in candB], candC=candC))


if __name__ == '__main__':
    main()
