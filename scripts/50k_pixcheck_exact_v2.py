#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50k (v2): точный контроль иконок карты Топольного.

Позиции иконок воспроизводятся ТОЧНО как в render_village_map:
Tree + partition_greedy -> cuts (узлы вреза = позиции ОРШ), anchor из сети.
Проверка структуры: ЦУ (красная рамка/корпус/табличка OLT/белое здание),
ОРШ (цвет зоны/белая цифра/цоколь).
"""
import json, sys, os
import numpy as np
from PIL import Image

FP = '/home/z/my-project/download/ftth_pipeline'
sys.path.insert(0, FP)
import ftth_pipeline as fp

ctx = fp.Ctx(os.path.join(FP, 'config_topolnoe.json'), only='topolnoe')
v = ctx.villages[0]
key = v['key']
vd = ctx.vdir(key)
db = fp.load_json(os.path.join(vd, 'boq.json'))
geo = fp.geo_for(key, ctx)
mpp = geo['mpp']
netp = os.path.join(vd, db['net'])
osm_p = os.path.join(vd, 'osm.json')
road = fp.build_road_graph(fp.load_json(osm_p), geo, mpp, ctx.P) if os.path.exists(osm_p) else None
t = fp.Tree(key, netp, mpp, ctx.P, road=road)
cuts, _ = t.partition_greedy(ctx.P('s_min_km'))
print('cuts:', [list(map(round, map(float, c))) if isinstance(c, (list, tuple)) else c for c in cuts])

net = fp.load_json(netp)
ct = fp.load_json(os.path.join(vd, 'crop_transform.json'))
Minv, scale = ct['M_inv'], ct['scale']
k = 1.0 / scale
HH = fp.fto.HH_HDR if hasattr(fp, 'fto') else 150

MAP = '/home/z/my-project/work/topolnoe_test/download/07_Топольное_зоны_ОРШ.jpg'
im = Image.open(MAP).convert('RGB')
W, H = im.size
a = np.asarray(im).astype(int)

def T(p):
    x, y = p
    return (Minv[0][0]*x + Minv[0][1]*y + Minv[0][2],
            Minv[1][0]*x + Minv[1][1]*y + Minv[1][2])

def px(x, y):
    xx, yy = int(round(x)), int(round(y))
    return a[yy, xx] if 0 <= yy < H and 0 <= xx < W else None

ok = True
def chk(cond, msg):
    global ok
    print(('OK  ' if cond else 'FAIL ') + msg)
    ok = ok and cond

def near(c, target, tol):
    return c is not None and all(abs(int(x)-y) <= tol for x, y in zip(c, target))

# ---------- ЦУ ----------
ax, ay = T((net['anchor']['x'], net['anchor']['y']))
R = 30 * k
cx, cy = int(round(ax)), int(round(ay + HH))
print(f"ЦУ @({cx},{cy}), R={R:.1f}")
chk(any(near(px(cx, cy - yy), (224, 49, 49), 60) for yy in range(int(1.05*R), int(1.45*R))), "рамка сверху (скан)")
chk(any(near(px(cx - xx, cy), (224, 49, 49), 60) for xx in range(int(0.9*R), int(1.3*R))), "рамка сбоку (скан)")
chk(any(near(px(cx, cy + yy), (16, 24, 40), 55) for yy in range(0, int(0.6*R))), f"тёмный корпус (скан)")
row_w = [px(x, cy - int(0.25*R)) for x in range(cx - int(0.55*R), cx + int(0.55*R))]
chk(any(near(c, (255, 255, 255), 35) for c in row_w), "белые элементы (мачта/крыша)")
row_p = [px(x, cy + int(0.7*R)) for x in range(cx - int(0.75*R), cx + int(0.75*R))]
chk(any(near(c, (224, 49, 49), 60) for c in row_p), "табличка OLT красная")

# ---------- ОРШ: позиции = узлы вреза (как в рендере) ----------
PAL = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181)]
# порядок как в рендере: по числу ДХ зоны (убывание)
from collections import defaultdict
zone_dh = defaultdict(int)
for node, dh in t.homes.items():
    zone_dh[node if node in set(cuts) else None] += 0  # placeholder — порядок ниже
order = sorted(cuts, key=lambda c: -zone_dh.get(c, 0))
# боевой порядок: воспроизведём как в рендере (zone_dh по zr)
zr = {t.root: t.root}
cutset = set(cuts)
for u in t.bfs:
    if u == t.root:
        continue
    zr[u] = u if u in cutset else zr[t.parent[u]]
zd = defaultdict(int)
for node, dh in t.homes.items():
    zd[zr[node]] += dh
order = sorted(cuts, key=lambda c: -zd[c])

for zi, c in enumerate(order):
    zx, zy = T(c)
    Rz = 16 * k
    cx, cy = int(round(zx)), int(round(zy + HH))
    col = PAL[zi % len(PAL)]
    print(f"ОРШ-{zi+1} @({cx},{cy}), R={Rz:.1f}, цвет {col}, {zd[c]} ДХ")
    chk(near(px(cx - int(0.42*Rz), cy - int(0.35*Rz)), col, 60), f"ОРШ-{zi+1}: корпус {px(cx-int(0.42*Rz), cy-int(0.35*Rz))}")
    col_v = [px(cx, y) for y in range(cy - int(0.75*Rz), cy + int(0.15*Rz))]
    chk(any(near(cc, (255, 255, 255), 40) for cc in col_v), f"ОРШ-{zi+1}: белая цифра")
    chk(any(near(px(cx, cy + yy), (28, 30, 36), 60) for yy in range(int(0.9*Rz), int(1.35*Rz))), f"ОРШ-{zi+1}: цоколь (скан)")

print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ')
sys.exit(0 if ok else 1)
