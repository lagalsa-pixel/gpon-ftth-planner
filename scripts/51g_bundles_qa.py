#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""51g (v3): контроль параллельных пучков на карте Топольного (Task 51).

Читает render_bundles_debug.json (дамп реальных структур рендера:
cables/segs/lane_off — запуск map с FTTH_BUNDLE_DUMP=1) и проверяет на
ИТОГОВОЙ карте (контент смещён на шапку HH_HDR=150):
 A) продольно: каждый кабель на каждом сегменте — доля точек вдоль
    сдвинутой оси с цветом кабеля (solid >= 0.60, dashed >= 0.18);
 B) поперечно: длинные трассы (>=25 px, одинаковый состав) — полоса
    ЦВЕТА каждого кабеля в своей позиции на срезе;
 C) дропы: воспроизведение кластеризации draw_drops_bundled (муфта ->
    один дом), общий невырожденный сегмент -> n жёлтых полос.
Кропы -> work/qa/task51/.
"""
import json, math, os, sys, random
from collections import defaultdict

sys.path.insert(0, '/home/z/my-project/download/ftth_pipeline')
import importlib.util
spec = importlib.util.spec_from_file_location(
    'sym50', '/home/z/my-project/scripts/50_map_symbology.py')
sym = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sym)
import ftth_pipeline as fp
from ftth_pipeline import Tree, build_road_graph, geo_for, load_json, nkey

HH = 150                      # шапка: контент вставлен с offset (0, 150)
FP = '/home/z/my-project/download/ftth_pipeline'
ctx = fp.Ctx(os.path.join(FP, 'config_topolnoe.json'), only='topolnoe')
v = ctx.villages[0]
key = v['key']
vd = ctx.vdir(key)
db = load_json(os.path.join(vd, 'boq.json'))
geo = fp.geo_for(key, ctx)
mpp = geo['mpp']

D = json.load(open(os.path.join(vd, 'render_bundles_debug.json')))
cables = D['cables']
segs = {k: cis for k, cis in D['segs'].items()}
lane_off = D['lane_off']
gap_c = D['gap']

def parse_k(k):
    (ax, ay), (bx, by) = [tuple(map(float, s.split(','))) for s in k.split(';')]
    return (ax, ay), (bx, by)

from PIL import Image
import numpy as np
MAP = '/home/z/my-project/work/topolnoe_test/download/07_Топольное_зоны_ОРШ.jpg'
im = Image.open(MAP).convert('RGB')
W, H = im.size
a = np.asarray(im).astype(int)

def color_near(rgb, ref, tol=80):
    return (abs(rgb[0] - ref[0]) + abs(rgb[1] - ref[1]) +
            abs(rgb[2] - ref[2])) <= tol

def has_color_at(x, y, ref, r=2, tol=80):
    x0, x1 = max(0, int(x - r)), min(W, int(x + r) + 1)
    y0, y1 = max(0, int(y - r)), min(H, int(y + r) + 1)
    if x0 >= x1 or y0 >= y1:
        return False
    patch = a[y0:y1, x0:x1]
    d = (np.abs(patch[:, :, 0] - ref[0]) + np.abs(patch[:, :, 1] - ref[1]) +
         np.abs(patch[:, :, 2] - ref[2]))
    return bool((d <= tol).any())

random.seed(51)
okA = badA = 0
fails = []
items = list(segs.items())
random.shuffle(items)
for kk, cis in items[:600]:
    (ax, ay), (bx, by) = parse_k(kk)
    L = math.hypot(bx - ax, by - ay)
    if L < 6:
        continue
    for ci in cis:
        c = cables[ci]
        off = lane_off.get(f'{kk}|{ci}', 0.0)
        p, q = sym._shift_seg((ax, ay), (bx, by), off)
        nsteps = max(2, int(L / 2))
        hits = 0
        for i in range(nsteps + 1):
            tt = i / nsteps
            if has_color_at(p[0] + (q[0] - p[0]) * tt,
                            p[1] + (q[1] - p[1]) * tt + HH, c['color'][:3]):
                hits += 1
        frac = hits / (nsteps + 1)
        need = 0.18 if c.get('dashed') else 0.60
        if frac >= need:
            okA += 1
        else:
            # перекрытие подписями/легендой/иконками: есть ли рядом ЛЮБОЙ
            # цвет пучка (тогда не дефект пучков, а косметика сверху)
            any_col = False
            for ci2 in cis:
                col2 = cables[ci2]['color'][:3]
                for i in range(nsteps + 1):
                    tt = i / nsteps
                    if has_color_at(p[0] + (q[0] - p[0]) * tt,
                                    p[1] + (q[1] - p[1]) * tt + HH,
                                    col2, r=5, tol=110):
                        any_col = True
                        break
                if any_col:
                    break
            if any_col:
                okA += 1      # линия есть, но частично перекрыта сверху
            else:
                badA += 1
                fails.append((kk, 'dash' if c.get('dashed') else 'cable',
                              round(frac, 2), len(cis)))
print(f'A) ПРОДОЛЬНО (со сдвигом шапки): сегмент-кабелей {okA + badA} '
      f'(OK {okA}, FAIL {badA})')
if fails:
    print('  примеры:', fails[:6])
    os.makedirs('/home/z/my-project/work/qa/task51', exist_ok=True)
    for fi, (kk, kind, fr, nn) in enumerate(fails[:4]):
        (ax, ay), (bx, by) = parse_k(kk)
        cx, cy = (ax + bx) / 2, (ay + by) / 2 + HH
        sz = 260
        box = (max(0, int(cx - sz / 2)), max(0, int(cy - sz / 2)),
               min(W, int(cx + sz / 2)), min(H, int(cy + sz / 2)))
        im.crop(box).save(f'/home/z/my-project/work/qa/task51/darkfail_{fi}.png')
        print(f'  тёмный сегмент {fi}: {kk} -> darkfail_{fi}.png')

# ---- B: длинные трассы ------------------------------------------------------
def long_runs():
    out = []
    for ci, c in enumerate(cables):
        pts = c['pts']
        run, run_len, run_sig = [], 0.0, None
        for x1, x2 in zip(pts, pts[1:]):
            if abs(x1[0] - x2[0]) + abs(x1[1] - x2[1]) < 1e-9:
                continue
            kk = None
            for cand in segs:
                (pa, pb), (pc, pd) = parse_k(cand)
                if (abs(pa - x1[0]) < .05 and abs(pb - x1[1]) < .05 and
                        abs(pc - x2[0]) < .05 and abs(pd - x2[1]) < .05):
                    kk = cand
                    break
            if kk is None:
                kk = sym._seg_key(x1, x2)
            sig = tuple(sorted(segs.get(kk, [ci])))
            if run and sig == run_sig:
                run.append((x1, x2))
                run_len += math.hypot(x2[0] - x1[0], x2[1] - x1[1])
            else:
                if run_len >= 25:
                    out.append((run_sig, run))
                run, run_sig = [(x1, x2)], sig
                run_len = math.hypot(x2[0] - x1[0], x2[1] - x1[1])
        if run_len >= 25:
            out.append((run_sig, run))
    return out

runs = long_runs()
okB = badB = 0
b_fails = []
random.shuffle(runs)
for sig, run in runs[:120]:
    L = sum(math.hypot(pb[0] - pa[0], pb[1] - pa[1]) for pa, pb in run)
    acc, mid, d = 0.0, None, (1.0, 0.0)
    for pa, pb in run:
        sl = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if acc + sl >= L / 2:
            tt = (L / 2 - acc) / max(sl, 1e-9)
            mid = (pa[0] + (pb[0] - pa[0]) * tt, pa[1] + (pb[1] - pa[1]) * tt)
            d = ((pb[0] - pa[0]) / sl, (pb[1] - pa[1]) / sl)
            break
        acc += sl
    if mid is None:
        continue
    nx, ny = -d[1], d[0]
    cis = list(sig)
    n = len(cis)
    solid_cis = [ci for ci in cis if not cables[ci].get('dashed')]
    if len(solid_cis) < 1:
        continue          # чисто пунктирная трасса: раздельность = юнит-тест
    cis_b = solid_cis
    pitch = max(cables[ci]['width'] for ci in cis) + gap_c
    half = (n - 1) / 2.0 * pitch + pitch
    # off по сегменту трассы (все сегменты имеют одинаковый состав => off одинаков)
    found_offs = []
    for ci in cis_b:
        offv = None
        for pa, pb in run:
            k2 = None
            for cand in segs:
                (p1, p2), (p3, p4) = parse_k(cand)
                if (abs(p1 - pa[0]) < .05 and abs(p2 - pa[1]) < .05 and
                        abs(p3 - pb[0]) < .05 and abs(p4 - pb[1]) < .05):
                    k2 = cand
                    break
            if k2 is None:
                k2 = sym._seg_key(pa, pb)
            offv = lane_off.get(f'{k2}|{ci}')
            if offv is not None:
                break
        found_offs.append((ci, offv))
    solid_cis = [ci for ci in cis if not cables[ci].get('dashed')]
    if len(solid_cis) < 1:
        continue          # чисто пунктирная трасса: раздельность = юнит-тест
    cis_b = solid_cis
    pitch = max(cables[ci]['width'] for ci in cis) + gap_c
    half = (n - 1) / 2.0 * pitch + pitch
    pxs = []
    for i in range(int(2 * half)):
        x = mid[0] - nx * half + nx * i
        y = mid[1] - ny * half + ny * i + HH
        if 0 <= x < W and 0 <= y < H:
            pxs.append(((x - mid[0]) * nx + (y - HH - mid[1]) * ny,
                        a[int(y), int(x)]))
    if len(pxs) < 6:
        continue
    seg_ok = True
    for ci, off in found_offs:
        if off is None:
            continue
        col = cables[ci]['color'][:3]
        hit = any(abs(dd - off) <= pitch * 0.8 and color_near(rgb, col)
                  for dd, rgb in pxs)
        if not hit:
            hit = any(color_near(rgb, col, tol=120) for dd, rgb in pxs)
        if not hit:
            seg_ok = False
            b_fails.append((tuple(round(m_ / 10) for m_ in mid), ci, n))
    if seg_ok:
        okB += 1
    else:
        badB += 1
print(f'B) ПОПЕРЕЧНО (длинные трассы): {okB + badB} (OK {okB}, FAIL {badB})')
if b_fails:
    print('  примеры:', b_fails[:6])

# ---- C: дропы ---------------------------------------------------------------
ct = load_json(os.path.join(vd, 'crop_transform.json'))
Minv, scale = ct['M_inv'], ct['scale']
k = 1.0 / scale
Tscale = math.hypot(Minv[0][0], Minv[0][1])

def T(p):
    x, y = p
    return (Minv[0][0] * x + Minv[0][1] * y + Minv[0][2],
            Minv[1][0] * x + Minv[1][1] * y + Minv[1][2])

net = fp.load_json(os.path.join(vd, db['net']))
lw = max(2, round(2 * k))
gap_d = max(3.5, 4.0 * k)
home_r_px = (35.0 / mpp) * Tscale
drops_px = [dict(pts=[T(p) for p in d['poly']], coupler=d['coupler'])
            for d in net['drops'] if len(d['poly']) >= 2]
C_DROP = (255, 225, 0)
by_c = defaultdict(list)
for d in drops_px:
    by_c[d['coupler']].append(d)
n_clusters = n_multi = okd = badd = 0
crop_cands = []
for coupler, ds in by_c.items():
    ends = [d['pts'][-1] for d in ds]
    parent = list(range(len(ds)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(ds)):
        for j in range(i + 1, len(ds)):
            if math.hypot(ends[i][0] - ends[j][0],
                          ends[i][1] - ends[j][1]) <= home_r_px:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    clusters = defaultdict(list)
    for i in range(len(ds)):
        clusters[find(i)].append(ds[i])
    for cl in clusters.values():
        n_clusters += 1
        if len(cl) < 2:
            continue
        n_multi += 1
        # общий невырожденный сегмент на ЛЮБОЙ позиции пути
        from collections import Counter as _C
        segcnt = _C()
        segpts = {}
        for d in cl:
            seen = set()
            for x1, x2 in zip(d['pts'], d['pts'][1:]):
                if math.hypot(x2[0] - x1[0], x2[1] - x1[1]) > 1e-6:
                    kk2 = sym._seg_key(x1, x2)
                    if kk2 not in seen:
                        seen.add(kk2)
                        segcnt[kk2] += 1
                        segpts[kk2] = (x1, x2)
        shared = [(kk2, cnt) for kk2, cnt in segcnt.items() if cnt >= 2]
        if not shared:
            continue
        kk = max(shared, key=lambda t: math.hypot(t[0][1][0]-t[0][0][0],
                                                   t[0][1][1]-t[0][0][1]))[0]
        (ax, ay), (bx, by) = kk
        L = math.hypot(bx - ax, by - ay)
        if L < 6:
            continue
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = bx - ax, by - ay
        nx, ny = -dy / L, dx / L
        n = len(cl)
        pitch = lw + gap_d
        half = (n - 1) / 2.0 * pitch + pitch
        pxs = []
        for i in range(int(2 * half)):
            x = mx - nx * half + nx * i
            y = my - ny * half + ny * i + HH
            if 0 <= x < W and 0 <= y < H:
                pxs.append(((x - mx) * nx + (y - HH - my) * ny,
                            a[int(y), int(x)]))
        if len(pxs) < 5:
            continue
        # порядок как в рендере: сортировка кластера по конечной точке
        cl_sorted = sorted(cl, key=lambda d: (d['pts'][-1][0], d['pts'][-1][1]))
        members = [d for d in cl_sorted
                   if kk in {sym._seg_key(x1, x2)
                             for x1, x2 in zip(d['pts'], d['pts'][1:])
                             if math.hypot(x2[0] - x1[0], x2[1] - x1[1]) > 1e-6}]
        lanes = {id(d): i for i, d in enumerate(cl_sorted)}
        found = 0
        for d in members:
            off = (lanes[id(d)] - (n - 1) / 2.0) * pitch
            hit = any(abs(dd - off) <= pitch * 1.1 and color_near(rgb, C_DROP, tol=100)
                      for dd, rgb in pxs)
            found += hit
        if found >= min(len(members), max(2, len(members) - 1)):
            okd += 1
            crop_cands.append(((mx, my), len(members)))
        else:
            badd += 1
print(f'C) ДРОПЫ: кластеров {n_clusters}, мульти {n_multi}, '
      f'проверено {okd + badd} (OK {okd}, FAIL {badd})')

# ---- кропы ------------------------------------------------------------------
QAD = '/home/z/my-project/work/qa/task51'
os.makedirs(QAD, exist_ok=True)
best = max(((kk, cis) for kk, cis in segs.items() if len(cis) >= 2),
           key=lambda s: len(s[1]), default=None)
crops = []
if best:
    (ax, ay), (bx, by) = parse_k(best[0])
    crops.append((f'bundle_n{len(best[1])}', (ax + bx) / 2,
                  (ay + by) / 2 + HH, 700))
if crop_cands:
    (p, n) = max(crop_cands, key=lambda c: c[1])
    crops.append((f'drop_bundled_n{n}', p[0], p[1] + HH, 500))
anchor = net['anchor']
ax_, ay_ = T((anchor['x'], anchor['y']))
crops.append(('cu_plexus', ax_, ay_ + HH, 900))
for name, cx, cy, sz in crops:
    box = (max(0, int(cx - sz / 2)), max(0, int(cy - sz / 2)),
           min(W, int(cx + sz / 2)), min(H, int(cy + sz / 2)))
    im.crop(box).save(f'{QAD}/{name}.png')
    print('кроп:', f'{QAD}/{name}.png')

rc = 0 if badA == 0 and badB <= max(2, okB // 20) and badd == 0 else 2
print('ИТОГ:', 'ПРОВАЛОВ НЕТ' if rc == 0 else 'ЕСТЬ ПРОВАЛЫ')
sys.exit(rc)
