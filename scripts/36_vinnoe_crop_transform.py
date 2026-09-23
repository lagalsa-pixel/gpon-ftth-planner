# -*- coding: utf-8 -*-
"""
Шаг 36. Восстановление crop_transform.json для Винного.

После сброса среды утеряны mosaic.jpg и crop_transform.json Винного. База
base_restitch.png (шаг 32b) перешита в координатном пространстве СТАРОЙ мозаики
со смещением (offx, offy): px_mosaic = px_restitch - (offx, offy).

Здесь: SIFT+FLANN+RANSAC (DS=4, CLAHE — параметры шага 08) кадр пользователя
upload/04_Винное.jpg -> base_restitch.png, затем компоновка сдвига в пространство
мозаики. NCC-контроль на уменьшенных копиях (полный варп 148 Мп не влезает в ОЗУ).
Кросс-проверка quad_old с crop.rect из network_v2.json (результат матча прежней
сессии: [554..6829] x [1671..7582]).

Выход: work/vinnoe/crop_transform.json (формат шага 08) + work/vinnoe/match_check.png
"""
import json, math, os, sys

import cv2
import numpy as np

BASE = '/home/z/my-project'
KEY = 'vinnoe'
DS = 4          # даунскейл для сопоставления
Q = 0.25        # масштаб NCC-проверки


def main():
    rs = json.load(open(f'{BASE}/work/{KEY}/restitch.json'))
    offx, offy = rs['offx'], rs['offy']
    old = cv2.imread(rs['img'])                     # base_restitch (restitch px)
    new = cv2.imread(f'{BASE}/upload/04_Винное.jpg')
    assert old is not None and new is not None, 'imread fail'
    Ho, Wo = old.shape[:2]
    Hn, Wn = new.shape[:2]
    print(f'restitch {Wo}x{Ho}, кадр {Wn}x{Hn}, off=({offx:.2f},{offy:.2f})', flush=True)

    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    new_s = cv2.resize(new, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(old_s, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(new_s, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1, g2 = clahe.apply(g1), clahe.apply(g2)

    sift = cv2.SIFT_create(nfeatures=60000, contrastThreshold=0.02)
    k1, d1 = sift.detectAndCompute(g1, None)       # restitch (train)
    k2, d2 = sift.detectAndCompute(g2, None)       # кадр (query)
    print(f'features: restitch {len(k1)}, кадр {len(k2)}', flush=True)

    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
    matches = flann.knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    print(f'good matches: {len(good)}', flush=True)
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000,
                                         confidence=0.999)
    assert M is not None, 'RANSAC fail'
    ninl = int(inl.sum())
    err = np.sqrt(((cv2.transform(src, M) - dst) ** 2).sum(axis=2)[inl.ravel() == 1]).mean()
    print(f'inliers: {ninl} ({100 * ninl / len(good):.1f}%), rms {err:.2f} px @DS={DS}', flush=True)

    # полный масштаб: restitch_full = S @ M @ S^-1 @ new_full
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    Si = np.diag([1.0 / DS, 1.0 / DS, 1.0])
    M_rs = S @ M3 @ Si                                # new -> restitch (3x3)

    # компоновка в пространство мозаики: mosaic = restitch - (offx, offy)
    Tm = np.array([[1, 0, -offx], [0, 1, -offy], [0, 0, 1]], dtype=np.float64)
    M_full = Tm @ M_rs                                 # new -> old-mosaic (3x3)
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    rot = math.degrees(math.atan2(M_full[1, 0], M_full[0, 0]))
    Minv = np.linalg.inv(M_full)                       # old-mosaic -> new

    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)

    # --- NCC на уменьшенных копиях: варп restitch_q -> геометрия кадра_q ---
    old_q = cv2.resize(old, None, fx=Q, fy=Q, interpolation=cv2.INTER_AREA)
    new_q = cv2.resize(new, None, fx=Q, fy=Q, interpolation=cv2.INTER_AREA)
    # M_q: new_q -> old_q  =  (1/Q) @ M_rs @ Q
    Mq = np.diag([Q, Q, 1.0]) @ M_rs @ np.diag([1.0 / Q, 1.0 / Q, 1.0])
    warped = cv2.warpAffine(old_q, np.linalg.inv(Mq)[:2, :],
                            (new_q.shape[1], new_q.shape[0]),
                            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gw = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gn = cv2.cvtColor(new_q, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gw -= gw.mean(); gn -= gn.mean()
    ncc = float((gw * gn).sum() / (np.sqrt((gw * gw).sum() * (gn * gn).sum()) + 1e-9))
    print(f'scale {scale:.4f}, rot {rot:+.3f} deg, NCC(q={Q}) {ncc:.3f}', flush=True)

    # --- кросс-проверка с crop.rect прежней сессии ---
    net = json.load(open(f'{BASE}/work/{KEY}/network_v2.json'))
    r = net['crop']['rect']
    dx = max(abs(quad[0][0] - r[0]), abs(quad[2][0] - r[2]))
    dy = max(abs(quad[0][1] - r[1]), abs(quad[2][1] - r[3]))
    print(f'quad_old TL=({quad[0][0]:.1f},{quad[0][1]:.1f}) BR=({quad[2][0]:.1f},{quad[2][1]:.1f})')
    print(f'crop.rect прежней сессии TL=({r[0]:.1f},{r[1]:.1f}) BR=({r[2]:.1f},{r[3]:.1f})')
    print(f'расхождение углов: dx={dx:.2f} px, dy={dy:.2f} px (допуск 3 px)')
    assert dx < 3.0 and dy < 3.0, 'кросс-проверка провалена'
    assert 0.495 < scale < 0.505 and abs(rot) < 0.05, 'scale/rot вне допуска'

    out = dict(
        new_image='upload/04_Винное.jpg', new_W=Wn, new_H=Hn,
        mosaic_W=7390, mosaic_H=8277,                # габариты старой мозаики (mosaic_geo)
        M_full=[[float(c) for c in row] for row in M_full],      # new -> old mosaic
        M_inv=[[float(c) for c in row] for row in Minv[:2, :]],  # old mosaic -> new
        scale=float(scale), rot_deg=float(rot),
        quad_old=[[float(x), float(y)] for x, y in quad],
        inliers=ninl, rms_px=float(err * DS), ncc=ncc,
        note='восстановлено шагом 36: SIFT против base_restitch.png + сдвиг (offx,offy)',
    )
    with open(f'{BASE}/work/{KEY}/crop_transform.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('-> work/vinnoe/crop_transform.json')

    # контрольная картинка: кадр | варп базы (в уменьшенном виде)
    cmp_img = np.hstack([new_q, warped])
    cv2.imwrite(f'{BASE}/work/{KEY}/match_check.png', cmp_img)
    print('-> work/vinnoe/match_check.png')


if __name__ == '__main__':
    main()
