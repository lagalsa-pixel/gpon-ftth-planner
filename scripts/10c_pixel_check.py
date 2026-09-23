# -*- coding: utf-8 -*-
"""Пиксельная проверка: у каждого обслуженного ДХ на карте есть жёлтый дроп возле маркера."""
import json
import numpy as np
from PIL import Image

BASE = '/home/z/my-project'
Image.MAX_IMAGE_PIXELS = None

def check(key, num):
    t = json.load(open(f'{BASE}/work/{key}/crop_transform.json'))
    net = json.load(open(f'{BASE}/work/{key}/network_v2.json'))
    hhs = json.load(open(f'{BASE}/work/{key}/households.json'))
    Mi = t['M_inv']
    HH = 600  # высота шапки в px кадра (S(150), k=2 -> 300... берём 300)
    HH = 300
    def T(p):
        return (Mi[0][0]*p[0] + Mi[0][1]*p[1] + Mi[0][2],
                Mi[1][0]*p[0] + Mi[1][1]*p[1] + Mi[1][2])
    img = np.asarray(Image.open(f'{BASE}/download/snp_vko/{num}_{key}_ftth_crop.png').convert('RGB'))
    R = img[:, :, 0].astype(np.int16); G = img[:, :, 1].astype(np.int16); B = img[:, :, 2].astype(np.int16)
    yellow = (R > 190) & (G > 170) & (B < 130)
    x0, y0, x1, y1 = net['crop']['rect']
    in_crop = [h for h in hhs if x0 - 2 <= h['cx'] <= x1 + 2 and y0 - 2 <= h['cy'] <= y1 + 2]
    served = {d['hh_id'] for d in net['drops']}
    miss = []
    rad = 36
    for h in in_crop:
        if h['id'] not in served:
            continue
        px, py = T((h['cx'], h['cy']))
        xi, yi = int(px), int(py + HH)
        if yi < 0 or xi < 0 or yi >= img.shape[0] or xi >= img.shape[1]:
            continue
        zone = yellow[max(0, yi-rad):yi+rad, max(0, xi-rad):xi+rad]
        if zone.sum() < 4:
            miss.append((h['id'], xi, yi, int(zone.sum())))
    print(f'{key}: обслужено {len([h for h in in_crop if h["id"] in served])}, '
          f'без жёлтых пикселей возле маркера: {len(miss)}')
    for m in miss[:10]:
        print('   !!', m)

check('solnechnoe', '02')
check('perevalnoe', '03')
check('prigorodnoe', '05')
check('altaiskiy', '06')
