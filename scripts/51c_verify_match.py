# -*- coding: utf-8 -*-
"""
Шаг 51c. Верификация привязки image.png к кадру 05_Пригородное.jpg (22 inliers):
NCC-корреляция варпа + пересчёт quad в координаты мозаики через crop_transform.
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
import cv2
import numpy as np

BASE = '/home/z/my-project'
key = 'prigorodnoe'

# quad в координатах КАДРА (из 51b): image -> frame, scale 0.8798
# повторим оценку аффинной тут же, надёжнее хранить матрицу
import importlib.util
spec = importlib.util.spec_from_file_location('m51b', f'{BASE}/scripts/51b_match_frames.py')
# не исполняем main, а повторим код:

def estimate():
    old = cv2.imread(f'{BASE}/upload/05_Пригородное.jpg')
    new = cv2.imread(f'{BASE}/upload/image.png')
    Hn, Wn = new.shape[:2]
    DS = 4
    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
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
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000, confidence=0.999)
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    M_full = S @ M3  # image px -> frame px (full)
    return old, new, M_full, int(inl.sum()), Wn, Hn

old, new, M_full, ninl, Wn, Hn = estimate()
print(f'inliers {ninl}, M_full scale {math.hypot(*M_full[0,:2]):.4f}')

# NCC: варп кадра в геометрию изображения
warped = cv2.warpAffine(old, np.linalg.inv(M_full)[:2, :], (Wn, Hn),
                        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
gw, gn = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
a = gw.astype(np.float32) - gw.mean(); b = gn.astype(np.float32) - gn.mean()
ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
print(f'NCC full-image: {ncc:.4f}')

# сайд-бай-сайд для VLM-сверки
side = np.hstack([new, warped])
cv2.imwrite(f'{BASE}/work/user_img_vs_frame.png', side)
print('side-by-side: work/user_img_vs_frame.png')

# quad изображения в координатах кадра
corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
quad_frame = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)
print('quad (frame px):', quad_frame.round(1).tolist())

# пересчёт в координаты мозаики через crop_transform (frame -> mosaic)
ct = json.load(open(f'{BASE}/work/{key}/crop_transform.json'))
Mfm = np.array(ct['M_full'], dtype=np.float64)  # frame px -> mosaic px (проверим направление)
# в 08_match_crops: M_full отображает px НОВОГО снимка -> px исходной мозаики.
# «новый снимок» = кадр пользователя => Mfm: frame -> mosaic. Верно.
quad_mos = cv2.transform(quad_frame.reshape(-1, 1, 2), Mfm[:2, :]).reshape(-1, 2)
print('quad (mosaic px):', quad_mos.round(1).tolist())
qm = quad_mos
print(f'центр (mosaic px): ({qm[:,0].mean():.1f}, {qm[:,1].mean():.1f}), размер {qm[:,0].max()-qm[:,0].min():.0f}x{qm[:,1].max()-qm[:,1].min():.0f} px')

# кроп мозаики с запасом
geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
mpp = geo['mpp']
mos = cv2.imread(f'{BASE}/work/{key}/mosaic.jpg')
pad = 60
x0 = int(max(0, qm[:,0].min()-pad)); y0 = int(max(0, qm[:,1].min()-pad))
x1 = int(min(mos.shape[1], qm[:,0].max()+pad)); y1 = int(min(mos.shape[0], qm[:,1].max()+pad))
crop = mos[y0:y1, x0:x1]
cv2.imwrite(f'{BASE}/work/user_img_mosaic_crop.png', crop)
print(f'кроп мозаики: work/user_img_mosaic_crop.png {crop.shape[1]}x{crop.shape[0]} px = {crop.shape[1]*mpp:.0f}x{crop.shape[0]*mpp:.0f} м')

# какие ДХ попадают в область
hh = json.load(open(f'{BASE}/work/{key}/households.json'))
qm_ = quad_mos
inside = [h for h in hh if qm_[:,0].min()-40 <= h['cx'] <= qm_[:,0].max()+40 and qm_[:,1].min()-40 <= h['cy'] <= qm_[:,1].max()+40]
print(f'ДХ в области снимка: {len(inside)}')
for h in inside:
    print(f"  hh id={h['id']} ({h['cx']:.0f},{h['cy']:.0f}) n_bld={h['n_bld']} main={h['main_w']*mpp:.0f}x{h['main_h']*mpp:.0f}м src={h['main_src']}")

json.dump(dict(ncc=ncc, inliers=ninl,
               quad_frame=quad_frame.round(1).tolist(),
               quad_mosaic=quad_mos.round(1).tolist()),
          open(f'{BASE}/work/user_img_match_verified.json', 'w'), ensure_ascii=False, indent=1)
