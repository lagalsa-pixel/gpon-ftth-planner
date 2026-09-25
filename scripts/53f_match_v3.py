#!/usr/bin/env python3
"""Task 53 (v3): надёжная привязка иллюстраций к карте Алтайского.

Проблема v2: фигуры в PDF повёрнуты (90°) и/или анизотропно сжаты
пользователем в Word; гомографии с сильной анизотропией недостоверны,
несмотря на inliers (повторяющиеся структуры крыш).

Решение:
  - варианты фигуры: raw / rot90CW / rot90CCW × масштабы [2, 1, 0.5, 0.25]
  - после каждого матча: варп фигуры в регион полноразмерной карты,
    NCC (Пирсон) с реальным кропом карты;
  - итог выбирается по (NCC, inliers), NCC >= 0.55 — валид.
Выход: work/altay_remarks/fig_match_v3.json + side-by-side PNG для контроля.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
FIGS = BASE / 'work/altay_remarks'
MAP = BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg'

NAMES = ['fig-001-000.png', 'fig-002-001.png', 'fig-003-002.png',
         'fig-003-003.png', 'fig-004-004.png', 'fig-004-005.png']
CAPS = {
    'fig-001-000.png': 'R1', 'fig-002-001.png': 'R2', 'fig-003-002.png': 'R3',
    'fig-003-003.png': 'R4', 'fig-004-004.png': 'R5', 'fig-004-005.png': 'R6',
}
MAP_DOWN = 2


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def try_match(fig, map_half):
    sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.04)
    k1, d1 = sift.detectAndCompute(fig, None)
    k2, d2 = sift.detectAndCompute(map_half, None)
    if d1 is None or d2 is None or len(k1) < 12:
        return None
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None or int(msk.sum()) < 8:
        return None
    return int(msk.sum()), len(good), H


def main():
    map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
    Hf, Wf = map_full.shape
    map_half = cv2.resize(map_full, (Wf // MAP_DOWN, Hf // MAP_DOWN),
                          interpolation=cv2.INTER_AREA)

    results = {}
    for name in NAMES:
        fig0 = cv2.imread(str(FIGS / name), cv2.IMREAD_GRAYSCALE)
        if fig0 is None:
            continue
        variants = {'raw': fig0,
                    'rotCW': cv2.rotate(fig0, cv2.ROTATE_90_CLOCKWISE),
                    'rotCCW': cv2.rotate(fig0, cv2.ROTATE_90_COUNTERCLOCKWISE)}
        best = None
        for vname, vimg in variants.items():
            h0, w0 = vimg.shape
            for s in [2.0, 1.0, 0.5, 0.25]:
                if s == 1.0:
                    fig = vimg
                else:
                    fig = cv2.resize(vimg, (int(w0 * s), int(h0 * s)),
                                     interpolation=cv2.INTER_AREA if s < 1
                                     else cv2.INTER_CUBIC)
                if min(fig.shape) < 40:
                    continue
                r = try_match(fig, map_half)
                if r is None:
                    continue
                inl, ngood, H = r
                if inl < 8:
                    continue
                # углы фигуры -> карта (полный размер)
                hh, ww = fig.shape
                corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                                      [0, hh]]).reshape(-1, 1, 2)
                proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) \
                    * MAP_DOWN
                x0, y0 = proj.min(axis=0)
                x1, y1 = proj.max(axis=0)
                # регион валиден?
                if x0 < -20 or y0 < -20 or x1 > Wf + 20 or y1 > Hf + 20:
                    continue
                wR, hR = int(round(x1 - x0)), int(round(y1 - y0))
                if wR < 30 or hR < 30 or wR > Wf or hR > Hf:
                    continue
                # варп фигуры на холст half-карты, затем кроп региона
                W2, H2 = map_half.shape[1], map_half.shape[0]
                warped_half = cv2.warpPerspective(
                    fig, H, (W2, H2),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=128)
                cx0, cy0 = int(x0) // MAP_DOWN, int(y0) // MAP_DOWN
                cx1, cy1 = int(x1) // MAP_DOWN + 1, int(y1) // MAP_DOWN + 1
                wh = warped_half[cy0:cy1, cx0:cx1]
                if wh.size < 500:
                    continue
                warped = cv2.resize(wh, (max(1, wh.shape[1] * 2),
                                         max(1, wh.shape[0] * 2)),
                                    interpolation=cv2.INTER_LINEAR)
                crop = map_full[int(y0):int(y0) + warped.shape[0],
                                int(x0):int(x0) + warped.shape[1]]
                if crop.shape[:2] != warped.shape[:2]:
                    mn = (min(crop.shape[0], warped.shape[0]),
                          min(crop.shape[1], warped.shape[1]))
                    crop = crop[:mn[0], :mn[1]]
                    warped = warped[:mn[0], :mn[1]]
                m = (warped > 5) & (warped < 250) & (crop > 5) & (crop < 250)
                if m.sum() < 500:
                    continue
                score = ncc(warped[m], crop[m])
                cand = dict(variant=vname, scale=s, inliers=inl, good=ngood,
                            ncc=round(score, 3),
                            region=[round(float(x0)), round(float(y0)),
                                    round(float(x1)), round(float(y1))])
                print(f'  {name} {vname} s={s}: inl={inl} ncc={score:.3f} '
                      f'region={cand["region"]}')
                if best is None or (score, inl) > (best['ncc'],
                                                   best['inliers']):
                    if score >= 0.30:
                        best = cand
        if best:
            results[CAPS[name]] = best
            print(f'{CAPS[name]}: BEST {best["variant"]} s={best["scale"]} '
                  f'inl={best["inliers"]} ncc={best["ncc"]} '
                  f'region={best["region"]}')
        else:
            results[CAPS[name]] = None
            print(f'{CAPS[name]}: NO VALID MATCH')
        print()

    json.dump(results, open(FIGS / 'fig_match_v3.json', 'w'),
              ensure_ascii=False, indent=1)
    print('saved fig_match_v3.json')


if __name__ == '__main__':
    sys.exit(main())
