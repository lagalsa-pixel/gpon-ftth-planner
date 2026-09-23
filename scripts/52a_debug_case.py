# -*- coding: utf-8 -*-
"""Дебаг критериев сплита на hh215 (кейс пользователя)."""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from importlib import import_module
import numpy as np
import cv2

BASE = '/home/z/my-project'
lib = import_module('52_hh_refine_lib')

R = lib.reproduce_04f('prigorodnoe')
mos, mpp, blds = R['mos'], R['mpp'], R['blds']

for hid in (215, 118, 107):
    yinfo = next(y for y in R['yards_hh'] if y['hh_id'] == hid)
    b = blds[yinfo['main']]
    poly = b['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    print(f'\n=== hh{hid}: bbox {max(xs)-min(xs):.0f}x{max(ys)-min(ys):.0f} px = '
          f'{(max(xs)-min(xs))*mpp:.1f}x{(max(ys)-min(ys))*mpp:.1f} м, area~{(max(xs)-min(xs))*(max(ys)-min(ys))*mpp*mpp:.0f} м²')
    # полный разбор без порогов
    x0, y0 = int(max(0, min(xs))), int(max(0, min(ys)))
    x1, y1 = int(max(xs)) + 1, int(max(ys)) + 1
    crop = mos[y0:y1, x0:x1]
    pts = np.array([[p[0] - x0, p[1] - y0] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    print(f'  area_px={int((mask>0).sum())} (полигон {mask.shape})')
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    v_ = hsv[..., 2]
    valid = (mask > 0) & (v_ >= 35) & (v_ <= 250)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    ys_, xs_ = np.nonzero(valid)
    data = np.column_stack([lab[ys_, xs_, 1], lab[ys_, xs_, 2]]).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(data, 2, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    for lb in (0, 1):
        sel = labels == lb
        mm = np.zeros(valid.shape, np.uint8); mm[ys_[sel], xs_[sel]] = 255
        ncc, cc = cv2.connectedComponents(mm)
        sizes = np.bincount(cc.ravel())[1:]
        print(f'  часть {lb}: n={sel.sum()} ({sel.sum()*mpp*mpp:.0f} м²), '
              f'ab=({centers[lb][0]:.1f},{centers[lb][1]:.1f}), '
              f'centroid=({xs_[sel].mean()+x0:.0f},{ys_[sel].mean()+y0:.0f}), '
              f'cc_share={sizes.max()/sel.sum():.2f}')
    dE = math.hypot(centers[0][0]-centers[1][0], centers[0][1]-centers[1][1])
    sel0 = labels == 0; sel1 = labels == 1
    cen_m = math.hypot(xs_[sel0].mean()-xs_[sel1].mean(), ys_[sel0].mean()-ys_[sel1].mean())*mpp
    print(f'  dE_ab={dE:.1f} (порог 18), centroid_m={cen_m:.1f} (порог 5)')
    # RGB средние частей — понять, какие это крыши
    for lb in (0, 1):
        sel = labels == lb
        px = crop[ys_[sel], xs_[sel]]
        print(f'  часть {lb}: средний RGB={px.mean(axis=0).round(0)}, L={lab[ys_[sel],xs_[sel],0].mean():.0f}')
    # сохранить кроп
    UP = 4
    vis = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_LANCZOS4)
    ptsu = np.array([[(p[0]-x0)*UP, (p[1]-y0)*UP] for p in poly], dtype=np.int32)
    cv2.polylines(vis, [ptsu], True, (255, 60, 60), 3)
    cv2.imwrite(f'{BASE}/work/hh2_proto/DBG_hh{hid}.png', vis)
