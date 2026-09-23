# -*- coding: utf-8 -*-
"""
Шаг 52. Генерация кандидатов уточнённой детекции ДХ (v2) по 6 сёлам.

Кандидаты трёх типов:
  A — сплит полигона по хроматике крыш (сблокированные дома, разные крыши);
  B — кластер 04f содержит 2+ дом-размерных зданий (кластеризация eps=16 м
      склеила отдельные дома одного двора... или соседние владения);
  C — многоэтажные жилые здания (apartments / levels>=2+площадь / крупный
      дом-размерный полигон) — учитываются числом квартир.

Выход: work/hh2/<key>/candidates.json + кропы cand_*.jpg для VLM-верификации.
"""
import sys, os, math, json, gc
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, save_json
import numpy as np
import cv2
from importlib import import_module

BASE = '/home/z/my-project'
lib = import_module('52_hh_refine_lib')


def render_crop(mos, polys, mpp, path, pad_m=35, note=''):
    """Кроп с полигонами (px мозаики), апскейл x3, JPEG для VLM.
    pad 35 м: межевой забор видно за пределами строений вглубь двора."""
    allpts = [p for poly in polys for p in poly]
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    pad = pad_m / mpp
    x0 = int(max(0, min(xs) - pad)); y0 = int(max(0, min(ys) - pad))
    x1 = int(min(mos.shape[1], max(xs) + pad)); y1 = int(min(mos.shape[0], max(ys) + pad))
    crop = mos[y0:y1, x0:x1].copy()
    UP = 3
    crop = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_LANCZOS4)
    for poly in polys:
        pts = np.array([[(p[0] - x0) * UP, (p[1] - y0) * UP] for p in poly], dtype=np.int32)
        cv2.polylines(crop, [pts], True, (255, 60, 60), 3)
    if note:
        cv2.putText(crop, note, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 88])


def gen_village(key):
    R = lib.reproduce_04f(key)
    mos, mpp, blds = R['mos'], R['mpp'], R['blds']
    outdir = f'{BASE}/work/hh2/{key}'
    os.makedirs(outdir, exist_ok=True)
    cands = []

    for yinfo in R['yards_hh']:
        yard, hid, mi = yinfo['yard'], yinfo['hh_id'], yinfo['main']
        main_b = blds[mi]
        # ---------- A: сплит главного здания (v3: геометрия, цвет вспомогателен) ----------
        area_m2 = main_b['w'] * main_b['h'] * mpp * mpp
        if area_m2 >= lib.MIN_BBOX_M2 and hid is not None:
            info = lib.roof_split_info(mos, main_b['poly'], mpp)
            if info:
                cid = f'A_hh{hid}'
                render_crop(mos, [main_b['poly']], mpp, f'{outdir}/cand_{cid}.jpg')
                cands.append(dict(cid=cid, type='A', hh_id=hid, bld=mi,
                                  prio=info.get('priority', 3),
                                  area_m2=round(area_m2, 1), cv=info))
        # ---------- B: 2+ дом-размерных зданий в кластере ----------
        bigs = [j for j in yard
                if blds[j]['w'] * blds[j]['h'] * mpp * mpp >= lib.CLUSTER_BLD_M2]
        if len(bigs) >= 2 and hid is not None:
            ok_pairs = []
            for a in range(len(bigs)):
                for b in range(a + 1, len(bigs)):
                    ba, bb = blds[bigs[a]], blds[bigs[b]]
                    d = math.hypot(ba['cx'] - bb['cx'], ba['cy'] - bb['cy']) * mpp
                    if d >= lib.B_MIN_SEP_M:
                        ok_pairs.append([bigs[a], bigs[b], round(d, 1)])
            if ok_pairs:
                cid = f'B_hh{hid}'
                render_crop(mos, [blds[j]['poly'] for j in bigs], mpp,
                            f'{outdir}/cand_{cid}.jpg')
                cands.append(dict(cid=cid, type='B', hh_id=hid, bld=mi,
                                  bigs=[int(j) for j in bigs], pairs=ok_pairs))

    # ---------- C: многоэтажки (все OSM-здания в зоне) ----------
    hh_pos = [(y['cx'], y['cy'], y['hh_id']) for y in R['yards_hh']]
    for j, b in enumerate(blds):
        if b['src'] != 'osm':
            continue
        t = b.get('tags', {})
        if t.get('building') not in lib.MS_HOUSE_TAGS:
            continue
        try:
            lv = float(t.get('building:levels', 1) or 1)
        except ValueError:
            lv = 1
        area_m2 = b['w'] * b['h'] * mpp * mpp
        is_ms = (t.get('building') == 'apartments' or lv >= 3
                 or (lv >= lib.MS_LEVELS_MIN and area_m2 >= lib.MS_AREA_MIN)
                 or area_m2 >= lib.MS_AREA_ANY)
        if not is_ms:
            continue
        # ближайшее ДХ (родитель для привязки к сети)
        best_hh, best_d = None, 1e9
        for cx, cy, ph in hh_pos:
            d = math.hypot(b['cx'] - cx, b['cy'] - cy) * mpp
            if d < best_d:
                best_hh, best_d = ph, d
        cid = f'C_b{j}'
        render_crop(mos, [b['poly']], mpp, f'{outdir}/cand_{cid}.jpg',
                    note=f'lv={lv:.0f} S={area_m2:.0f}m2')
        cands.append(dict(cid=cid, type='C', bld=j, hh_id=best_hh,
                          hh_dist_m=round(best_d, 1), lv=lv, area_m2=round(area_m2, 1),
                          tag=t.get('building'),
                          units=t.get('units') or t.get('apartments') or t.get('flats')))

    save_json(f'{outdir}/candidates.json', cands)
    nA = sum(1 for c in cands if c['type'] == 'A')
    nB = sum(1 for c in cands if c['type'] == 'B')
    nC = sum(1 for c in cands if c['type'] == 'C')
    p1 = sum(1 for c in cands if c.get('prio') == 1)
    p2 = sum(1 for c in cands if c.get('prio') == 2)
    p3 = sum(1 for c in cands if c.get('prio') == 3)
    print(f'{key}: A={nA} (prio 1/2/3: {p1}/{p2}/{p3}) B={nB} C={nC} всего {len(cands)} кандидатов', flush=True)
    del mos, R
    gc.collect()
    return nA, nB, nC


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    tot = [0, 0, 0]
    for v in VILLAGES:
        if only and v['key'] != only:
            continue
        r = gen_village(v['key'])
        for i in range(3):
            tot[i] += r[i]
    print(f'ИТОГО: A={tot[0]} B={tot[1]} C={tot[2]}')


if __name__ == '__main__':
    main()
