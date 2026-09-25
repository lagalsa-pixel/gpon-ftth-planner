#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55b (v2, быстрая): FLANN, s=2.0 + raw, 4 поворота.
Регион стабилен независимо от масштаба фигуры (проверено v1)."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay2'
MAP = DIR / 'map06_v4.jpg'

NAMES = ['img_9.png', 'img_10.png', 'img_11.png', 'img_12.png']
MAP_DOWN = 2


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def main():
    map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
    Hf, Wf = map_full.shape
    map_half = cv2.resize(map_full, (Wf // MAP_DOWN, Hf // MAP_DOWN),
                          interpolation=cv2.INTER_AREA)

    sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02)
    k2, d2 = sift.detectAndCompute(map_half, None)
    print(f'map_half {map_half.shape}: {len(k2)} kp', flush=True)
    flann = cv2.FlannBasedMatcher(
        dict(algorithm=1, trees=5), dict(checks=64))

    results = {}
    for name in NAMES:
        fig0 = cv2.imread(str(DIR / name), cv2.IMREAD_GRAYSCALE)
        variants = {'raw': fig0,
                    'rotCW': cv2.rotate(fig0, cv2.ROTATE_90_CLOCKWISE),
                    'rotCCW': cv2.rotate(fig0, cv2.ROTATE_90_COUNTERCLOCKWISE),
                    'rot180': cv2.rotate(fig0, cv2.ROTATE_180)}
        best = None
        for vname, vimg in variants.items():
            for s in ([1.0, 2.0] if min(vimg.shape) >= 100 else [2.0, 4.0]):
                h0, w0 = vimg.shape
                fig = cv2.resize(vimg, (max(2, int(w0 * s)),
                                        max(2, int(h0 * s))),
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
                cand = dict(variant=vname, scale=s, inliers=inl,
                            good=len(good), ncc=round(score, 3),
                            region=[round(float(x0)), round(float(y0)),
                                    round(float(x1)), round(float(y1))])
                print(f'  {name} {vname} s={s}: inl={inl} ncc={score:.3f} '
                      f'region={cand["region"]}', flush=True)
                if best is None or (score, inl) > (best['ncc'],
                                                   best['inliers']):
                    if score >= 0.30:
                        best = cand
        if best:
            results[name] = best
            print(f'{name}: BEST {best["variant"]} s={best["scale"]} '
                  f'inl={best["inliers"]} ncc={best["ncc"]} '
                  f'region={best["region"]}', flush=True)
        else:
            results[name] = None
            print(f'{name}: NO VALID MATCH', flush=True)
        sys.stdout.flush()

    json.dump(results, open(DIR / 'fig_match.json', 'w'),
              ensure_ascii=False, indent=1)
    print('saved fig_match.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
