# -*- coding: utf-8 -*-
"""
Шаг 11. Винное — перенос ИСХОДНОЙ FTTH-сети (проект шага 06 на полной мозаике)
на новый обрезанный пользователем кадр upload/04_Винное.jpg
БЕЗ перестроения топологии и БЕЗ оптимизации
(указание пользователя: «винное, солнечное оставь без изменений»).

Фазы (аргумент CLI): match | build | render | all (по умолчанию — all).
Каждая фаза запускается отдельным процессом ради экономии ОЗУ (кадр 148 Мп).

  match  — SIFT-привязка кадра к work/vinnoe/mosaic.jpg (параметры шага 08:
           DS=4, CLAHE, FLANN+RANSAC, аффинная модель) -> work/vinnoe/crop_transform.json
           NCC-проверка выполняется на уменьшенных копиях (эквивалентно, но без
           полноразмерного варпа, который не влезает в ОЗУ вместе с кадром).
  build  — work/vinnoe/network_v2.json := network.json (геометрия не меняется;
           дропам добавляется hh_id для рендера) + рамка кадра + статистика «в кадре».
           НИКАКОГО перевыбора ОРШ, перепривязки ДХ, чистки муфт.
  render — вызов 10_render_cropped.render_crop('vinnoe') ->
           download/snp_vko/04_vinnoe_ftth_crop.png (+ _fragment.png).
"""
import sys
import os
import math
import gc
import json

sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json, save_json, V, BASE  # noqa: E402

KEY = 'vinnoe'
NEW_REL = 'upload/04_Винное.jpg'
OLD_REL = f'work/{KEY}/mosaic.jpg'
DS = 4          # даунскейл для сопоставления (как в 08_match_crops)
SIFT_NF = 60000
SIFT_CT = 0.02


# ---------------------------------------------------------------- PHASE: match
def phase_match():
    import cv2
    import numpy as np

    old = cv2.imread(f'{BASE}/{OLD_REL}')
    new = cv2.imread(f'{BASE}/{NEW_REL}')
    assert old is not None and new is not None, 'imread fail'
    Ho, Wo = old.shape[:2]
    Hn, Wn = new.shape[:2]
    print(f'мозаика {Wo}x{Ho}, кадр {Wn}x{Hn} ({Wn * Hn / 1e6:.0f} Мп)')

    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    new_s = cv2.resize(new, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(old_s, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(new_s, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1, g2 = clahe.apply(g1), clahe.apply(g2)

    sift = cv2.SIFT_create(nfeatures=SIFT_NF, contrastThreshold=SIFT_CT)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    print(f'  признаки: мозаика {len(k1)}, кадр {len(k2)}')

    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
    matches = flann.knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    print(f'  хорошие пары: {len(good)}')

    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000,
                                         confidence=0.999)
    assert M is not None, 'RANSAC fail'
    ninl = int(inl.sum())
    err = np.sqrt(((cv2.transform(src, M) - dst) ** 2).sum(axis=2)[inl.ravel() == 1]).mean()
    print(f'  inliers: {ninl} ({100 * ninl / len(good):.1f}%), rms {err:.2f} px (при DS={DS})')

    # полный масштаб: old_full = S @ M @ S^-1 @ new_full, S = diag(DS, DS, 1)
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    Si = np.diag([1.0 / DS, 1.0 / DS, 1.0])
    M_full = S @ M3 @ Si
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    rot = math.degrees(math.atan2(M_full[1, 0], M_full[0, 0]))

    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)

    # NCC-проверка на уменьшенных копиях (экономия ОЗУ):
    # варпим old_s в геометрию new_s (нужен old->new в редуцированных координатах)
    Mr = np.linalg.inv(M3)
    warped_s = cv2.warpAffine(old_s, Mr[:2, :], (new_s.shape[1], new_s.shape[0]),
                              flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gw = cv2.cvtColor(warped_s, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gn = g2.astype(np.float32)
    step = 2
    a = gw[::step, ::step] - gw[::step, ::step].mean()
    b = gn[::step, ::step] - gn[::step, ::step].mean()
    ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
    print(f'  scale {scale:.4f}, rot {rot:+.3f} deg, NCC {ncc:.3f}')
    print(f'  охват кадра (px мозаики): x [{quad[:, 0].min():.0f}..{quad[:, 0].max():.0f}], '
          f'y [{quad[:, 1].min():.0f}..{quad[:, 1].max():.0f}]')

    out = dict(
        new_image=NEW_REL, new_W=Wn, new_H=Hn,
        mosaic_W=Wo, mosaic_H=Ho,
        M_full=[[float(c) for c in row] for row in M_full],      # new -> old
        M_inv=[[float(c) for c in row] for row in np.linalg.inv(M_full)[:2, :]],  # old -> new
        scale=float(scale), rot_deg=float(rot),
        quad_old=[[float(x), float(y)] for x, y in quad],
        inliers=ninl, rms_px=float(err * DS), ncc=ncc,
    )
    save_json(f'{vdir(KEY)}/crop_transform.json', out)

    # контрольная картинка: кадр | варп мозаики (уменьшенные)
    cmp_img = np.hstack([new_s[:, :, ::-1], warped_s[:, :, ::-1]])
    cv2.imwrite(f'{BASE}/work/{KEY}/match_check.png', cmp_img)
    print(f'  -> work/{KEY}/crop_transform.json, work/{KEY}/match_check.png')


# ---------------------------------------------------------------- PHASE: build
def clip_len_m(a, b, rect, mpp):
    """Длина отрезка a-b внутри прямоугольника rect (Liang-Barsky), в метрах."""
    x0, y0, x1, y1 = rect
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0.0:
            if q < 0.0:
                return 0.0
        else:
            r = q / p
            if p < 0.0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return 0.0
    return math.hypot(dx, dy) * (t1 - t0) * mpp


def phase_build():
    g = load_json(f'{BASE}/work/mosaic_geo.json')[KEY]
    t = load_json(f'{vdir(KEY)}/crop_transform.json')
    net = load_json(f'{vdir(KEY)}/network.json')
    hhs = load_json(f'{vdir(KEY)}/households.json')
    mpp = g['mpp']

    assert abs(t['rot_deg']) < 0.05, f"кадр повёрнут ({t['rot_deg']:.3f} deg) — проверить вручную"
    q = t['quad_old']
    x0, y0 = min(p[0] for p in q), min(p[1] for p in q)
    x1, y1 = max(p[0] for p in q), max(p[1] for p in q)
    rect = (x0, y0, x1, y1)
    print(f'рамка кадра в px мозаики: [{x0:.0f}..{x1:.0f}] x [{y0:.0f}..{y1:.0f}] '
          f'({(x1 - x0) * mpp / 1000:.2f} x {(y1 - y0) * mpp / 1000:.2f} км)')

    m2 = 2.0
    def inr(x, y):
        return (x0 - m2 <= x <= x1 + m2) and (y0 - m2 <= y <= y1 + m2)

    hhs_in = [h for h in hhs if inr(h['cx'], h['cy'])]
    hh_in_ids = {h['id'] for h in hhs_in}
    print(f'ДХ в кадре: {len(hhs_in)} из {len(hhs)}')

    anchor = net['anchor']
    a_in = inr(anchor['x'], anchor['y'])
    print(f"ОРШ: id={anchor['bld_id']} ({anchor['area']:.0f} м²) — "
          f"{'В КАДРЕ, сохранён' if a_in else '!!! ЗА РАМКОЙ КАДРА !!!'}")

    # дропы: полный исходный список, добавляем только hh_id (для рендера)
    drops = [dict(dd, hh_id=hhs[dd['hh']]['id']) for dd in net['drops']]
    drops_in = [dd for dd in drops if dd['hh_id'] in hh_in_ids]
    couplers_in = [c for c in net['couplers'] if inr(c['x'], c['y'])]

    feeder_m = sum(clip_len_m(a, b, rect, mpp) for a, b in net['feeder_edges'])
    drop_m = sum(dd['length_m'] for dd in drops_in)
    stats = dict(
        households_in_crop=len(hhs_in),
        served=len(drops_in),
        unserved_no_road=len(hhs_in) - len(drops_in),
        couplers=len(couplers_in),
        feeder_km=round(feeder_m / 1000, 2),
        drop_km=round(drop_m / 1000, 2),
        avg_drop_m=round(drop_m / max(1, len(drops_in)), 1),
        max_drop_m=round(max((dd['length_m'] for dd in drops_in), default=0), 1),
        anchor_changed=False,
        anchor_in_frame=bool(a_in),
        transfer='unchanged',                 # пометка: перенос БЕЗ перестроения
        stats_full_network=net['stats'],      # исходная статистика для справки
    )
    net2 = dict(
        anchor=anchor, anchor_changed=False, root_node=net['root_node'],
        crop=dict(rect=[x0, y0, x1, y1], scale=t['scale']),
        couplers=net['couplers'],             # полный список — рисуется как есть
        feeder_edges=net['feeder_edges'],     # полный список — рисуется как есть
        drops=drops,                          # полный список — рисуется как есть
        stats=stats,
    )
    save_json(f'{vdir(KEY)}/network_v2.json', net2)
    print(f"ИТОГ в кадре: обслужено {stats['served']}/{stats['households_in_crop']} ДХ, "
          f"муфт {stats['couplers']}, магистраль {stats['feeder_km']} км, "
          f"дропы {stats['drop_km']} км, ср. дроп {stats['avg_drop_m']} м "
          f"(вся сеть: {net['stats']['served']} ДХ, {net['stats']['couplers']} муфт, "
          f"{net['stats']['feeder_km']} км, {net['stats']['drop_km']} км)")
    print(f'-> work/{KEY}/network_v2.json (топология не изменена)')


# -------------------------------------------------------------- PHASE: render
def phase_render():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'r10', os.path.join(os.path.dirname(__file__), '10_render_cropped.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.render_crop(KEY)


if __name__ == '__main__':
    phase = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if phase in ('match', 'all'):
        phase_match()
        gc.collect()
    if phase in ('build', 'all'):
        phase_build()
        gc.collect()
    if phase in ('render', 'all'):
        phase_render()
