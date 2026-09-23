#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50d: кропы новой символики с итоговой карты ВБ (ЦУ, ОРШ, легенда)."""
import json, os
from PIL import Image

BASE = '/home/z/my-project'
KEY = 'verhneberezovka'
MAP = f'{BASE}/download/snp_vko/01_Верхнеберезовка_зоны_ОРШ_схема_D.jpg'
OUT = f'{BASE}/work/qa/symbology_t50'
os.makedirs(OUT, exist_ok=True)

db = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
v = next(x for x in db['villages'] if x['key'] == KEY)
net = json.load(open(f'{BASE}/work/{KEY}/network_hh2.json', encoding='utf-8'))
HH = 150 * (v.get('scale_k', 1) if 'scale_k' in v else 1)   # шапка: S(150), S~1 для ВБ?

im = Image.open(MAP)
print('карта:', im.size)
# заголовочная полоса HH: из 48b — canvas H+HH, HH=S(150); S() для ВБ = 1? Проверим фактически:
# карта 7312x7892, мозаика 7312x7742 → HH=150 → S=1 ✓
HH = im.height - 7742
print('HH =', HH)

anchor = net['anchor']
ax, ay = anchor['x'], anchor['y'] + HH

def crop(cx, cy, r, name):
    box = (max(0, cx - r), max(0, cy - r), min(im.width, cx + r), min(im.height, cy + r))
    im.crop(box).save(f'{OUT}/{name}.jpg', quality=92)
    print(f'{name}: центр ({cx},{cy}) -> {box}')

# ЦУ (якорь)
crop(int(ax), int(ay), 260, '01_cu_olt')
# ОРШ: первые 3 зоны из книги (px = медиана зоны)
zones = [z for z in v.get('zones', []) if not z.get('zone', '').startswith('ЦУ')]
print('зон в книге:', len(zones))
for i, z in enumerate(zones[:3]):
    ox, oy = z['px']
    crop(int(ox), int(oy + HH), 220, f'0{i+2}_orsh_{i+1}')
# легенда: из qa json позиции
lg = json.load(open(f'{BASE}/work/qa/zone_maps_v4/01_legend.json', encoding='utf-8'))
lx, ly, lw, lh = lg['x'], lg['y'], lg['W'], lg['H']
crop(lx + lw // 2, ly + lh // 2, max(lw, lh), '05_legend')
print('готово ->', OUT)
