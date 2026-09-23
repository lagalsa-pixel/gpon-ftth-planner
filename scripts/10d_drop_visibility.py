# -*- coding: utf-8 -*-
"""Проверка видимости каждого дропа ВДОЛЬ полилинии (между маркерами муфты и ДХ)."""
import json, math
import numpy as np
from PIL import Image

BASE = '/home/z/my-project'
Image.MAX_IMAGE_PIXELS = None

def check(key, num):
    t = json.load(open(f'{BASE}/work/{key}/crop_transform.json'))
    net = json.load(open(f'{BASE}/work/{key}/network_v2.json'))
    Mi = t['M_inv']
    k = 1.0 / t['scale']
    HH = int(round(150 * k))
    def T(p):
        return (Mi[0][0]*p[0] + Mi[0][1]*p[1] + Mi[0][2],
                Mi[1][0]*p[0] + Mi[1][1]*p[1] + Mi[1][2])
    img = np.asarray(Image.open(f'{BASE}/download/snp_vko/{num}_{key}_ftth_crop.png').convert('RGB'))
    R = img[:, :, 0].astype(np.int16); G = img[:, :, 1].astype(np.int16); B = img[:, :, 2].astype(np.int16)
    yellow = (R > 185) & (G > 165) & (B < 140)
    H, W = yellow.shape
    bad = []
    for d in net['drops']:
        pts = [T(p) for p in d['poly']]
        # суммарная длина и точки выборки каждые 6 px, отбрасывая 22 px у концов (маркеры)
        total = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1))
        if total < 60:      # короткий дроп: почти весь под маркерами — проверяем как есть
            skip = 10
        else:
            skip = 22
        samples = []
        acc = 0.0
        for i in range(len(pts)-1):
            seg = math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
            n = max(1, int(seg / 6))
            for j in range(n):
                f = (j + 0.5) / n
                d_cum = acc + seg * f
                if skip < d_cum < total - skip:
                    samples.append((pts[i][0] + (pts[i+1][0]-pts[i][0])*f,
                                    pts[i][1] + (pts[i+1][1]-pts[i][1])*f))
            acc += seg
        hits = 0
        for (x, y) in samples:
            xi, yi = int(x), int(y + HH)
            if 0 <= xi < W and 0 <= yi < H:
                zone = yellow[max(0, yi-6):yi+6, max(0, xi-6):xi+6]
                if zone.sum() > 0:
                    hits += 1
        if samples and hits / len(samples) < 0.5:
            bad.append((d['hh_id'], round(hits/max(1,len(samples)), 2), round(total)))
    print(f'{key}: дропов {len(net["drops"])}, плохо видимых (<50% сэмплов жёлтые): {len(bad)}')
    for b in bad[:12]:
        print('   !!', b)

check('solnechnoe', '02')
check('perevalnoe', '03')
check('prigorodnoe', '05')
check('altaiskiy', '06')
