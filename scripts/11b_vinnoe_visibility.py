# -*- coding: utf-8 -*-
"""Шаг 11b. Проверка видимости дропов Винного вдоль полилинии (адаптация 10d
под перенос без изменений: uint8 вместо int16 — экономия ОЗУ на карте 152 Мп;
пропуск дропов, целиком лежащих за рамкой кадра)."""
import json
import math
import numpy as np
from PIL import Image

BASE = '/home/z/my-project'
Image.MAX_IMAGE_PIXELS = None

KEY = 'vinnoe'
NUM = '04'

t = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
net = json.load(open(f'{BASE}/work/{KEY}/network_v2.json'))
Mi = t['M_inv']
k = 1.0 / t['scale']
HH = int(round(150 * k))


def T(p):
    return (Mi[0][0] * p[0] + Mi[0][1] * p[1] + Mi[0][2],
            Mi[1][0] * p[0] + Mi[1][1] * p[1] + Mi[1][2])


img = np.asarray(Image.open(f'{BASE}/download/snp_vko/{NUM}_{KEY}_ftth_crop.png').convert('RGB'))
R = img[:, :, 0]
G = img[:, :, 1]
B = img[:, :, 2]
yellow = (R > 185) & (G > 165) & (B < 140)
H, W = yellow.shape
print(f'карта {W}x{H}, шапка {HH} px; жёлтых px: {yellow.sum()}')

bad = []
n_in_frame = 0
for d in net['drops']:
    pts = [T(p) for p in d['poly']]
    if all(not (0 <= x < W and 0 <= y < H - HH) for x, y in pts):
        continue                      # дроп целиком за рамкой кадра — не проверяем
    n_in_frame += 1
    total = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                for i in range(len(pts) - 1))
    skip = 10 if total < 60 else 22   # отбрасываем зоны маркеров муфты/ДХ
    samples = []
    acc = 0.0
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        n = max(1, int(seg / 6))
        for j in range(n):
            f = (j + 0.5) / n
            d_cum = acc + seg * f
            if skip < d_cum < total - skip:
                samples.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
                                pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
        acc += seg
    hits = 0
    for (x, y) in samples:
        xi, yi = int(x), int(y + HH)
        if 0 <= xi < W and 0 <= yi < H:
            zone = yellow[max(0, yi - 6):yi + 6, max(0, xi - 6):xi + 6]
            if zone.sum() > 0:
                hits += 1
    if samples and hits / len(samples) < 0.5:
        bad.append((d['hh_id'], round(hits / max(1, len(samples)), 2), round(total)))

print(f'{KEY}: дропов в кадре {n_in_frame} (всего {len(net["drops"])}), '
      f'плохо видимых (<50% сэмплов жёлтые): {len(bad)}')
for b in bad[:15]:
    print('   !!', b)
