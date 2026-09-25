#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 55u: верификация правок Task 55 (как 54r для Task 54).
1) 283: 4 дропа у контура, без муфт внутри, длины sane
2) cv-дуплекс img_12: 2 дропа у здания
3) контрольный кроп карты v5 с обоими зданиями для VLM/заказчика."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
DIR = BASE / 'work/altay2'

tr = json.load(open(BASE / f'work/{KEY}/crop_transform.json'))
M_inv = tr['M_inv']
geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


def mos_to_map(x, y):
    fx = M_inv[0][0] * x + M_inv[0][1] * y + M_inv[0][2]
    fy = M_inv[1][0] * x + M_inv[1][1] * y + M_inv[1][2]
    return fx, fy + 300


osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {}
for b in osm['buildings']:
    pts = [g2p(la, lo) for la, lo in b['poly']]
    BLD[b['id']] = dict(pts=pts, poly=Polygon(pts),
                        cx=sum(p[0] for p in pts) / len(pts),
                        cy=sum(p[1] for p in pts) / len(pts))

net = json.load(open(BASE / f'work/{KEY}/network_hh3.json'))
drops = net['drops']
couplers = net['couplers']
print(f'network_hh3: дропов {len(drops)}, муфт {len(couplers)}')

# --- 283 ---
b = BLD[637127283]
d283 = [d for d in drops if b['poly'].distance(Point(d['poly'][-1])) <= 14.0]
print(f'\n637127283 (9.3x28.9): дропов {len(d283)} (ожидается 4)')
for d in sorted(d283, key=lambda x: x['hh_id']):
    p = d['poly'][-1]
    dist = b['poly'].distance(Point(p))
    print(f'   hh_id={d["hh_id"]} coupler={d.get("coupler")} '
          f'len={d.get("length_m", 0):.1f} м, до контура {dist * mpp:.1f} м')
c_in = [c for c in couplers if b['poly'].contains(Point(c['x'], c['y']))]
print(f'   муфт внутри контура: {len(c_in)} (ожидается 0)')

# --- cv-дуплекс (img_12) ---
CX, CY = 3746.5, 7826.0
d12 = [d for d in drops
       if math.hypot(d['poly'][-1][0] - CX, d['poly'][-1][1] - CY) < 45]
print(f'\ncv-дуплекс img_12 (у {CX},{CY}): дропов {len(d12)} (ожидается 2)')
for d in sorted(d12, key=lambda x: x['hh_id']):
    p = d['poly'][-1]
    print(f'   hh_id={d["hh_id"]} coupler={d.get("coupler")} '
          f'len={d.get("length_m", 0):.1f} м, конец=({p[0]:.1f},{p[1]:.1f})')

# --- контрольный кроп карты v5 ---
mapv5 = Image.open(
    BASE / 'download/snp_vko/06_Алтайский_зоны_ОРШ_схема_D.jpg').convert('RGB')
# 283: map (1918,6688); дуплекс: map (2400,6776) — оба в один кроп?
# 283 x=1918, дуплекс x=2400: расстояние 500 px — сделаем ДВА кропа
FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
for tag, (mx, my), pad in [('283', (1918, 6688), 220),
                           ('duplex', (2400, 6776), 220)]:
    x0, y0 = int(mx - pad), int(my - pad)
    x1, y1 = int(mx + pad), int(my + pad)
    crop = mapv5.crop((x0, y0, x1, y1))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    dr = ImageDraw.Draw(crop)
    dr.text((16, 12), tag, font=FONT, fill=(255, 255, 0),
            stroke_width=3, stroke_fill=(0, 0, 0))
    out = DIR / f'verify_map_{tag}.jpg'
    crop.save(out, quality=93)
    print(f'\nкроп: {out.name} {crop.size}')
print('\nВЕРИФИКАЦИОННЫЕ КРОПЫ ГОТОВЫ')
