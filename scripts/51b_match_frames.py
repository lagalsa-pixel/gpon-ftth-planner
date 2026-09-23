# -*- coding: utf-8 -*-
"""
Шаг 51b. Привязка upload/image.png к КАДРАМ пользователя (upload/0*.jpg) —
Google Earth Pro экспорты, использованные в Task 4/5.
"""
import sys, os, json, math, gc
sys.path.insert(0, os.path.dirname(__file__))
import cv2
import numpy as np

BASE = '/home/z/my-project'
IMG = f'{BASE}/upload/image.png'
FRAMES = [
    ('solnechnoe',   f'{BASE}/upload/02_Солнечное.jpg'),
    ('perevalnoe',   f'{BASE}/upload/03_Перевальное.jpg'),
    ('vinnoe',       f'{BASE}/upload/04_Винное.jpg'),
    ('prigorodnoe',  f'{BASE}/upload/05_Пригородное.jpg'),
    ('altaiskiy',    f'{BASE}/upload/06_Алтайский_граница.jpg'),
]
DS = 4  # даунскейл кадра (экономия ОЗУ)

def match_frame(key, path):
    old = cv2.imread(path)
    new = cv2.imread(IMG)
    assert old is not None and new is not None, 'imread fail'
    Hn, Wn = new.shape[:2]
    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    del old; gc.collect()
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
    # полный масштаб кадра
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    M_full = S @ M3
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)
    return dict(inliers=ninl, scale=round(scale, 4),
                quad=[[round(float(x), 1), round(float(y), 1)] for x, y in quad])

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for key, path in FRAMES:
        if only and key != only:
            continue
        try:
            r = match_frame(key, path)
        except Exception as e:
            r = dict(error=str(e))
        gc.collect()
        if r and 'error' not in r and r is not None:
            q = r['quad']
            print(f"{key:14s} inliers={r['inliers']:5d} scale={r['scale']:.4f} "
                  f"quad=({q[0][0]:.0f},{q[0][1]:.0f})..({q[2][0]:.0f},{q[2][1]:.0f})", flush=True)
        else:
            print(f"{key:14s} FAIL {r}", flush=True)

if __name__ == '__main__':
    main()
