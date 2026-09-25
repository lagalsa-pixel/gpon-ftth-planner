#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59b: диагностика — все гомографии fig->map06 без жёстких фильтров.
Цель: понять, на каком масштабе/повороте есть сигнатура, и не размыт ли кадр."""
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay3'
FIG = DIR / 'img_9_p1.png'
# кл < 10: работает с готовыми половинками *_half.jpg (MAP_DOWN=1)
MK = int(sys.argv[1]) if len(sys.argv) > 1 else 6
if MK in (1, 3, 4):
    MAP, MAP_DOWN = DIR / f'map{MK:02d}_half.jpg', 1
elif MK == 7:
    MAP, MAP_DOWN = DIR / 'map07_half.jpg', 1
else:
    MAP, MAP_DOWN = DIR / f'map{MK:02d}_v8.jpg', 2
SCALES = (0.25, 0.35, 0.5, 0.6, 0.75, 0.9, 1.0, 1.25, 1.5, 2.0)


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def main():
    fig0 = cv2.imread(str(FIG), cv2.IMREAD_GRAYSCALE)
    sift_f = cv2.SIFT_create(nfeatures=4000, contrastThreshold=0.02)
    k0, d0 = sift_f.detectAndCompute(fig0, None)
    print(f'fig keypoints: {len(k0)}', flush=True)

    map_full = cv2.imread(str(MAP), cv2.IMREAD_GRAYSCALE)
    Hf, Wf = map_full.shape
    map_half = cv2.resize(map_full, (Wf // MAP_DOWN, Hf // MAP_DOWN),
                          interpolation=cv2.INTER_AREA)
    sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.02)
    k2, d2 = sift.detectAndCompute(map_half, None)
    print(f'map_half {map_half.shape}: {len(k2)} kp', flush=True)
    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5),
                                  dict(checks=64))

    variants = {'raw': fig0,
                'rotCW': cv2.rotate(fig0, cv2.ROTATE_90_CLOCKWISE),
                'rotCCW': cv2.rotate(fig0, cv2.ROTATE_90_COUNTERCLOCKWISE),
                'rot180': cv2.rotate(fig0, cv2.ROTATE_180)}
    for vname, vimg in variants.items():
        for s in SCALES:
            h0, w0 = vimg.shape
            fig = cv2.resize(vimg, (max(2, int(w0 * s)),
                                    max(2, int(h0 * s))),
                             interpolation=cv2.INTER_CUBIC)
            if min(fig.shape) < 30:
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
            if H is None:
                continue
            inl = int(msk.sum())
            if inl < 8:
                continue
            hh, ww = fig.shape
            corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                                  [0, hh]]).reshape(-1, 1, 2)
            proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
            x0, y0 = proj.min(axis=0)
            x1, y1 = proj.max(axis=0)
            wR, hR = x1 - x0, y1 - y0
            ar_fig = max(ww, hh) / max(1, min(ww, hh))
            ar_reg = max(wR, hR) / max(1, min(wR, hR))
            ar_dev = abs(ar_fig - ar_reg) / max(ar_fig, ar_reg)
            # мягкая проверка региона
            inside = -100 <= x0 and -100 <= y0 and \
                x1 <= Wf + 100 and y1 <= Hf + 100 and \
                wR > 15 and hR > 15
            W2, H2 = map_half.shape[1], map_half.shape[0]
            warped_half = cv2.warpPerspective(
                fig, H, (W2, H2), flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=128)
            cx0, cy0 = max(0, int(x0) // MAP_DOWN), max(0, int(y0) // MAP_DOWN)
            cx1 = min(Wf, int(x1) // MAP_DOWN + 1)
            cy1 = min(Hf, int(y1) // MAP_DOWN + 1)
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
            score = ncc(warped[m], crop[m]) if m.sum() >= 200 else 0.0
            flag = ' <== CANDIDATE' if (inl >= 10 and inside
                                        and ar_dev < 0.5) else ''
            print(f'{vname} s={s}: kp={len(k1)} good={len(good)} '
                  f'inl={inl} inside={inside} ar_dev={ar_dev:.2f} '
                  f'ncc={score:.3f} region=({x0:.0f},{y0:.0f})-'
                  f'({x1:.0f},{y1:.0f}){flag}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
