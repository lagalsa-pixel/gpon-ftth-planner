# -*- coding: utf-8 -*-
"""
Шаг 43b. Сравнительная карта трасс фидера ЦУ -> ОРШ-2 (с. Пригородное).

Показывает на спутниковой мозаике (Google z18):
  - сеть села (серым, контекст);
  - СТАРУЮ трассу фидера: путь внутри дерева распределения — 1313,6 м (зелёный);
  - НОВУЮ трассу: кратчайший путь по улицам — 683,9 м (красный);
  - маршрут пользователя (белый пунктир) — совпадает с кратчайшим;
  - точку расхождения (81 м от ЦУ), ЦУ и ОРШ-2.

Выход: download/Сравнение_трасс_фидера_ОРШ2_Пригородное.png
"""
import json
import math

from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
KEY = 'prigorodnoe'
OUT = f'{BASE}/download/Сравнение_трасс_фидера_ОРШ2_Пригородное.png'
Q = json.load(open(f'{BASE}/work/route_diag_prigorodnoe.json'))
GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
mpp = GEO['mpp']

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
f = lambda sz, b=True: ImageFont.truetype(FB if b else FR, sz)

# --- окно (px мозаики) со запасом ---
xs = [p[0] for p in Q['user_px'] + Q['sp_px'] + Q['chain']]
ys = [p[1] for p in Q['user_px'] + Q['sp_px'] + Q['chain']]
M = 260
x0, x1 = max(0, int(min(xs)) - M), int(max(xs)) + M
y0, y1 = max(0, int(min(ys)) - M), int(max(ys)) + M
K = 2  # апскейл
S = lambda v: int(round(v * K))

base = Image.open(f'{BASE}/work/{KEY}/mosaic.jpg').convert('RGB').crop((x0, y0, x1, y1))
W, H = base.size
base = base.resize((W * K, H * K), Image.LANCZOS)
W, H = base.size
print(f'окно ({x0},{y0})-({x1},{y1}), канва {W}x{H}, {mpp / K:.4f} м/px')


def T(p):
    return ((p[0] - x0) * K, (p[1] - y0) * K)


ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
dr = ImageDraw.Draw(ov)

# --- 1) все улицы/дороги OSM (контекст: трассы идут по улицам) ---
import sys
sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty  # noqa: E402


def geo_to_px_aff(lat_, lon_):
    return ((lon_ - GEO['west']) * (111320 * math.cos(math.radians(lat_))) / mpp,
            (GEO['north'] - lat_) * 111320 / mpp)


osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
for r_ in osm['roads']:
    pl = [geo_to_px_aff(la, lo) for la, lo in r_['pts']]
    for a_, b_ in zip(pl, pl[1:]):
        pa, pb = T(a_), T(b_)
        if -80 <= pa[0] <= W + 80 and -80 <= pa[1] <= H + 80 and \
           -80 <= pb[0] <= W + 80 and -80 <= pb[1] <= H + 80:
            dr.line([pa, pb], fill=(215, 215, 215, 120), width=S(1))
net = json.load(open(f'{BASE}/work/{KEY}/network_v2.json'))
for d_ in net['drops']:
    a, b = T(d_['poly'][0]), T(d_['poly'][-1])
    if 0 <= b[0] <= W and 0 <= b[1] <= H:
        dr.line([a, b], fill=(255, 225, 0, 70), width=S(1))
# --- 2) старая трасса: путь в дереве (зелёный) ---
chain = [T(p) for p in Q['chain']]
dr.line(chain, fill=(47, 158, 68, 235), width=S(5))

# --- 3) новая трасса: кратчайший путь (красный) ---
sp = [T(p) for p in Q['sp_px']]
dr.line(sp, fill=(224, 49, 49, 250), width=S(5))

# --- 4) маршрут пользователя (белый пунктир) ---


def dashed(pts, fill, width, dash=26, gap=20):
    g = 0.0
    for (x1_, y1_), (x2_, y2_) in zip(pts, pts[1:]):
        L = math.hypot(x2_ - x1_, y2_ - y1_)
        if L < 1e-9:
            continue
        g0, g1 = g, g + L
        seg = dash + gap
        for k in range(int(g0 / seg) - 1, int(g1 / seg) + 1):
            a = max(g0, k * seg)
            b = min(g1, k * seg + dash)
            if b > a:
                t0, t1 = (a - g0) / L, (b - g0) / L
                dr.line([(x1_ + (x2_ - x1_) * t0, y1_ + (y2_ - y1_) * t0),
                         (x1_ + (x2_ - x1_) * t1, y1_ + (y2_ - y1_) * t1)],
                        fill=fill, width=width)
        g = g1


dashed([T(p) for p in Q['user_px']], (255, 255, 255, 230), S(3))

# --- 5) маркеры ---
# ЦУ (конец маршрутов у развилки)
cu = sp[0]
R = S(16)
dr.ellipse([cu[0] - R, cu[1] - R, cu[0] + R, cu[1] + R], fill=(255, 255, 255, 90),
           outline=(255, 255, 255, 255), width=S(3))
pts = []
for i in range(10):
    r = R * (0.55 if i % 2 else 1.0)
    a = -math.pi / 2 + i * math.pi / 5
    pts.append((cu[0] + r * math.cos(a), cu[1] + r * math.sin(a)))
dr.polygon(pts, fill=(255, 40, 40, 255), outline=(255, 255, 255, 255))
dr.text((cu[0] + S(24), cu[1] - S(14)), 'ЦУ', font=f(44), fill=(255, 255, 255, 255),
        stroke_width=S(4), stroke_fill=(90, 0, 0, 255))

# ОРШ-2
oz = sp[-1]
r1, r2 = S(15), S(12)
dr.rectangle([oz[0] - r1, oz[1] - r1, oz[0] + r1, oz[1] + r1], fill=(20, 20, 25, 235))
dr.rectangle([oz[0] - r2, oz[1] - r2, oz[0] + r2, oz[1] + r2], fill=(47, 158, 68, 255),
             outline=(255, 255, 255, 255), width=S(3))
dr.text((oz[0] + S(24), oz[1] - S(14)), 'ОРШ-2', font=f(44), fill=(255, 255, 255, 255),
        stroke_width=S(4), stroke_fill=(15, 15, 15, 255))

# точка расхождения (81 м от ЦУ, узел дерева #17)
dv = T(Q['chain'][17])
dr.ellipse([dv[0] - S(11), dv[1] - S(11), dv[0] + S(11), dv[1] + S(11)],
           fill=(255, 170, 0, 255), outline=(20, 20, 20, 255), width=S(3))
dr.text((dv[0] + S(18), dv[1] + S(10)), 'расхождение: 81 м от ЦУ', font=f(30),
        fill=(255, 235, 180, 255), stroke_width=S(3), stroke_fill=(20, 20, 20, 255))

# --- подписи длин вдоль трасс ---
# зелёная: у северной точки крюка дерева (над трассой)
y_top = min(p[1] for p in Q['chain'])
x_at_top = next(p[0] for p in Q['chain'] if p[1] == y_top)
lab_old = T((x_at_top, y_top))
dr.text((lab_old[0] - S(430), lab_old[1] - S(76)),
        'путь в дереве сети: 1 313,6 м', font=f(36), fill=(140, 235, 165, 255),
        stroke_width=S(4), stroke_fill=(10, 40, 18, 255))
# красная: под нижней (южной) ногой маршрута, у ЦУ
y_bot = max(p[1] for p in Q['sp_px'])
x_mid_bot = sorted(p[0] for p in Q['sp_px'])[len(Q['sp_px']) // 4]
lab_new = T((x_mid_bot, y_bot))
dr.text((lab_new[0] - S(120), lab_new[1] + S(26)),
        'кратчайший по улицам: 683,9 м (−48%)', font=f(36), fill=(255, 190, 190, 255),
        stroke_width=S(4), stroke_fill=(60, 8, 8, 255))

# ============================================== композит + шапка/легенда ==
HH = S(210)
canvas = Image.new('RGB', (W, H + HH), (10, 18, 30))
canvas.paste(base, (0, HH))
canvas.paste(Image.alpha_composite(Image.new('RGBA', (W, H), (0, 0, 0, 0)),
                                   ov).convert('RGB'), (0, HH))
dh = ImageDraw.Draw(canvas)

dh.text((S(26), S(14)),
        'с. Пригородное — фидер ЦУ → ОРШ-2: логика прокладки трассы (схема D)',
        font=f(46), fill=(240, 245, 250))
dh.text((S(26), S(74)),
        'путь точка-точка внутри дерева Штейнера вдвое длиннее кратчайшего маршрута по улицам; '
        'фидер прокладывается по кратчайшему пути дорожного графа',
        font=f(28, False), fill=(170, 185, 200))
dh.text((S(26), S(112)),
        'трасса в дереве (зелёный): 1 313,6 м   ·   кратчайший путь Дейкстры (красный): 683,9 м   ·   '
        'маршрут пользователя (белый пунктир): 681,3 м   ·   экономия 630 м (48%)',
        font=f(30), fill=(255, 220, 120))
dh.text((S(26), S(154)),
        'серым — улицы и дороги OSM, жёлтым — дропы; расхождение трасс — оранжевая точка; '
        f'масштаб {mpp / K:.2f} м/px (Google z18, Web Mercator, привязка по OSM-якорю ±0,2 м)',
        font=f(26, False), fill=(140, 155, 170))

# масштабная линейка: 200 м
sb_m = 200
sb_px = sb_m / mpp * K
x0s, y0s = W - int(sb_px) - S(40), HH + H - S(46)
dh.line([(x0s, y0s), (x0s + sb_px, y0s)], fill=(255, 255, 255), width=S(5))
for xx in (x0s, x0s + sb_px / 2, x0s + sb_px):
    dh.line([(xx, y0s - S(9)), (xx, y0s + S(9))], fill=(255, 255, 255), width=S(4))
dh.text((x0s + sb_px / 2 - S(40), y0s - S(46)), f'{sb_m} м', font=f(30), fill=(255, 255, 255))

# стрелка севера
nx, ny = W - S(70), HH + S(64)
dh.polygon([(nx, ny - S(34)), (nx - S(13), ny + S(16)), (nx, ny + S(6)), (nx + S(13), ny + S(16))],
           outline=(255, 255, 255), width=S(3))
dh.text((nx - S(8), ny + S(18)), 'С', font=f(28), fill=(255, 255, 255))

canvas.save(OUT)
print('сохранено:', OUT, f'{canvas.width}x{canvas.height}')
