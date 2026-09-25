#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 58e: кропы для контроля значков МЖД (до/после) на карте Алтайского."""
import json
from PIL import Image

BASE = '/home/z/my-project'
key = 'altaiskiy'
tr = json.load(open(f'{BASE}/work/{key}/crop_transform.json'))
Mi = tr['M_inv']

def T(p):
    x, y = p
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2])

# здания для контроля: 272 (n=32), 295 (n=8, заказчик), 283 (n=4, барак),
# 480 (n=24), 289 (n=8, барак R3), юг (4 дома кармана — дропы должны остаться)
grp = json.load(open(f'{BASE}/work/{key}/mzd_groups.json'))
APT = {g['bid']: g for g in grp if g['kind'] == 'apartment'}

crops = []
for bid in (637127272, 637127295, 637127283, 496463480, 637127289):
    g = APT[bid]
    cx, cy = T((g['cx'], g['cy']))
    crops.append((f'mzd_{bid}_n{g["n"]}', cx, cy))
# южный карман: дома hh 710-713 (дропы должны остаться!)
net = json.load(open(f'{BASE}/work/{key}/network_hh3.json'))
sp = [d for d in net['drops'] if d['hh_id'] in (710, 711, 712, 713)]
if sp:
    cx = sum(T(d['poly'][-1])[0] for d in sp) / len(sp)
    cy = sum(T(d['poly'][-1])[1] for d in sp) / len(sp)
    crops.append(('south_pocket_drops', cx, cy))

HH = 300  # шапка карты
for name, cx, cy in crops:
    R = 520
    for tag, path in (('after', f'{BASE}/download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg'),
                      ('before', f'{BASE}/work/qa/task58_before/06_Алтайский_зоны_ОРШ_схема_D.jpg')):
        im = Image.open(path)
        box = (int(cx - R), int(cy - R + HH), int(cx + R), int(cy + R + HH))
        box = (max(0, box[0]), max(0, box[1]), min(im.width, box[2]), min(im.height, box[3]))
        c = im.crop(box)
        c.save(f'{BASE}/work/qa/task58_before/crop_{name}_{tag}.jpg', quality=88)
        print(name, tag, c.size)
print('done')
