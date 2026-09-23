# -*- coding: utf-8 -*-
"""
Шаг 33. Рендер карт зон ОРШ поверх сетей сёл — схема D (зонные ОРШ 1:64,
единый узел OLT, S_MIN = 15).

Базовые снимки:
  * Солнечное, Перевальное, Пригородное, Алтайский — work/<key>/mosaic.jpg
    (координаты сетей совпадают с мозаикой пиксельно, NCC-проверка шага 32);
  * Верхнеберезовка, Винное — work/<key>/base_restitch.png (перешив Google z18
    в координатном пространстве мозаики, шаг 32b, смещение (offx, offy)).

Слои (снизу вверх): зоны-оболочки -> дропы -> ствол (серый) -> распределительная
сеть зоны (цвет зоны) -> фидер ЦУ->ОРШ (пунктир цвета зоны) -> муфты ->
домохозяйства (цвет зоны) -> зонные ОРШ -> ЦУ. Шапка, легенда зон, условные
обозначения, масштабная линейка, стрелка севера.

Выход: download/snp_vko/<NN>_<Село>_зоны_ОРШ_схема_D.jpg (JPG q90, 4:4:4)
        work/qa/zone_maps/<NN>_preview.png (превью для контроля).
"""
import json, math, os, sys, gc, time, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
DL = f'{BASE}/download/snp_vko'
os.makedirs(DL, exist_ok=True)
os.makedirs(f'{BASE}/work/qa/zone_maps', exist_ok=True)

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)
Tree, nkey = de28.Tree, de28.nkey

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}

from PIL import Image, ImageDraw, ImageFont
Image.MAX_IMAGE_PIXELS = None

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

# ---------------------------------------------------------------- стиль ----
C_DROP = (255, 225, 0, 225)
C_COUP = (0, 255, 225, 255)
C_COUP_OUT = (0, 60, 60, 255)
C_TRUNK = (215, 225, 240, 235)
C_HH_OUT = (25, 25, 25, 255)
C_CU = (224, 49, 49)                 # ЦУ (корневая зона) — красный
PALETTE = [                           # зонные цвета (насыщенные — линии/маркеры)
    (25, 113, 194),                   # синий
    (47, 158, 68),                    # зелёный
    (240, 140, 0),                    # оранжевый
    (156, 54, 181),                   # фиолетовый
    (12, 133, 153),                   # глубокий бирюзовый
    (230, 73, 128),                   # розовый
    (102, 168, 15),                   # лаймовый
    (112, 72, 232),                   # фиолетово-синий
    (160, 90, 44),                    # коричневый
]
HH = 150                              # высота шапки
DASH, GAP = 30, 22                    # пунктир фидера


def fnt(sz, bold=True):
    return ImageFont.truetype(FB if bold else FR, sz)


def hull(points):
    """Выпуклая оболочка (monotone chain)."""
    pts = sorted(set((round(x, 1), round(y, 1)) for x, y in points))
    if len(pts) < 3:
        return [tuple(p) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def draw_dashed(dr, pts, fill, width, phase=0.0):
    """Пунктир по ломаной pts: пересечение отрезков [k*seg+phase, +DASH] с сегментами."""
    seg = DASH + GAP
    g = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            continue
        g0, g1 = g, g + L
        for k in range(int(math.floor((g0 - phase) / seg)) - 1,
                       int(math.ceil((g1 - phase) / seg)) + 1):
            a = max(g0, k * seg + phase)
            b = min(g1, k * seg + phase + DASH)
            if b > a:
                t0, t1 = (a - g0) / L, (b - g0) / L
                dr.line([(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0),
                         (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)],
                        fill=fill, width=width)
        g += L


class Labels:
    """Размещение подписей без наложений (жадно, 8 кандидатов)."""

    def __init__(self):
        self.boxes = []

    def place(self, x, y, tw, th, W, H, pad=14):
        for dx, dy in ((pad, -th - pad), (-tw - pad, -th - pad), (pad, pad),
                       (-tw - pad, pad), (pad, -th // 2), (-tw - pad, -th // 2),
                       (tw // 2 - tw // 2, -th - 2 * pad), (0, pad + 4)):
            bx, by = x + dx, y + dy
            if bx < 8 or by < 8 or bx + tw > W - 8 or by + th > H - 8:
                continue
            box = (bx - 6, by - 6, bx + tw + 6, by + th + 6)
            if any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]
                   for b in self.boxes):
                continue
            self.boxes.append(box)
            return bx, by
        return None


def render_village(v):
    t_start = time.time()
    key = v['key']
    db = DBY[key]
    t = Tree(v)
    cuts, _ = t.partition_greedy(15.0)
    cutset = set(cuts)

    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cutset else zr[t.parent[u]]

    # --- база ---
    if key in ('solnechnoe', 'perevalnoe', 'prigorodnoe', 'altaiskiy'):
        base_path = f'{BASE}/work/{key}/mosaic.jpg'
        offx = offy = 0.0
    else:
        meta = json.load(open(f'{BASE}/work/{key}/restitch.json'))
        base_path = meta['img']
        offx, offy = meta['offx'], meta['offy']

    base = Image.open(base_path).convert('RGB')
    W, H = base.size
    print(f'  база {W}x{H} за {time.time() - t_start:.0f} с', flush=True)
    mpp = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]['mpp']

    def T(p):
        return (p[0] + offx, p[1] + offy)

    net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    adj_keys = set(zr.keys())

    def zone_of_drop(d):
        k = ck.get(d['coupler'])
        if k is None or k not in adj_keys:
            return t.root          # как в модели шага 28: дроп вне дерева -> ЦУ
        return zr[k]

    # --- нумерация зон: по числу ДХ (по убыванию); ЦУ — отдельно ---
    zone_dh = defaultdict(int)
    for node, dh in t.homes.items():
        zone_dh[zr[node]] += dh
    order = sorted(cuts, key=lambda c: -zone_dh[c])
    zcolor = {t.root: C_CU}
    zname = {t.root: 'ЦУ'}
    for i, c in enumerate(order):
        zcolor[c] = PALETTE[i % len(PALETTE)]
        zname[c] = f'ОРШ-{i + 1}'

    # точки зон: дома + муфты + корень
    zpts = defaultdict(list)
    for d in net['drops']:
        zpts[zone_of_drop(d)].append(d['poly'][-1])
    for c in net['couplers']:
        k = nkey([c['x'], c['y']])
        if k in zr:
            zpts[zr[k]].append((c['x'], c['y']))
    for z in [t.root] + list(cuts):
        zpts[z].append(z)

    # ================================================================ СЛОИ =
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)

    # 1) оболочки зон
    for z in [t.root] + list(cuts):
        col = zcolor[z]
        hpts = [T(p) for p in zpts[z]]
        hp = hull(hpts)
        if len(hp) >= 3:
            dr.polygon(hp, fill=col + (38,), outline=col + (170,), width=4)

    # 2) дропы
    for d in net['drops']:
        poly = [T(p) for p in d['poly']]
        if len(poly) >= 2:
            dr.line(poly, fill=C_DROP, width=2)

    # 3) магистраль: ствол (зона ЦУ) серым, зоны — своим цветом
    for (p, ch, L) in t.edges:
        z = zr[ch]
        col = C_TRUNK if z == t.root else zcolor[z] + (235,)
        dr.line([T(p), T(ch)], fill=col, width=5)

    # 4) фидеры ЦУ -> зонный ОРШ: пунктир цвета зоны по стволу
    for i, c in enumerate(order):
        chain = [c]
        u = c
        while t.parent[u] is not None:
            u = t.parent[u]
            chain.append(u)
        chain.reverse()
        pts = [T(u) for u in chain]
        draw_dashed(dr, pts, zcolor[c] + (215,), 6, phase=i * (DASH + GAP) / 2.0)

    # 5) муфты
    for c in net['couplers']:
        x, y = T((c['x'], c['y']))
        dr.rectangle([x - 6, y - 6, x + 6, y + 6], fill=C_COUP,
                     outline=C_COUP_OUT, width=2)

    # 6) домохозяйства (цвет зоны)
    for d in net['drops']:
        col = zcolor[zone_of_drop(d)]
        x, y = T(d['poly'][-1])
        dr.rectangle([x - 4, y - 4, x + 4, y + 4], fill=col + (255,),
                     outline=C_HH_OUT, width=1)

    # 7) зонные ОРШ
    f_z1 = fnt(34)
    f_z2 = fnt(26, bold=False)
    labels = Labels()
    for c in order:
        col = zcolor[c]
        x, y = T(c)
        dr.rectangle([x - 17, y - 17, x + 17, y + 17], fill=(20, 20, 25, 235))
        dr.rectangle([x - 14, y - 14, x + 14, y + 14], fill=col + (255,),
                     outline=(255, 255, 255, 255), width=4)
        name = zname[c]
        dh = zone_dh[c]
        tw = max(dr.textlength(name, font=f_z1), dr.textlength(f'{dh} ДХ', font=f_z2))
        pos = labels.place(x, y, int(tw), 34 + 30, W, H)
        if pos:
            bx, by = pos
            dr.rectangle([bx - 8, by - 6, bx + tw + 8, by + 34 + 30 + 6],
                         fill=(12, 14, 20, 130))
            dr.text((bx, by), name, font=f_z1, fill=(255, 255, 255, 255),
                    stroke_width=4, stroke_fill=(15, 15, 15, 255))
            dr.text((bx, by + 36), f'{dh} ДХ', font=f_z2, fill=(255, 235, 180, 255),
                    stroke_width=3, stroke_fill=(15, 15, 15, 255))

    # 8) ЦУ
    ax, ay = T((net['anchor']['x'], net['anchor']['y']))
    R = 30
    dr.ellipse([ax - R, ay - R, ax + R, ay + R], fill=(255, 255, 255, 90),
               outline=(255, 255, 255, 255), width=5)
    pts = []
    for i in range(10):
        r = R * (0.55 if i % 2 else 1.0)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    dr.polygon(pts, fill=(255, 40, 40, 255), outline=(255, 255, 255, 255))
    f_cu = fnt(34)
    t1 = 'ЦУ — ОРШ (единый узел OLT)'
    t2 = f"корневая зона: {zone_dh[t.root]} ДХ"
    pos = labels.place(ax, ay, int(dr.textlength(t1, font=f_cu)), 34 + 28, W, H)
    if pos:
        bx, by = pos
        tw1 = int(dr.textlength(t1, font=f_cu))
        dr.rectangle([bx - 8, by - 6, bx + tw1 + 8, by + 34 + 28 + 6],
                     fill=(12, 14, 20, 130))
        dr.text((bx, by), t1, font=f_cu, fill=(255, 255, 255, 255),
                stroke_width=4, stroke_fill=(120, 0, 0, 255))
        dr.text((bx, by + 36), t2, font=f_z2, fill=(255, 235, 180, 255),
                stroke_width=3, stroke_fill=(120, 0, 0, 255))

    # ======================================================== ШАПКА/ЛЕГЕНДА =
    canvas = Image.new('RGB', (W, H + HH), (10, 18, 30))
    map_rgb = base.convert('RGBA')
    map_rgb.alpha_composite(ov)
    canvas.paste(map_rgb.convert('RGB'), (0, HH))
    dh = ImageDraw.Draw(canvas)

    f1, f2, f3 = fnt(46), fnt(27, bold=False), fnt(27)
    dh.text((26, 12), f"с. {db['name']} — схема D: зонные ОРШ (сплиттеры 1:64) при едином узле OLT",
            font=f1, fill=(240, 245, 250))
    dh.text((26, 68), f"{db['raion']} · {db['so']} · спутник Google z18 ({mpp:.2f} м/px) · "
                      f"топология сети, муфты и дропы — без изменений (как в схемах A/B/C)",
            font=f2, fill=(170, 185, 200))
    st = (f"ДХ: {db['dhx_served']}   ·   зонных ОРШ: {db['n_zones']} + ЦУ   ·   "
          f"волокно-км: {db['fiber_km']:.1f}   ·   магистраль: {db['cable_km_raw']:.1f} км   ·   "
          f"дроп-кабель: {db['drop_cable_km']:.1f} км   ·   сплиттеры 1×64: {db['splitters64']}")
    dh.text((26, 106), st, font=f3, fill=(255, 220, 120))

    # --- легенда зон (слева снизу) ---
    rows = []
    rows.append(('ЦУ', C_CU, f"корневая зона: {zone_dh[t.root]} ДХ · "
                             f"{db['zones'][0]['splitters']}×1:64 · кросс {db['zones'][0]['orsh_ports']} портов"))
    for i, c in enumerate(order):
        zs = db['zones'][1 + cuts.index(c)]
        rows.append((zname[c], zcolor[c],
                     f"{zone_dh[c]} ДХ · {zs['splitters']}×1:64 · фидер {zs['feeder_fibers']} вол. · "
                     f"{zs['root_dist_m'] / 1000:.2f} км от ЦУ"))
    if not cuts:
        rows.append(('--', (120, 120, 120),
                     'зонные ОРШ не образуются: село компактное, экономия ниже S_MIN'))

    fl_t, fl_r = fnt(32), fnt(28, bold=False)
    LW = 900
    LHH = 58 + len(rows) * 52 + 36 + 50 + 7 * 52 + 28
    lg = Image.new('RGBA', (LW, LHH), (8, 12, 20, 218))
    ld = ImageDraw.Draw(lg)
    ld.text((20, 14), 'ЗОНЫ ОРШ (схема D, S_MIN = 15)', font=fl_t, fill=(240, 240, 240))
    yy = 58
    for name, col, txt in rows:
        ld.rectangle([20, yy - 15, 52, yy + 15], fill=col, outline=(255, 255, 255), width=2)
        ld.text((64, yy - 15), f'{name}: {txt}', font=fl_r, fill=(228, 232, 238))
        yy += 52
    yy += 14
    ld.line([(20, yy), (LW - 20, yy)], fill=(90, 100, 115), width=2)
    yy += 18
    ld.text((20, yy), 'УСЛОВНЫЕ ОБОЗНАЧЕНИЯ', font=fl_t, fill=(240, 240, 240))
    yy += 50

    # ствол
    ld.line([(20, yy), (52, yy)], fill=C_TRUNK[:3], width=6)
    ld.text((64, yy - 15), 'ствол сети: волокна зоны ЦУ + фидеры зон', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # зона
    ld.line([(20, yy), (52, yy)], fill=PALETTE[0], width=6)
    ld.text((64, yy - 15), 'распределительная сеть зоны (цвет зоны)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # пунктир
    draw_dashed(ld, [(20, yy), (52, yy)], PALETTE[1] + (235,), 7)
    ld.text((64, yy - 15), 'фидер ЦУ → зонный ОРШ (ceil(1,25 × сплиттеры зоны))', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # дроп
    ld.line([(20, yy), (52, yy)], fill=C_DROP[:3], width=4)
    ld.text((64, yy - 15), 'дроп-кабель к домохозяйству', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # муфта
    ld.rectangle([28, yy - 12, 44, yy + 12], fill=C_COUP[:3], outline=(0, 60, 60), width=2)
    ld.text((64, yy - 15), 'муфта оптическая (ветвление)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # ДХ
    ld.rectangle([30, yy - 9, 42, yy + 9], fill=PALETTE[2], outline=(25, 25, 25))
    ld.text((64, yy - 15), 'домохозяйство (цвет его зоны)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # зонный ОРШ
    ld.rectangle([24, yy - 15, 48, yy + 15], fill=(20, 20, 25))
    ld.rectangle([27, yy - 12, 45, yy + 12], fill=PALETTE[3], outline=(255, 255, 255), width=3)
    ld.text((64, yy - 15), 'зонный ОРШ — шкаф уличный (в муфте ветвления)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    # ЦУ
    ld.ellipse([28, yy - 15, 44, yy + 15], outline=(255, 255, 255), width=3)
    ld.polygon([(36 - 5, yy), (33, yy - 9), (39, yy - 9)], fill=(255, 40, 40))
    ld.text((64, yy - 15), 'ЦУ — ОРШ села, точка входа фидера (единый OLT)', font=fl_r, fill=(228, 232, 238))

    canvas.paste(lg, (16, HH + H - LHH - 16), lg)

    # --- масштабная линейка ---
    cand = [100, 200, 500, 1000, 2000]
    sb_m = max((m for m in cand if m / mpp <= 1400), key=lambda m: m / mpp)
    sb_px = sb_m / mpp
    x0 = W - int(sb_px) - 60
    y0 = HH + H - 46
    txt = f'{sb_m} м' if sb_m < 1000 else f'{sb_m // 1000} км'
    dh.line([(x0, y0), (x0 + sb_px, y0)], fill=(255, 255, 255), width=5)
    for xx in (x0, x0 + sb_px / 2, x0 + sb_px):
        dh.line([(xx, y0 - 9), (xx, y0 + 9)], fill=(255, 255, 255), width=4)
    dh.text((x0 + sb_px / 2 - 34, y0 - 44), txt, font=fnt(27), fill=(255, 255, 255))

    # --- стрелка севера ---
    nx, ny = W - 70, HH + 64
    dh.polygon([(nx, ny - 34), (nx - 13, ny + 16), (nx, ny + 6), (nx + 13, ny + 16)],
               outline=(255, 255, 255), width=3)
    dh.text((nx - 8, ny + 18), 'С', font=fnt(27), fill=(255, 255, 255))

    # --- сохранение ---
    fname = f"{DL}/{db['num']}_{db['name']}_зоны_ОРШ_схема_D.jpg"
    canvas.save(fname, quality=90, subsampling=0)

    prev = canvas.copy()
    prev.thumbnail((1800, 1800), Image.LANCZOS)
    prev.save(f"{BASE}/work/qa/zone_maps/{db['num']}_preview.png")

    sz = os.path.getsize(fname) / 1e6
    print(f"{db['num']} {db['name']:<18} {canvas.width}x{canvas.height}  "
          f"зон {len(cuts)}+ЦУ  {fname.split('/')[-1]} ({sz:.1f} МБ)  "
          f"[{time.time() - t_start:.0f} с]", flush=True)
    del base, ov, map_rgb, canvas, prev
    gc.collect()
    return fname


def main():
    outs = []
    for v in de28.VILLAGES:
        outs.append(render_village(v))
    print('\nГотово:', len(outs), 'карт ->', DL)


if __name__ == '__main__':
    main()
