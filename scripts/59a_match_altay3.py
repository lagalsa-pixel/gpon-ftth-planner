#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59a: привязка img altay3 (1 изображение, 459x339) к 6 картам v8.
Методика 55b: FLANN + RANSAC + NCC-варп, 4 поворота, масштабы 1/2/4."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay3'
FIG = DIR / 'img_9_p1.png'
MAPS = {k: DIR / f'map{k:02d}_v8.jpg' for k in range(1, 7)}
ONLY = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else list(MAPS)
MAP_DOWN = 4 if 3 in ONLY or 4 in ONLY else 2


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def main():
    fig0 = cv2.imread(str(FIG), cv2.IMREAD_GRAYSCALE)
    h0, w0 = fig0.shape
    print(f'fig {w0}x{h0}', flush=True)
    sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.02)
    flann = cv2.FlannBasedMatcher(
        dict(algorithm=1, trees=5), dict(checks=64))
    results = {}
    if (DIR / 'fig_match.json').exists():
        results = json.load(open(DIR / 'fig_match.json'))
    for mk in ONLY:
        mpath = MAPS[mk]
        map_full = cv2.imread(str(mpath), cv2.IMREAD_GRAYSCALE)
        Hf, Wf = map_full.shape
        map_half = cv2.resize(map_full, (Wf // MAP_DOWN, Hf // MAP_DOWN),
                              interpolation=cv2.INTER_AREA)
        k2, d2 = sift.detectAndCompute(map_half, None)
        best = None
        variants = {'raw': fig0,
                    'rotCW': cv2.rotate(fig0, cv2.ROTATE_90_CLOCKWISE),
                    'rotCCW': cv2.rotate(fig0, cv2.ROTATE_90_COUNTERCLOCKWISE),
                    'rot180': cv2.rotate(fig0, cv2.ROTATE_180)}
        for vname, vimg in variants.items():
            for s in (0.5, 0.75, 1.0, 1.5, 2.0):
                hh0, ww0 = vimg.shape
                fig = cv2.resize(vimg, (max(2, int(ww0 * s)),
                                        max(2, int(hh0 * s))),
                                 interpolation=cv2.INTER_CUBIC)
                if min(fig.shape) < 40:
                    continue
                k1, d1 = sift.detectAndCompute(fig, None)
                if d1 is None or len(k1) < 8:
                    continue
                matches = flann.knnMatch(d1, d2, k=2)
                good = [m for m, n in matches
                        if m.distance < 0.75 * n.distance]
                if len(good) < 8:
                    continue
                src = np.float32([k1[m.queryIdx].pt
                                  for m in good]).reshape(-1, 1, 2)
                dst = np.float32([k2[m.trainIdx].pt
                                  for m in good]).reshape(-1, 1, 2)
                H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
                if H is None or int(msk.sum()) < 8:
                    continue
                inl = int(msk.sum())
                hh, ww = fig.shape
                corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                                      [0, hh]]).reshape(-1, 1, 2)
                proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2) \
                    * MAP_DOWN
                x0, y0 = proj.min(axis=0)
                x1, y1 = proj.max(axis=0)
                if x0 < -20 or y0 < -20 or x1 > Wf + 20 or y1 > Hf + 20:
                    continue
                wR, hR = int(round(x1 - x0)), int(round(y1 - y0))
                if wR < 30 or hR < 30 or wR > Wf or hR > Hf:
                    continue
                ar_fig = max(ww, hh) / max(1, min(ww, hh))
                ar_reg = max(wR, hR) / max(1, min(wR, hR))
                if abs(ar_fig - ar_reg) / max(ar_fig, ar_reg) > 0.35:
                    continue
                W2, H2 = map_half.shape[1], map_half.shape[0]
                warped_half = cv2.warpPerspective(
                    fig, H, (W2, H2), flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=128)
                cx0, cy0 = int(x0) // MAP_DOWN, int(y0) // MAP_DOWN
                cx1, cy1 = int(x1) // MAP_DOWN + 1, int(y1) // MAP_DOWN + 1
                wh = warped_half[cy0:cy1, cx0:cx1]
                if wh.size < 400:
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
                if m.sum() < 400:
                    continue
                score = ncc(warped[m], crop[m])
                cand = dict(map=mk, variant=vname, scale=s, inliers=inl,
                            ncc=round(score, 3),
                            region=[round(float(x0)), round(float(y0)),
                                    round(float(x1)), round(float(y1))])
                if score >= 0.30 and (best is None or (score, inl) >
                                      (best['ncc'], best['inliers'])):
                    best = cand
        if best:
            results[str(mk)] = best
            print(f'map{mk:02d}: BEST {best["variant"]} s={best["scale"]} '
                  f'inl={best["inliers"]} ncc={best["ncc"]} '
                  f'region={best["region"]}', flush=True)
        else:
            print(f'map{mk:02d}: NO VALID MATCH', flush=True)
        del map_full, map_half, k2, d2
        import gc
        gc.collect()
    json.dump(results, open(DIR / 'fig_match.json', 'w'),
              ensure_ascii=False, indent=1)
    print('saved fig_match.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
