#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55f: усиленный матчинг img_10 — маскирование синей аннотации
заказчика + template/SIFT на полное разрешение карты."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay2'
MAP = DIR / 'map06_v4.jpg'


def ncc(a, b):
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def mask_blue(img_bgr):
    """Заменяем насыщенно-синие пиксели (аннотация) средним окружения."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    # синий: hue ~100..130 (OpenCV 0..179), насыщенный
    m = ((h >= 95) & (h <= 135) & (s > 90)).astype(np.uint8) * 255
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    out = img_bgr.copy()
    if m.sum() == 0:
        return out, 0
    mean_color = cv2.mean(img_bgr, mask=cv2.bitwise_not(m))[:3]
    out[m > 0] = [int(c) for c in mean_color]
    return out, int((m > 0).sum())


def main():
    fig = cv2.imread(str(DIR / 'img_10.png'))  # BGR
    fig_m, nblue = mask_blue(fig)
    print(f'синих пикселей замаскировано: {nblue}')
    cv2.imwrite(str(DIR / 'img_10_masked.png'), fig_m)

    map_full = cv2.imread(str(MAP))
    map_gray = cv2.cvtColor(map_full, cv2.COLOR_BGR2GRAY)
    Hf, Wf = map_gray.shape

    best = None
    # --- template matching: апскейл 2..8 против full map (может быть долго,
    #     поэтому против map в 1/2, потом уточняем в окне) ---
    map_half = cv2.resize(map_gray, (Wf // 2, Hf // 2),
                          interpolation=cv2.INTER_AREA)
    fig_g = cv2.cvtColor(fig_m, cv2.COLOR_BGR2GRAY)
    h0, w0 = fig_g.shape
    for s in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]:
        tpl = cv2.resize(fig_g, (int(w0 * s / 2), int(h0 * s / 2)),
                         interpolation=cv2.INTER_CUBIC)
        if min(tpl.shape) < 20 or tpl.shape[0] >= map_half.shape[0] \
                or tpl.shape[1] >= map_half.shape[1]:
            continue
        r = cv2.matchTemplate(map_half, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        region = [loc[0] * 2, loc[1] * 2,
                  (loc[0] + tpl.shape[1]) * 2, (loc[1] + tpl.shape[0]) * 2]
        print(f'  tpl s={s}: peak={mx:.3f} region={region}')
        if best is None or mx > best[0]:
            best = (float(mx), s, region)

    if best and best[0] >= 0.40:
        print(f'BEST tpl: peak={best[0]:.3f} s={best[1]} region={best[2]}')
        # уточняющее SIFT в окне +-400 px
        x0, y0, x1, y1 = best[2]
        pad = 400
        wx0, wy0 = max(0, x0 - pad), max(0, y0 - pad)
        wx1 = min(Wf, x1 + pad)
        wy1 = min(Hf, y1 + pad)
        win = map_gray[wy0:wy1, wx0:wx1]
        sift = cv2.SIFT_create(nfeatures=8000, contrastThreshold=0.02)
        flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5),
                                      dict(checks=64))
        for s in [2.0, 3.0, 4.0]:
            tpl = cv2.resize(fig_g, (int(w0 * s), int(h0 * s)),
                             interpolation=cv2.INTER_CUBIC)
            k1, d1 = sift.detectAndCompute(tpl, None)
            k2, d2 = sift.detectAndCompute(win, None)
            if d1 is None or d2 is None or len(k1) < 8:
                continue
            ms = flann.knnMatch(d1, d2, k=2)
            good = [m for m, n in ms if m.distance < 0.75 * n.distance]
            if len(good) < 8:
                print(f'  sift s={s}: good={len(good)} < 8')
                continue
            src = np.float32([k1[m.queryIdx].pt
                              for m in good]).reshape(-1, 1, 2)
            dst = np.float32([k2[m.trainIdx].pt
                              for m in good]).reshape(-1, 1, 2)
            H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
            if H is None or int(msk.sum()) < 8:
                print(f'  sift s={s}: inl<8')
                continue
            inl = int(msk.sum())
            hh, ww = tpl.shape
            corners = np.float32([[0, 0], [ww, 0], [ww, hh],
                                  [0, hh]]).reshape(-1, 1, 2)
            proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
            proj[:, 0] += wx0
            proj[:, 1] += wy0
            x0p, y0p = proj.min(axis=0)
            x1p, y1p = proj.max(axis=0)
            print(f'  sift s={s}: inl={inl} region='
                  f'[{x0p:.0f},{y0p:.0f},{x1p:.0f},{y1p:.0f}]')
        out = dict(peak=best[0], scale=best[1], region=best[2])
    else:
        out = None
        print('template: нет надёжного матча')

    json.dump(out, open(DIR / 'img10_match.json', 'w'), indent=1)
    print('saved img10_match.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
