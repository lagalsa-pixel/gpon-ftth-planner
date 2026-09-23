# -*- coding: utf-8 -*-
"""
Шаг 51. Привязка изображения пользователя (upload/image.png, кейс сблокированного дома)
к мозаикам 6 сёл. SIFT + FLANN + RANSAC (частичная аффинная).
Мозаика даунскейлится (DS), изображение пользователя — в полном размере (оно маленькое).
Выход: work/user_img_match.json — лучшее село + матрица + quad + кропы для проверки.
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, save_json
import cv2
import numpy as np

BASE = '/home/z/my-project'
IMG = f'{BASE}/upload/image.png'
DS = 4  # даунскейл мозаики (экономия ОЗУ)
import gc

def match_village(key):
    old = cv2.imread(f'{BASE}/work/{key}/mosaic.jpg')
    new = cv2.imread(IMG)
    assert old is not None and new is not None, 'imread fail'
    Hn, Wn = new.shape[:2]
    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    del old
    gc.collect()
    g1 = cv2.cvtColor(old_s, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1, g2 = clahe.apply(g1), clahe.apply(g2)

    sift = cv2.SIFT_create(nfeatures=40000, contrastThreshold=0.02)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)

    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
    matches = flann.knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000, confidence=0.999)
    if M is None:
        return None
    ninl = int(inl.sum())
    err = np.sqrt(((cv2.transform(src, M) - dst) ** 2).sum(axis=2)[inl.ravel() == 1]).mean()

    # полный масштаб мозаики: old_full_px = S @ M @ S^-1 @ img_px  (S = diag(DS,DS,1) на старой стороне)
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    M_full = S @ M3  # img -> old_full (img не масштабировалась)
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    rot = math.degrees(math.atan2(M_full[1, 0], M_full[0, 0]))

    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)

    # NCC: заново читаем только нужную область мозаики (экономия ОЗУ)
    x0, y0 = int(quad[:, 0].min()), int(quad[:, 1].min())
    x1, y1 = int(quad[:, 0].max()), int(quad[:, 1].max())
    del old_s, g1, d1, k1, d2, k2, matches, good
    gc.collect()
    oldr = cv2.imread(f'{BASE}/work/{key}/mosaic.jpg')
    pad = 10
    sub = oldr[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    del oldr
    gc.collect()
    if sub.size == 0:
        return None
    # подвинуть M_full в координаты среза
    off = np.array([[1, 0, -max(0, x0 - pad)], [0, 1, -max(0, y0 - pad)], [0, 0, 1]], dtype=np.float64)
    Msub = off @ M_full
    warped = cv2.warpAffine(sub, np.linalg.inv(Msub)[:2, :], (Wn, Hn), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
    gw, gn = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
    step = 2
    a = gw[::step, ::step].astype(np.float32); b = gn[::step, ::step].astype(np.float32)
    a = a - a.mean(); b = b - b.mean()
    ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
    return dict(inliers=ninl, rms=round(float(err), 2), scale=round(scale, 4), rot=round(rot, 3),
                ncc=round(ncc, 4), quad=[[round(float(x), 1), round(float(y), 1)] for x, y in quad],
                M_full=[[round(float(c), 4) for c in row] for row in M_full[:2]])

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = {}
    try:
        prev = json.load(open(f'{BASE}/work/user_img_match.json'))
        results = prev.get('results', {})
    except Exception:
        pass
    for v in VILLAGES:
        key = v['key']
        if only and key != only:
            continue
        if not only and key in results and 'error' not in results[key]:
            continue  # уже посчитано в прошлых запусках
        try:
            r = match_village(key)
        except Exception as e:
            r = dict(error=str(e))
        results[key] = r
        gc.collect()
        if r and 'error' not in r:
            print(f"{v['name']:20s} inliers={r['inliers']:5d} rms={r['rms']:5.2f} scale={r['scale']:.4f} "
                  f"rot={r['rot']:+6.2f} NCC={r['ncc']:.4f} quad_min=({r['quad'][0][0]:.0f},{r['quad'][0][1]:.0f}) "
                  f"size={(r['quad'][2][0]-r['quad'][0][0]):.0f}x{(r['quad'][2][1]-r['quad'][0][1]):.0f}px", flush=True)
        else:
            print(f"{v['name']:20s} FAIL {r}", flush=True)
        save_json(f'{BASE}/work/user_img_match.json', dict(best=None, results=results))
    ok = {k: r for k, r in results.items() if r and 'error' not in r and r['inliers'] >= 8}
    if ok:
        best = max(ok, key=lambda k: ok[k]['ncc'])
        print(f"\nЛУЧШЕЕ СООТВЕТСТВИЕ: {best} (NCC {ok[best]['ncc']:.4f})")
        save_json(f'{BASE}/work/user_img_match.json', dict(best=best, results=results))
        # кроп мозаики в области снимка для визуальной сверки
        r = ok[best]
        q = np.array(r['quad'])
        x0, y0 = int(q[:, 0].min()), int(q[:, 1].min())
        x1, y1 = int(q[:, 0].max()), int(q[:, 1].max())
        old = cv2.imread(f'{BASE}/work/{best}/mosaic.jpg')
        crop = old[max(0, y0):y1, max(0, x0):x1]
        cv2.imwrite(f'{BASE}/work/user_img_mosaic_crop.png', crop)
        print(f"кроп мозаики: work/user_img_mosaic_crop.png {crop.shape[1]}x{crop.shape[0]}")
    else:
        print('\nСопоставление не найдено')
        save_json(f'{BASE}/work/user_img_match.json', dict(best=None, results=results))

if __name__ == '__main__':
    main()
