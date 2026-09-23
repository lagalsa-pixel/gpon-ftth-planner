# -*- coding: utf-8 -*-
"""
Шаг 52d. CV-детектор межевых заборов вдоль линии раздела сблокированных домов.

Идея: линия раздела двух владений (по хроматике крыш) ПРОДОЛЖАЕТСЯ за пределы
здания вглубь двора в виде забора (тонкая тёмная/светлая линия 1-3 px с тенью).
Детектор: вдоль продолжения линии (вне полигона здания) на каждом шаге
измеряется контраст центральных пикселей против флангов; coverage = доля
положений с контрастом выше порога.

Валидация: на Верхнеберезовке есть 100+ VLM-вердиктов (n_properties) —
сверяем CV-fence с ними, подбираем порог.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json
import numpy as np
import cv2
from importlib import import_module

BASE = '/home/z/my-project'
lib = import_module('52_hh_refine_lib')

EXT_M = 22.0        # насколько далеко за здание продолжаем линию, м
FLANK_PX = 7        # полуширина полосы анализа, px
CONTRAST_THR = 10   # порог контраста линия/фланги (0-255)
OFFSETS = (0.0, 1.5, -1.5, 3.0, -3.0)  # сдвиги линии поперёк (px) — забор не строго на линии


def line_profile(gray, cx, y0, y1, off):
    """Вертикальная линия x=cx+off на строках y0..y1: контраст по каждой строке.
    Возвращает массив score (len = y1-y0)."""
    cxr = int(round(cx + off))
    h, w = gray.shape
    if cxr - FLANK_PX < 0 or cxr + FLANK_PX >= w:
        return None
    ys = np.arange(max(0, y0), min(h, y1))
    if len(ys) < 4:
        return None
    center = gray[ys, cxr - 1:cxr + 2].mean(axis=1).astype(np.float32)
    lf = gray[ys, cxr - FLANK_PX:cxr - 3].mean(axis=1).astype(np.float32)
    rf = gray[ys, cxr + 4:cxr + FLANK_PX + 1].mean(axis=1).astype(np.float32)
    flanks = (lf + rf) / 2.0
    return np.maximum(flanks - center, center - flanks)


def col_profile(gray, cy, x0, x1, off):
    """Горизонтальная линия y=cy+off на столбцах x0..x1."""
    cyr = int(round(cy + off))
    h, w = gray.shape
    if cyr - FLANK_PX < 0 or cyr + FLANK_PX >= h:
        return None
    xs = np.arange(max(0, x0), min(w, x1))
    if len(xs) < 4:
        return None
    center = gray[cyr - 1:cyr + 2, xs].mean(axis=0).astype(np.float32)
    lf = gray[cyr - FLANK_PX:cyr - 3, xs].mean(axis=0).astype(np.float32)
    rf = gray[cyr + 4:cyr + FLANK_PX + 1, xs].mean(axis=0).astype(np.float32)
    flanks = (lf + rf) / 2.0
    return np.maximum(flanks - center, center - flanks)


def fence_score(mos_rgb, poly, axis, t, mpp):
    """Оценка забора вдоль продолжения линии раздела.
    axis=0: линия x = t*W (вертикальная), забор тянется по y за пределы здания.
    Возвращает dict(coverage, contrast_med, n_samples) или None."""
    gray = cv2.cvtColor(mos_rgb, cv2.COLOR_RGB2GRAY)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ext = EXT_M / mpp
    best = None
    if axis == 0:
        cx = x0 + t * (x1 - x0)
        for side0, side1 in ((int(y0 - ext), int(y0)), (int(y1), int(y1 + ext))):
            for off in OFFSETS:
                sc = line_profile(gray, cx, side0, side1, off)
                if sc is None or len(sc) < 4:
                    continue
                cov = float((sc >= CONTRAST_THR).mean())
                med = float(np.median(sc)) if len(sc) else 0.0
                if best is None or cov > best[0]:
                    best = (cov, med, len(sc))
    else:
        cy = y0 + t * (y1 - y0)
        for side0, side1 in ((int(x0 - ext), int(x0)), (int(x1), int(x1 + ext))):
            for off in OFFSETS:
                sc = col_profile(gray, cy, side0, side1, off)
                if sc is None or len(sc) < 4:
                    continue
                cov = float((sc >= CONTRAST_THR).mean())
                med = float(np.median(sc)) if len(sc) else 0.0
                if best is None or cov > best[0]:
                    best = (cov, med, len(sc))
    if best is None:
        return None
    return dict(coverage=round(best[0], 2), contrast=round(best[1], 1), n=best[2])


def main():
    # --- валидация на ВБ по VLM-вердиктам ---
    key = 'verhneberezovka'
    verd = load_json(f'{BASE}/work/hh2/{key}/verdicts.json')
    cands = load_json(f'{BASE}/work/hh2/{key}/candidates.json')
    cby = {c['cid']: c for c in cands}
    R = lib.reproduce_04f(key)
    gray = cv2.cvtColor(R['mos'], cv2.COLOR_RGB2GRAY)
    mpp = R['mpp']
    rows = []
    for cid, v in verd.items():
        if not v.get('ok') or 'n_properties' not in v or cid not in cby:
            continue
        c = cby[cid]
        if c['type'] != 'A':
            continue
        cvi = c['cv']
        fs = fence_score(R['mos'], R['blds'][c['bld']]['poly'], cvi['axis'], cvi['t'], mpp)
        n = 1 if int(v['n_properties']) < 2 else 2
        rows.append(dict(cid=cid, n=n, fence_vlm=bool(v.get('fence_between')),
                         cov=fs['coverage'] if fs else 0.0,
                         con=fs['contrast'] if fs else 0.0))
    import collections
    for n in (1, 2):
        g = [r for r in rows if r['n'] == n]
        if not g:
            continue
        covs = sorted(r['cov'] for r in g)
        print(f"VLM n_prop={n}: {len(g)} шт | CV-fence coverage med={covs[len(covs)//2]:.2f} "
              f"p25={covs[int(len(covs)*0.25)]:.2f} p75={covs[int(len(covs)*0.75)]:.2f}")
    # пороги
    for thr in (0.2, 0.3, 0.4, 0.5, 0.6):
        tp = sum(1 for r in rows if r['n'] == 2 and r['cov'] >= thr)
        fn = sum(1 for r in rows if r['n'] == 2 and r['cov'] < thr)
        fp = sum(1 for r in rows if r['n'] == 1 and r['cov'] >= thr)
        tn = sum(1 for r in rows if r['n'] == 1 and r['cov'] < thr)
        print(f"cov>={thr}: сплит {tp}/{tp+fn} истинных, {fp}/{fp+tn} ложных "
              f"(precision {100*tp/max(1,tp+fp):.0f}%, recall {100*tp/max(1,tp+fn):.0f}%)")


if __name__ == '__main__':
    main()
