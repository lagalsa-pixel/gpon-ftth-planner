#!/usr/bin/env python3
import cv2
import json
import numpy as np

BASE = '/home/z/my-project'
img = cv2.imread(f'{BASE}/work/altay3/map05_v8.jpg')
tr = json.load(open(f'{BASE}/work/prigorodnoe/crop_transform.json'))
Mi = tr['M_inv']
net = json.load(open(f'{BASE}/work/prigorodnoe/network_hh2.json'))
tiles = []
for d in net['drops'][:4]:
    ex, ey = d['poly'][-1]
    mx = Mi[0][0] * ex + Mi[0][1] * ey + Mi[0][2]
    my = Mi[1][0] * ex + Mi[1][1] * ey + Mi[1][2]
    for nm, (px, py) in [('T', (mx, my)), ('raw/2', (ex * 0.5, ey * 0.5))]:
        px, py = int(px), int(py)
        if 40 <= px < img.shape[1] - 40 and 40 <= py < img.shape[0] - 40:
            tiles.append((f"hh{d['hh_id']} {nm}",
                          img[py - 40:py + 40, px - 40:px + 40].copy()))
print('tiles:', [(t[0], t[1].shape) for t in tiles])
if tiles:
    fixed = [cv2.resize(t[1], (80, 80)) for t in tiles]
    rows = []
    for i in range(0, len(fixed), 4):
        row = np.hstack([cv2.copyMakeBorder(t, 2, 2, 2, 2,
                                            cv2.BORDER_CONSTANT,
                                            value=(255, 255, 255))
                         for t in fixed[i:i + 4]])
        rows.append(row)
    cv2.imwrite(f'{BASE}/work/altay3/debug_transform.png',
                np.vstack(rows))
    print('saved debug_transform.png')
