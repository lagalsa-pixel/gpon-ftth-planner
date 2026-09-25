#!/usr/bin/env python3
"""Task 53 (v2): SIFT-привязка иллюстраций к карте Алтайского, память-бережливо.

Карта даунскейлится x2 (SIFT-пирамида на 29 МП не лезет в 3.4 ГБ),
каждый фрагмент пробуется в 3 масштабах. Координаты углов возвращаются
в пикселях ПОЛНОРАЗМЕРНОЙ карты.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path('/home/z/my-project')
FIGS = ROOT / 'work/altay_remarks'
MAP = ROOT / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg'

CAPTIONS = {
    'fig-001-000.png': 'R1: два многоэтажных жилых дома',
    'fig-002-001.png': 'R2: тоже многоэтажные жилые дома',
    'fig-003-002.png': 'R3/R4: многоэтажные или не идентифицированы',
    'fig-003-003.png': 'R4/R3: не идентифицированы или многоэтажные',
    'fig-004-004.png': 'R5/R6: фундамент или по два ДХ',
    'fig-004-005.png': 'R6/R5: по два ДХ или фундамент',
}
FIG_SCALES = [1.0, 0.5, 0.25, 2.0]
MAP_DOWN = 2  # карта делится на этот фактор


def match_at(fig_gray, map_gray, mask=None):
    sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.04)
    k1, d1 = sift.detectAndCompute(fig_gray, None)
    k2, d2 = sift.detectAndCompute(map_gray, None)
    if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
        return None
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return {'good': len(good), 'inliers': 0}
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None:
        return {'good': len(good), 'inliers': 0}
    return {'good': len(good), 'inliers': int(msk.sum()), 'H': H,
            'kp_fig': len(k1)}


def main():
    map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
    H_full, W_full = map_full.shape
    print(f'map full: {W_full}x{H_full}')
    map_half = cv2.resize(map_full, (W_full // MAP_DOWN, H_full // MAP_DOWN),
                          interpolation=cv2.INTER_AREA)
    print(f'map half: {map_half.shape[1]}x{map_half.shape[0]}')

    results = []
    for name in sorted(CAPTIONS):
        p = FIGS / name
        fig0 = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if fig0 is None:
            print(f'{name}: read FAIL')
            continue
        h0, w0 = fig0.shape
        best = None
        for s in FIG_SCALES:
            if s == 1.0:
                fig = fig0
            else:
                fig = cv2.resize(fig0, (int(w0 * s), int(h0 * s)),
                                 interpolation=cv2.INTER_AREA if s < 1
                                 else cv2.INTER_CUBIC)
            if min(fig.shape) < 40:
                continue
            r = match_at(fig, map_half)
            if r is None:
                continue
            print(f'  {name} scale={s}: good={r["good"]} inl={r["inliers"]}')
            if r['inliers'] >= 8 and (best is None
                                      or r['inliers'] > best['inliers']):
                best = {**r, 'fig_scale': s, 'fig_sz': fig.shape[::-1]}

        rec = {'fig': name, 'caption': CAPTIONS[name]}
        if best and best['inliers'] >= 8:
            hh, ww = best['fig_sz']
            # corners в half-координатах -> полные
            H = best['H']
            corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                                  [0, hh]]).reshape(-1, 1, 2)
            proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) * MAP_DOWN
            rec.update(status='MATCHED', inliers=best['inliers'],
                       good=best['good'], fig_scale=best['fig_scale'],
                       corners_map_px=np.round(proj, 1).tolist())
            c = rec['corners_map_px']
            print(f"{name}: MATCHED inl={best['inliers']} "
                  f"corners={[(round(x), round(y)) for x, y in c]}")
        else:
            rec.update(status='NO_MATCH')
            print(f'{name}: NO_MATCH')
        results.append(rec)

    out = FIGS / 'fig_match_map.json'
    json.dump(results, open(out, 'w'), ensure_ascii=False, indent=1)
    print('saved:', out)


if __name__ == '__main__':
    sys.exit(main())
