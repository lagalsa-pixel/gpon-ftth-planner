# -*- coding: utf-8 -*-
"""Вырезка зон, которые VLM пометил как 'недоохват', для проверки на полном разрешении."""
import json
from PIL import Image

BASE = '/home/z/my-project'
Image.MAX_IMAGE_PIXELS = None

# --- Солнечное: зона муфт M24-M26 (центр-север) ---
net = json.load(open(f'{BASE}/work/solnechnoe/network_v2.json'))
t = json.load(open(f'{BASE}/work/solnechnoe/crop_transform.json'))
Mi = t['M_inv']
def T(p):
    return (Mi[0][0]*p[0] + Mi[0][1]*p[1] + Mi[0][2],
            Mi[1][0]*p[0] + Mi[1][1]*p[1] + Mi[1][2])

mz = [c for c in net['couplers'] if c['label'] in ('M24', 'M25', 'M26')]
img = Image.open(f'{BASE}/download/snp_vko/02_solnechnoe_ftth_crop.png')
if mz:
    cx = sum(T((c['x'], c['y']))[0] for c in mz) / len(mz)
    cy = sum(T((c['x'], c['y']))[1] for c in mz) / len(mz)
    box = (int(cx-900), 300+int(cy-900), int(cx+900), 300+int(cy+900))
    img.crop(box).save(f'{BASE}/work/solnechnoe/qa_zone_M24.png')
    print('solnechnoe M24-26 zone:', box)

# непокрытые ДХ Солнечного (контурные квадраты)
hhs = json.load(open(f'{BASE}/work/solnechnoe/households.json'))
served = {d['hh_id'] for d in net['drops']}
x0, y0, x1, y1 = net['crop']['rect']
uns = [h for h in hhs if x0 <= h['cx'] <= x1 and y0 <= h['cy'] <= y1 and h['id'] not in served]
print(f'solnechnoe: не обслужено {len(uns)} ДХ:')
for h in uns:
    px, py = T((h['cx'], h['cy']))
    print(f"  hh id={h['id']} @ crop px ({px:.0f},{py:.0f})")

# --- Перевальное: СЗ и ЮВ углы ---
img2 = Image.open(f'{BASE}/download/snp_vko/03_perevalnoe_ftth_crop.png')
W, H = img2.size
HH = 300
img2.crop((0, HH, 2800, HH+2800)).save(f'{BASE}/work/perevalnoe/qa_zone_NW.png')
img2.crop((W-2800, HH+H-2800, W, HH+H)).save(f'{BASE}/work/perevalnoe/qa_zone_SE.png')
print('perevalnoe NW/SE zones saved')

# количественная проверка: все ли ДХ в кадре Перевального имеют дроп
net2 = json.load(open(f'{BASE}/work/perevalnoe/network_v2.json'))
hhs2 = json.load(open(f'{BASE}/work/perevalnoe/households.json'))
served2 = {d['hh_id'] for d in net2['drops']}
x0, y0, x1, y1 = net2['crop']['rect']
in_crop = [h for h in hhs2 if x0 <= h['cx'] <= x1 and y0 <= h['cy'] <= y1]
uns2 = [h for h in in_crop if h['id'] not in served2]
print(f'perevalnoe: ДХ в кадре {len(in_crop)}, без дропа {len(uns2)}')
