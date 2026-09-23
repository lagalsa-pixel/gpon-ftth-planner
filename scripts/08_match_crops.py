# -*- coding: utf-8 -*-
"""
Шаг 8. Сопоставление обрезанных пользователем снимков с исходными мозаиками Google z18.
SIFT + FLANN + RANSAC (частичная аффинная = поворот+масштаб+сдвиг).
Выход: work/<key>/crop_transform.json
  M_full: матрица 2x3, отображающая px нового снимка -> px исходной мозаики
  quad_old: 4 угла нового снимка в координатах мозаики
  scale, mpp_new, качество (inliers, NCC)
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json, save_json
import cv2
import numpy as np

TASKS = [
    ('perevalnoe',   'upload/03_Перевальное.jpg'),
    ('prigorodnoe',  'upload/05_Пригородное.jpg'),
    ('altaiskiy',    'upload/06_Алтайский_граница.jpg'),
]
BASE = '/home/z/my-project'
DS = 4  # даунскейл для сопоставления

def match_pair(key, new_path):
    old = cv2.imread(f'{BASE}/work/{key}/mosaic.jpg')
    new = cv2.imread(f'{BASE}/{new_path}')
    assert old is not None and new is not None, 'imread fail'
    Ho, Wo = old.shape[:2]; Hn, Wn = new.shape[:2]
    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    new_s = cv2.resize(new, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(old_s, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(new_s, cv2.COLOR_BGR2GRAY)
    # CLAHE для устойчивости к разной яркости
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1, g2 = clahe.apply(g1), clahe.apply(g2)

    sift = cv2.SIFT_create(nfeatures=60000, contrastThreshold=0.02)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    print(f'  features: mosaic {len(k1)}, crop {len(k2)}')

    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
    matches = flann.knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    print(f'  good matches: {len(good)}')
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000, confidence=0.999)
    assert M is not None, 'RANSAC fail'
    ninl = int(inl.sum())
    err = np.sqrt(((cv2.transform(src, M) - dst) ** 2).sum(axis=2)[inl.ravel() == 1]).mean()
    print(f'  inliers: {ninl} ({100*ninl/len(good):.1f}%), rms err {err:.2f} px (при DS={DS})')

    # полный масштаб: old_full = S @ M @ S^-1 @ new_full, S = diag(DS, DS, 1)
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    Si = np.diag([1.0 / DS, 1.0 / DS, 1.0])
    M_full = S @ M3 @ Si
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    rot = math.degrees(math.atan2(M_full[1, 0], M_full[0, 0]))

    # углы нового снимка в координатах мозаики (2x3 для cv2.transform!)
    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)

    # NCC-проверка: варпим мозаику в геометрию нового снимка (нужно old->new!)
    Minv = np.linalg.inv(M_full)
    warped = cv2.warpAffine(old, Minv[:2, :], (Wn, Hn), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
    gw, gn = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
    # сравнение по прореженной сетке
    step = 4
    a = gw[::step, ::step].astype(np.float32)
    b = gn[::step, ::step].astype(np.float32)
    a = a - a.mean(); b = b - b.mean()
    ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
    print(f'  scale {scale:.4f}, rot {rot:+.3f} deg, NCC {ncc:.3f}')
    print(f'  crop quad (old px): min {quad.min(axis=0).round(1)}, max {quad.max(axis=0).round(1)}')

    out = dict(
        new_image=new_path, new_W=Wn, new_H=Hn,
        mosaic_W=Wo, mosaic_H=Ho,
        M_full=[[float(c) for c in row] for row in M_full],      # new -> old
        M_inv=[[float(c) for c in row] for row in Minv[:2, :]],  # old -> new
        scale=float(scale), rot_deg=float(rot),
        quad_old=[[float(x), float(y)] for x, y in quad],
        inliers=ninl, rms_px=float(err * DS), ncc=ncc,
    )
    save_json(f'{vdir(key)}/crop_transform.json', out)
    # контрольная картинка: новое | варп мозаики (склейка в уменьшенном виде — экономия ОЗУ)
    q = 0.25
    new_q = cv2.resize(new, None, fx=q, fy=q, interpolation=cv2.INTER_AREA)
    warped_q = cv2.resize(warped, None, fx=q, fy=q, interpolation=cv2.INTER_AREA)
    cmp_img = np.hstack([new_q[:, :, ::-1], warped_q[:, :, ::-1]])
    del new_q, warped_q, warped
    cv2.imwrite(f'{BASE}/work/{key}/match_check.png', cmp_img)
    return out

if __name__ == '__main__':
    for key, path in TASKS:
        print(f'=== {key} : {path} ===')
        match_pair(key, path)
