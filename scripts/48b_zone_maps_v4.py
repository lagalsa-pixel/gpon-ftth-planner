# -*- coding: utf-8 -*-
"""
Шаг 48b. Рендер карт зон ОРШ (схема D, топология v4 = уточнённые ДХ) на кадрах пользователя.

Отличия от шага 37 (v1-карты):
  - данные: work/boq_decentral_data_v4.json (врезы = cut_log v3, ОРШ = медианы
    зон — «в центре сектора»);
  - фидеры ЦУ -> зонный ОРШ: ПУНКТИР ПО КРАТЧАЙШЕМУ ПУТИ дорожного графа
    (Дейкстра), обрезанного границей НП (шаг 46) — а не по стволу дерева;
  - маркер зонного ОРШ стоит в медиане зоны (orsh_px), не в узле вреза;
  - на карту наносится ГРАНИЦА НАСЕЛЁННОГО ПУНКТА (морфология застройки,
    шаг 46a) — белым пунктиром; сеть и фидеры ей ограничены;
  - Верхнеберезовка: кадра пользователя нет — база work/<key>/mosaic.jpg
    (полная мозаика, тождественное преобразование), как в шаге 33.

Слои, цвета, шапка, легенда, масштабная линейка, стрелка севера — как в 37.

Выход: download/snp_vko/<NN>_<Село>_зоны_ОРШ_схема_D.jpg (замена v1-карт)
        work/qa/zone_maps_v4/<NN>_preview.png
Запуск: python3 48_zone_maps_v4.py <key>|all
"""
import json, math, os, sys, gc, time, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
DL = f'{BASE}/download/snp_vko'
QAD = f'{BASE}/work/qa/zone_maps_v4'
os.makedirs(QAD, exist_ok=True)


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de46 = load_mod('de46', f'{BASE}/scripts/46_topology_v3.py')
Tree, nkey = de28.Tree, de28.nkey

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}
ANA = {v['key']: v for v in json.load(open(f'{BASE}/work/v3_analysis.json'))['villages']}

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
C_BOUND = (255, 255, 255, 200)       # граница НП — белый пунктир
PALETTE = [
    (25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
    (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
    (160, 90, 44),
]

ALL_KEYS = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe',
            'prigorodnoe', 'altaiskiy']
CROPS = {'solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altaiskiy'}


def fnt(sz, bold=True):
    return ImageFont.truetype(FB if bold else FR, sz)


def fit_font(dr, text, sz, max_w, bold=True):
    f = fnt(sz, bold)
    w = dr.textlength(text, font=f)
    if w <= max_w:
        return f
    sz2 = max(int(sz * 0.55), int(sz * max_w / max(w, 1)))
    return fnt(sz2, bold)


def hull(points):
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


def draw_dashed(dr, pts, fill, width, phase=0.0, dash=30, gap=22):
    seg = dash + gap
    g = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            continue
        g0, g1 = g, g + L
        for k in range(int(math.floor((g0 - phase) / seg)) - 1,
                       int(math.ceil((g1 - phase) / seg)) + 1):
            a = max(g0, k * seg + phase)
            b = min(g1, k * seg + phase + dash)
            if b > a:
                t0, t1 = (a - g0) / L, (b - g0) / L
                dr.line([(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0),
                         (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)],
                        fill=fill, width=width)
        g += L


class Labels:
    def __init__(self, S):
        self.S = S
        self.boxes = []

    def place(self, x, y, tw, th, W, H):
        S = self.S
        pad = S(14)
        for dx, dy in ((pad, -th - pad), (-tw - pad, -th - pad), (pad, pad),
                       (-tw - pad, pad), (pad, -th // 2), (-tw - pad, -th // 2),
                       (0, -th - 2 * pad), (0, pad + S(4))):
            bx, by = x + dx, y + dy
            m = S(8)
            if bx < m or by < m or bx + tw > W - m or by + th > H - m:
                continue
            p = S(6)
            box = (bx - p, by - p, bx + tw + p, by + th + p)
            if any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]
                   for b in self.boxes):
                continue
            self.boxes.append(box)
            return bx, by
        return None


def render_village(key):
    t_start = time.time()
    v = next(v for v in de28.VILLAGES if v['key'] == key)
    db = DBY[key]
    t = Tree(v)
    cuts = [tuple(l['node']) for l in db['cut_log']]      # врезы v3
    cutset = set(cuts)

    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cutset else zr[t.parent[u]]

    # --- v3: модель для фидерных трасс (Дейкстра в границе НП) и медиан ---
    V3 = de46.VillageV3(v)
    med_model = V3.medians_of(cuts)                      # врез -> точная медиана
    for z in cuts:
        zd = db['zones'][1 + cuts.index(z)]
        assert tuple(round(x, 1) for x in med_model[z]) == tuple(zd['orsh_px']), \
            f'{key}: медиана книги != модели для {z}'

    # --- база и преобразование ---
    if key in CROPS:
        tr = json.load(open(f'{BASE}/work/{key}/crop_transform.json', encoding='utf-8'))
        Mi = tr['M_inv']                                   # old mosaic px -> crop px
        scale = tr['scale']
        img_path = tr['new_image']
        if not os.path.isabs(img_path):
            img_path = os.path.join(BASE, img_path)
    else:
        Mi = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]           # ВБ: полная мозаика
        scale = 1.0
        img_path = f'{BASE}/work/{key}/mosaic.jpg'
    k = 1.0 / scale
    S = lambda val: max(1, int(round(val * k)))
    mpp = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]['mpp']
    mpp_new = mpp * scale

    def T(p):
        x, y = p
        return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
                Mi[1][0] * x + Mi[1][1] * y + Mi[1][2])

    base = Image.open(img_path).convert('RGB')
    W, H = base.size
    print(f'  база {W}x{H}, k={k:.2f}, {mpp_new:.4f} м/px', flush=True)

    net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    adj_keys = set(zr.keys())

    def zone_of_drop(d):
        kk = ck.get(d['coupler'])
        if kk is None or kk not in adj_keys:
            return t.root
        return zr[kk]

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

    # точки зон: дома + муфты + врез + медиана (ОРШ)
    zpts = defaultdict(list)
    for d in net['drops']:
        zpts[zone_of_drop(d)].append(d['poly'][-1])
    for c in net['couplers']:
        kk = nkey([c['x'], c['y']])
        if kk in zr:
            zpts[zr[kk]].append((c['x'], c['y']))
    for z in [t.root] + list(cuts):
        zpts[z].append(z)
        if z in med_model:
            zpts[z].append(med_model[z])

    # ================================================================ СЛОИ =
    DASH, GAP = S(30), S(22)
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)

    # 0) граница НП (морфология застройки) — белый пунктир
    ring = ANA[key]['boundary_poly_px']
    bpts = [T(p) for p in ring]
    if len(bpts) >= 3:
        draw_dashed(dr, bpts, C_BOUND, S(4), dash=S(26), gap=S(18))

    # 1) оболочки зон
    for z in [t.root] + list(cuts):
        col = zcolor[z]
        hpts = [T(p) for p in zpts[z]]
        hp = hull(hpts)
        if len(hp) >= 3:
            dr.polygon(hp, fill=col + (38,), outline=col + (170,), width=S(4))

    # 2) дропы
    for d in net['drops']:
        poly = [T(p) for p in d['poly']]
        if len(poly) >= 2:
            dr.line(poly, fill=C_DROP, width=S(2))

    # 3) магистраль: ствол (зона ЦУ) серым, зоны — своим цветом
    for (p, ch, L) in t.edges:
        z = zr[ch]
        col = C_TRUNK if z == t.root else zcolor[z] + (235,)
        dr.line([T(p), T(ch)], fill=col, width=S(5))

    # 4) фидеры ЦУ -> зонный ОРШ: пунктир цвета зоны ПО КРАТЧАЙШЕМУ ПУТИ (v3)
    for i, c in enumerate(order):
        med = med_model[c]
        chain_idx = [V3.idx[med]]
        cur = V3.idx[med]
        while cur != V3.root_i and V3.pred[cur] >= 0:
            cur = int(V3.pred[cur])
            chain_idx.append(cur)
        chain_idx.reverse()                       # ЦУ -> ОРШ
        pts = [T(V3.P[j]) for j in chain_idx]
        draw_dashed(dr, pts, zcolor[c] + (215,), S(6),
                    phase=i * (DASH + GAP) / 2.0, dash=DASH, gap=GAP)

    # 5) муфты
    for c in net['couplers']:
        x, y = T((c['x'], c['y']))
        r = S(6)
        dr.rectangle([x - r, y - r, x + r, y + r], fill=C_COUP,
                     outline=C_COUP_OUT, width=S(2))

    # 6) домохозяйства (цвет зоны)
    for d in net['drops']:
        col = zcolor[zone_of_drop(d)]
        x, y = T(d['poly'][-1])
        r = S(4)
        dr.rectangle([x - r, y - r, x + r, y + r], fill=col + (255,),
                     outline=C_HH_OUT, width=1)

    # 7) зонные ОРШ — в медиане зоны (центр сектора)
    f_z1 = fnt(S(34))
    f_z2 = fnt(S(26), bold=False)
    labels = Labels(S)
    # подписи не должны перекрывать маркеры ОРШ и ЦУ — регистрируем их зоны
    for c in order:
        mx_, my_ = T(med_model[c])
        r_ = S(26)
        labels.boxes.append((mx_ - r_, my_ - r_, mx_ + r_, my_ + r_))
    ax0, ay0 = T((net['anchor']['x'], net['anchor']['y']))
    R0 = S(42)
    labels.boxes.append((ax0 - R0, ay0 - R0, ax0 + R0, ay0 + R0))
    for c in order:
        col = zcolor[c]
        x, y = T(med_model[c])
        r1, r2 = S(17), S(14)
        dr.rectangle([x - r1, y - r1, x + r1, y + r1], fill=(20, 20, 25, 235))
        dr.rectangle([x - r2, y - r2, x + r2, y + r2], fill=col + (255,),
                     outline=(255, 255, 255, 255), width=S(4))
        name = zname[c]
        dh_ = zone_dh[c]
        tw = max(dr.textlength(name, font=f_z1), dr.textlength(f'{dh_} ДХ', font=f_z2))
        pos = labels.place(x, y, int(tw), S(34) + S(30), W, H)
        if pos:
            bx, by = pos
            p = S(8)
            dr.rectangle([bx - p, by - S(6), bx + tw + p, by + S(34) + S(30) + S(6)],
                         fill=(12, 14, 20, 130))
            dr.text((bx, by), name, font=f_z1, fill=(255, 255, 255, 255),
                    stroke_width=S(4), stroke_fill=(15, 15, 15, 255))
            dr.text((bx, by + S(36)), f'{dh_} ДХ', font=f_z2, fill=(255, 235, 180, 255),
                    stroke_width=S(3), stroke_fill=(15, 15, 15, 255))

    # 8) ЦУ
    ax, ay = T((net['anchor']['x'], net['anchor']['y']))
    R = S(30)
    dr.ellipse([ax - R, ay - R, ax + R, ay + R], fill=(255, 255, 255, 90),
               outline=(255, 255, 255, 255), width=S(5))
    pts = []
    for i in range(10):
        r = R * (0.55 if i % 2 else 1.0)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    dr.polygon(pts, fill=(255, 40, 40, 255), outline=(255, 255, 255, 255))
    f_cu = fnt(S(34))
    t1 = 'ЦУ — ОРШ (единый узел OLT)'
    t2 = f"корневая зона: {zone_dh[t.root]} ДХ"
    pos = labels.place(ax, ay, int(dr.textlength(t1, font=f_cu)), S(34) + S(28), W, H)
    if pos:
        bx, by = pos
        tw1 = int(dr.textlength(t1, font=f_cu))
        p = S(8)
        dr.rectangle([bx - p, by - S(6), bx + tw1 + p, by + S(34) + S(28) + S(6)],
                     fill=(12, 14, 20, 130))
        dr.text((bx, by), t1, font=f_cu, fill=(255, 255, 255, 255),
                stroke_width=S(4), stroke_fill=(120, 0, 0, 255))
        dr.text((bx, by + S(36)), t2, font=f_z2, fill=(255, 235, 180, 255),
                stroke_width=S(3), stroke_fill=(120, 0, 0, 255))

    # ================================================ КОМПОЗИТ ПОЛОСАМИ ====
    HH = S(150)
    canvas = Image.new('RGB', (W, H + HH), (10, 18, 30))
    step = 2048
    for y0 in range(0, H, step):
        y1 = min(H, y0 + step)
        strip = base.crop((0, y0, W, y1)).convert('RGBA')
        strip.alpha_composite(ov.crop((0, y0, W, y1)))
        canvas.paste(strip.convert('RGB'), (0, HH + y0))
        del strip
    del ov
    gc.collect()
    print(f'  композит за {time.time() - t_start:.0f} с', flush=True)

    # ======================================================== ШАПКА/ЛЕГЕНДА =
    dh_ = ImageDraw.Draw(canvas)
    mx = S(26)
    f1 = fit_font(dh_, f"с. {db['name']} — схема D (v4): зонные ОРШ в центрах секторов, фидеры — кратчайшие пути в границе НП",
                  S(46), W - 2 * mx)
    dh_.text((mx, S(12)),
             f"с. {db['name']} — схема D (v4): зонные ОРШ в центрах секторов, фидеры — кратчайшие пути в границе НП",
             font=f1, fill=(240, 245, 250))
    l2 = (f"{db['raion']} · {db['so']} · кадр {'пользователя' if key in CROPS else 'полной мозаики'} "
          f"({mpp_new:.2f} м/px, спутник Google z18 ×{k:.0f}) · дерево сети, муфты и дропы — без изменений (как в схемах A/B/C); "
          f"граница НП — морфология застройки (шаг 46)")
    dh_.text((mx, S(68)), l2, font=fit_font(dh_, l2, S(27), W - 2 * mx, bold=False),
             fill=(170, 185, 200))
    st = (f"ДХ: {db['dhx_served']}   ·   зонных ОРШ: {db['n_zones']} + ЦУ   ·   "
          f"волокно-км: {db['fiber_km']:.1f}   ·   магистраль: {db['cable_km_raw']:.1f} км   ·   "
          f"дроп-кабель: {db['drop_cable_km']:.1f} км   ·   сплиттеры 1×64: {db['splitters64']}")
    dh_.text((mx, S(106)), st, font=fit_font(dh_, st, S(27), W - 2 * mx), fill=(255, 220, 120))

    # --- легенда зон ---
    rows = []
    rows.append(('ЦУ', C_CU, f"корневая зона: {zone_dh[t.root]} ДХ · "
                             f"{db['zones'][0]['splitters']}×1:64 · кросс {db['zones'][0]['orsh_ports']} портов"))
    for i, c in enumerate(order):
        zs = db['zones'][1 + cuts.index(c)]
        rows.append((zname[c], zcolor[c],
                     f"{zone_dh[c]} ДХ · {zs['splitters']}×1:64 · фидер {zs['feeder_fibers']} вол. · "
                     f"{zs['root_dist_m'] / 1000:.2f} км от ЦУ · ОРШ в центре сектора"
                     + (f" (сдвиг {zs['median_shift_m']:.0f} м)" if zs['median_shift_m'] > 1 else "")))
    if not cuts:
        rows.append(('--', (120, 120, 120),
                     'зонные ОРШ не образуются: село компактное, экономия ниже S_MIN'))

    fl_t, fl_r = fnt(S(32)), fnt(S(28), bold=False)
    LW = S(900)
    LHH = S(58 + len(rows) * 52 + 36 + 50 + 8 * 52 + 28)
    m = S(20)
    hh_pts = [T(d['poly'][-1]) for d in net['drops']]
    coupler_pts = [T((c['x'], c['y'])) for c in net['couplers']]
    orsh_pts = [T(med_model[c]) for c in order]
    cu_pt = T((net['anchor']['x'], net['anchor']['y']))

    def covered_score(lx, ly):
        s = 0
        for pts, w in ((hh_pts, 1), (coupler_pts, 2), (orsh_pts, 20)):
            for (hx_, hy_) in pts:
                if lx - m <= hx_ <= lx + LW + m and ly - m <= hy_ <= ly + LHH + m:
                    s += w
        if lx - m <= cu_pt[0] <= lx + LW + m and ly - m <= cu_pt[1] <= ly + LHH + m:
            s += 50
        return s

    cands = [
        ('BL', (S(16), H - LHH - S(16))),
        ('BR', (W - LW - S(16), H - LHH - S(16))),
        ('ML', (S(16), (H - LHH) // 2)),
        ('MR', (W - LW - S(16), (H - LHH) // 2)),
        ('TL', (S(16), S(16))),
    ]
    for tag, (x, y) in cands:
        print(f'  легенда {tag}: вес перекрытых {covered_score(x, y)}', flush=True)
    lg_tag, (lx, ly) = min(((tag, pos) for tag, pos in cands),
                           key=lambda tp: (covered_score(*tp[1]), cands.index(tp)))
    lg_pos = (lx, ly + HH)
    legend_right = lx > (W - LW) / 2
    print(f'  выбор позиции легенды: {lg_tag}', flush=True)
    # сайдкар для числового QA (49): прямоугольник панели в координатах канвы
    json.dump(dict(tag=lg_tag, x=lg_pos[0], y=lg_pos[1], W=LW, H=LHH),
              open(f'{QAD}/{db["num"]}_legend.json', 'w'))

    lg = Image.new('RGBA', (LW, LHH), (8, 12, 20, 218))
    ld = ImageDraw.Draw(lg)
    ld.text((S(20), S(14)), 'ЗОНЫ ОРШ (схема D v4, S_MIN = 15)', font=fl_t, fill=(240, 240, 240))
    yy = S(58)
    for name, col, txt in rows:
        ld.rectangle([S(20), yy - S(15), S(52), yy + S(15)], fill=col,
                     outline=(255, 255, 255), width=S(2))
        ld.text((S(64), yy - S(15)), f'{name}: {txt}', font=fl_r, fill=(228, 232, 238))
        yy += S(52)
    yy += S(14)
    ld.line([(S(20), yy), (LW - S(20), yy)], fill=(90, 100, 115), width=S(2))
    yy += S(18)
    ld.text((S(20), yy), 'УСЛОВНЫЕ ОБОЗНАЧЕНИЯ', font=fl_t, fill=(240, 240, 240))
    yy += S(50)

    draw_dashed(ld, [(S(20), yy), (S(52), yy)], C_BOUND, S(4), dash=S(26), gap=S(18))
    ld.text((S(64), yy - S(15)), 'граница населённого пункта (морфология застройки)',
            font=fl_r, fill=(228, 232, 238))
    yy += S(52)
    ld.line([(S(20), yy), (S(52), yy)], fill=C_TRUNK[:3], width=S(6))
    ld.text((S(64), yy - S(15)), 'ствол сети: волокна зоны ЦУ + фидеры зон', font=fl_r,
            fill=(228, 232, 238))
    yy += S(52)
    ld.line([(S(20), yy), (S(52), yy)], fill=PALETTE[0], width=S(6))
    ld.text((S(64), yy - S(15)), 'распределительная сеть зоны (цвет зоны)', font=fl_r,
            fill=(228, 232, 238))
    yy += S(52)
    draw_dashed(ld, [(S(20), yy), (S(52), yy)], PALETTE[1] + (235,), S(7),
                dash=S(30), gap=S(22))
    ld.text((S(64), yy - S(15)), 'фидер ЦУ → зонный ОРШ: кратчайший путь (ceil(1,25 × сплиттеры))',
            font=fl_r, fill=(228, 232, 238))
    yy += S(52)
    ld.line([(S(20), yy), (S(52), yy)], fill=C_DROP[:3], width=S(4))
    ld.text((S(64), yy - S(15)), 'дроп-кабель к домохозяйству', font=fl_r,
            fill=(228, 232, 238))
    yy += S(52)
    ld.rectangle([S(28), yy - S(12), S(44), yy + S(12)], fill=C_COUP[:3],
                 outline=(0, 60, 60), width=S(2))
    ld.text((S(64), yy - S(15)), 'муфта оптическая (ветвление)', font=fl_r,
            fill=(228, 232, 238))
    yy += S(52)
    ld.rectangle([S(30), yy - S(9), S(42), yy + S(9)], fill=PALETTE[2], outline=(25, 25, 25))
    ld.text((S(64), yy - S(15)), 'домохозяйство (цвет его зоны)', font=fl_r,
            fill=(228, 232, 238))
    yy += S(52)
    ld.rectangle([S(24), yy - S(15), S(48), yy + S(15)], fill=(20, 20, 25))
    ld.rectangle([S(27), yy - S(12), S(45), yy + S(12)], fill=PALETTE[3],
                 outline=(255, 255, 255), width=S(3))
    ld.text((S(64), yy - S(15)), 'зонный ОРШ — шкаф уличный (в центре сектора зоны)',
            font=fl_r, fill=(228, 232, 238))
    yy += S(52)
    ld.ellipse([S(28), yy - S(15), S(44), yy + S(15)], outline=(255, 255, 255), width=S(3))
    ld.polygon([(S(36) - S(5), yy), (S(33), yy - S(9)), (S(39), yy - S(9))], fill=(255, 40, 40))
    ld.text((S(64), yy - S(15)), 'ЦУ — ОРШ села, точка входа фидера (единый OLT)',
            font=fl_r, fill=(228, 232, 238))

    canvas.paste(lg, lg_pos, lg)
    del lg, base
    gc.collect()

    # --- масштабная линейка ---
    cand = [100, 200, 500, 1000, 2000]
    sb_m = max((m for m in cand if m / mpp_new <= S(1400)), key=lambda m: m / mpp_new)
    sb_px = sb_m / mpp_new
    if legend_right:
        x0s = S(40)
    else:
        x0s = W - int(sb_px) - S(40)
    y0s = HH + H - S(46)
    dh_.line([(x0s, y0s), (x0s + sb_px, y0s)], fill=(255, 255, 255), width=S(5))
    for xx in (x0s, x0s + sb_px / 2, x0s + sb_px):
        dh_.line([(xx, y0s - S(9)), (xx, y0s + S(9))], fill=(255, 255, 255), width=S(4))
    txt = f'{sb_m} м' if sb_m < 1000 else f'{sb_m // 1000} км'
    dh_.text((x0s + sb_px / 2 - S(34), y0s - S(44)), txt, font=fnt(S(27)),
             fill=(255, 255, 255))

    # --- стрелка севера ---
    nx, ny = W - S(70), HH + S(64)
    dh_.polygon([(nx, ny - S(34)), (nx - S(13), ny + S(16)), (nx, ny + S(6)),
                 (nx + S(13), ny + S(16))], outline=(255, 255, 255), width=S(3))
    dh_.text((nx - S(8), ny + S(18)), 'С', font=fnt(S(27)), fill=(255, 255, 255))

    # --- сохранение ---
    fname = f"{DL}/{db['num']}_{db['name']}_зоны_ОРШ_схема_D.jpg"
    canvas.save(fname, quality=90, subsampling=0)

    prev = canvas.copy()
    prev.thumbnail((1800, 1800), Image.LANCZOS)
    prev.save(f'{QAD}/{db["num"]}_preview.png')

    sz = os.path.getsize(fname) / 1e6
    print(f"{db['num']} {db['name']:<18} {canvas.width}x{canvas.height}  "
          f"зон {len(cuts)}+ЦУ  {fname.split('/')[-1]} ({sz:.1f} МБ)  "
          f"[{time.time() - t_start:.0f} с]", flush=True)
    del canvas, prev
    gc.collect()
    return fname


def main():
    keys = sys.argv[1:] if len(sys.argv) > 1 else ['all']
    if keys == ['all']:
        keys = ALL_KEYS
    for key in keys:
        assert key in ALL_KEYS, f'нет базы для {key}'
        print(f'== {key} ==', flush=True)
        render_village(key)
    print('\nГотово:', len(keys), 'карт ->', DL)


if __name__ == '__main__':
    main()
