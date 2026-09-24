#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ftth_outputs.py — финальные артефакты конвейера FTTH.

  stage_map(ctx)   — карта зон ОРШ (схема D) на базовом снимке: слои сети,
                     зонные оболочки, фидеры пунктиром, легенда (авто-размещение
                     по минимуму перекрытий), масштаб, север. JPG q90 4:4:4.
  stage_xlsx(ctx)  — спецификация материалов: Excel «Сводная (схема D)»,
                     «Параметры сетей», «Схемы A и D», «Методика».

Вызывается из ftth_pipeline.py; требует work/<key>/boq.json (стадия boq).
"""
import json
import math
import os
import subprocess
import sys
import time
import importlib.util
from collections import defaultdict
from datetime import date

# Task 50: интуитивные обозначения ЦУ/OLT и ОРШ (общий модуль с 48b)
_spec50 = importlib.util.spec_from_file_location(
    'sym50', '/home/z/my-project/scripts/50_map_symbology.py')
_sym50 = importlib.util.module_from_spec(_spec50)
_spec50.loader.exec_module(_sym50)
draw_olt_node, draw_orsh = _sym50.draw_olt_node, _sym50.draw_orsh
# Task 51: параллельные кабели на общих трассах + пучки дропов
draw_cables_bundled = _sym50.draw_cables_bundled
draw_drops_bundled = _sym50.draw_drops_bundled
edge_chains = _sym50.edge_chains

from PIL import Image, ImageDraw, ImageFont
Image.MAX_IMAGE_PIXELS = None

from ftth_pipeline import (Tree, build_road_graph, geo_for, load_json, nkey, save_json)

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

# ---------------------------------------------------------------- стиль ----
C_DROP = (255, 225, 0, 225)
C_COUP = (0, 255, 225, 255)
C_COUP_OUT = (0, 60, 60, 255)
C_TRUNK = (215, 225, 240, 235)
C_HH_OUT = (25, 25, 25, 255)
C_CU = (224, 49, 49)
PALETTE = [
    (25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
    (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
    (160, 90, 44),
]
HH_HDR = 150
DASH, GAP = 30, 22


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
    """Пунктир по ломаной: пересечение отрезков [k*seg+phase, +DASH] с сегментами."""
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
                       (0, -th - 2 * pad), (0, pad + 4)):
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


def legend_weight(rect, hh_pts, coup_pts, orsh_pts, cu_pt):
    """Вес перекрытия легенды: ДХ=1, муфта=2, зонный ОРШ=20, ЦУ=50."""
    x0, y0, x1, y1 = rect
    w = 0
    for (x, y), k in [(p, 1) for p in hh_pts] + [(p, 2) for p in coup_pts] + \
                      [(p, 20) for p in orsh_pts]:
        if x0 - 8 <= x <= x1 + 8 and y0 - 8 <= y <= y1 + 8:
            w += k
    if cu_pt and x0 - 20 <= cu_pt[0] <= x1 + 20 and y0 - 20 <= cu_pt[1] <= y1 + 20:
        w += 50
    return w


def vlm_check(image_path, prompt):
    """VLM-проверка через z-ai CLI (если доступен). Возвращает текст или None."""
    try:
        r = subprocess.run(['z-ai', 'vision', '--prompt', prompt, '--image', image_path],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def render_village_map(ctx, v):
    """Карта зон ОРШ схемы D для одного села."""
    t0 = time.time()
    key = v['key']
    db = load_json(os.path.join(ctx.vdir(key), 'boq.json'))
    geo = geo_for(key, ctx)
    mpp = geo['mpp']

    # --- разбиение на зоны (воспроизведение расчёта стадии boq) ---
    netp = os.path.join(ctx.vdir(key), db['net'])
    osm_p = os.path.join(ctx.vdir(key), 'osm.json')
    road = build_road_graph(load_json(osm_p), geo, mpp, ctx.P) if os.path.exists(osm_p) else None
    t = Tree(key, netp, mpp, ctx.P, road=road)
    cuts, _ = t.partition_greedy(ctx.P('s_min_km'))
    cutset = set(cuts)
    zr = {t.root: t.root}
    for u in t.bfs:
        if u == t.root:
            continue
        zr[u] = u if u in cutset else zr[t.parent[u]]

    # --- базовый снимок: пользовательский кадр или мозаика ---
    ct_path = os.path.join(ctx.vdir(key), 'crop_transform.json')
    use_crop = bool(v.get('crop_image')) and os.path.exists(ct_path)
    if use_crop:
        ct = load_json(ct_path)
        frame = ct['new_image']
        if not os.path.isabs(frame):
            frame = os.path.join(ctx.root, frame)
        base = Image.open(frame).convert('RGB')
        Minv = ct['M_inv']
        k = 1.0 / max(1e-9, ct['scale'])     # размер маркеров/линий x k

        def T(p):
            x, y = p
            return (Minv[0][0] * x + Minv[0][1] * y + Minv[0][2],
                    Minv[1][0] * x + Minv[1][1] * y + Minv[1][2])
    else:
        base = Image.open(os.path.join(ctx.vdir(key), 'mosaic.jpg')).convert('RGB')
        k = 1.0

        def T(p):
            return (p[0], p[1])

    W, H = base.size
    print(f'  база {W}x{H} ({"кадр пользователя" if use_crop else "мозаика"}),'
          f' зоны {len(cuts)}+ЦУ', flush=True)

    net = t.net
    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    adj_keys = set(zr.keys())

    def zone_of_drop(d):
        kk = ck.get(d['coupler'])
        if kk is None or kk not in adj_keys:
            return t.root
        return zr[kk]

    zone_dh = defaultdict(int)
    for node, dh in t.homes.items():
        zone_dh[zr[node]] += dh
    order = sorted(cuts, key=lambda c: -zone_dh[c])
    zcolor = {t.root: C_CU}
    zname = {t.root: 'ЦУ'}
    for i, c in enumerate(order):
        zcolor[c] = PALETTE[i % len(PALETTE)]
        zname[c] = f'ОРШ-{i + 1}'

    zpts = defaultdict(list)
    for d in net['drops']:
        zpts[zone_of_drop(d)].append(d['poly'][-1])
    for c in net['couplers']:
        kk = nkey([c['x'], c['y']])
        if kk in zr:
            zpts[zr[kk]].append((c['x'], c['y']))
    for z in [t.root] + list(cuts):
        zpts[z].append(z)

    # ================================================================ СЛОИ =
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    lw = max(2, round(2 * k))
    trunk_w = max(5, round(5 * k))

    for z in [t.root] + list(cuts):
        col = zcolor[z]
        hp = hull([T(p) for p in zpts[z]])
        if len(hp) >= 3:
            dr.polygon(hp, fill=col + (38,), outline=col + (170,), width=max(3, round(4 * k)))

    # Task 51: дропы пучками «одна муфта -> один дом» — параллельные линии
    # с промежутком; начало точно у муфты, заход точно в точку ДХ
    _ts = math.hypot(Minv[0][0], Minv[0][1]) if use_crop else 1.0
    drops_px = [dict(pts=[T(p) for p in d['poly']], coupler=d['coupler'],
                     color=C_DROP, width=lw)
                for d in net['drops'] if len(d['poly']) >= 2]
    draw_drops_bundled(dr, drops_px, gap=max(3.5, 4.0 * k), width=lw,
                       home_r_px=(35.0 / mpp) * _ts)

    # Task 51: магистраль + фидеры — параллельными линиями на общих трассах:
    # сплошные рёбра группируются по зонам в цепочки (стыки без клиньев),
    # фидеры зон — пунктиром своей полосой в общем пучке
    cables = []
    zone_edges = defaultdict(list)
    for (p, ch, L) in t.edges:
        zone_edges[zr[ch]].append((p, ch))
    for z in [t.root] + list(cuts):
        col = C_TRUNK if z == t.root else zcolor[z] + (235,)
        for chain in edge_chains(zone_edges.get(z, [])):
            cables.append(dict(pts=[T(p) for p in chain], color=col,
                               width=trunk_w, sort_key=-0.5))
    for i, c in enumerate(order):
        cables.append(dict(pts=[T(p) for p in t.feeder_path_nodes(c)],
                           color=zcolor[c] + (215,), width=max(5, round(6 * k)),
                           dashed=True, phase=i * (DASH + GAP) / 2.0,
                           sort_key=float(i)))
    _dump = os.path.join(ctx.vdir(key), 'render_bundles_debug.json') \
        if os.environ.get('FTTH_BUNDLE_DUMP') else None
    draw_cables_bundled(dr, cables, gap=max(4.5, round(6.0 * k)),
                        dash=DASH, gap_d=GAP, dump_path=_dump)

    for c in net['couplers']:
        x, y = T((c['x'], c['y']))
        s = 6 * k
        dr.rectangle([x - s, y - s, x + s, y + s], fill=C_COUP,
                     outline=C_COUP_OUT, width=max(1, round(2 * k)))

    for d in net['drops']:
        col = zcolor[zone_of_drop(d)]
        x, y = T(d['poly'][-1])
        s = 4 * k
        dr.rectangle([x - s, y - s, x + s, y + s], fill=col + (255,),
                     outline=C_HH_OUT, width=max(1, round(k)))

    f_z1 = fnt(max(26, round(34 * k)))
    f_z2 = fnt(max(20, round(26 * k)), bold=False)
    labels = Labels()
    # Task 50: зоны маркеров не перекрываются подписями (иконки стали выше)
    for c in order:
        mx_, my_ = T(c)
        r_ = 24 * k
        labels.boxes.append((mx_ - r_, my_ - r_, mx_ + r_, my_ + r_))
    _ax0, _ay0 = T((net['anchor']['x'], net['anchor']['y']))
    _R0 = 40 * k
    labels.boxes.append((_ax0 - _R0, _ay0 - _R0, _ax0 + _R0, _ay0 + _R0))
    for zi, c in enumerate(order):
        col = zcolor[c]
        x, y = T(c)
        draw_orsh(dr, x, y, 16 * k, col, zi + 1)     # Task 50: шкаф с номером зоны
        name = zname[c]
        dh = zone_dh[c]
        tw = max(dr.textlength(name, font=f_z1), dr.textlength(f'{dh} ДХ', font=f_z2))
        hgt = f_z1.size + f_z2.size + 2
        pos = labels.place(x, y, int(tw), hgt, W, H)
        if pos:
            bx, by = pos
            dr.rectangle([bx - 8, by - 6, bx + tw + 8, by + hgt + 6], fill=(12, 14, 20, 130))
            dr.text((bx, by), name, font=f_z1, fill=(255, 255, 255, 255),
                    stroke_width=max(2, round(4 * k)), stroke_fill=(15, 15, 15, 255))
            dr.text((bx, by + f_z1.size + 2), f'{dh} ДХ', font=f_z2,
                    fill=(255, 235, 180, 255),
                    stroke_width=max(2, round(3 * k)), stroke_fill=(15, 15, 15, 255))

    ax, ay = T((net['anchor']['x'], net['anchor']['y']))
    draw_olt_node(dr, ax, ay, 30 * k)                # Task 50: здание + антенна + бейдж OLT
    f_cu = fnt(max(26, round(34 * k)))
    t1 = 'ЦУ · OLT — центральный узел села'
    t2 = f"корневая зона: {zone_dh[t.root]} ДХ"
    pos = labels.place(ax, ay, int(dr.textlength(t1, font=f_cu)), f_cu.size + f_z2.size, W, H)
    if pos:
        bx, by = pos
        tw1 = int(dr.textlength(t1, font=f_cu))
        dr.rectangle([bx - 8, by - 6, bx + tw1 + 8, by + f_cu.size + f_z2.size + 6],
                     fill=(12, 14, 20, 130))
        dr.text((bx, by), t1, font=f_cu, fill=(255, 255, 255, 255),
                stroke_width=max(2, round(4 * k)), stroke_fill=(120, 0, 0, 255))
        dr.text((bx, by + f_cu.size + 2), t2, font=f_z2, fill=(255, 235, 180, 255),
                stroke_width=max(2, round(3 * k)), stroke_fill=(120, 0, 0, 255))

    # ======================================================== ШАПКА/ЛЕГЕНДА =
    canvas = Image.new('RGB', (W, H + HH_HDR), (10, 18, 30))
    map_rgb = base.convert('RGBA')
    map_rgb.alpha_composite(ov)
    canvas.paste(map_rgb.convert('RGB'), (0, HH_HDR))
    dh2 = ImageDraw.Draw(canvas)

    f1, f2, f3 = fnt(46), fnt(27, bold=False), fnt(27)
    dh2.text((26, 12), f"с. {db['name']} — схема D: зонные ОРШ (сплиттеры 1:64)"
             f" при едином узле OLT", font=f1, fill=(240, 245, 250))
    dh2.text((26, 68), f"{db['raion']} · спутник Google z{geo.get('zoom', 18)}"
              f" ({mpp:.2f} м/px) · топология сети, муфты и дропы — как в схеме A",
             font=f2, fill=(170, 185, 200))
    st = (f"ДХ: {db['dhx_served']}   ·   зонных ОРШ: {db['n_zones']} + ЦУ   ·   "
          f"волокно-км: {db['fiber_km']:.1f}   ·   магистраль: {db['cable_km_raw']:.1f} км   ·   "
          f"дроп-кабель: {db['drop_cable_km']:.1f} км   ·   сплиттеры 1×64: {db['splitters64']}")
    dh2.text((26, 106), st, font=f3, fill=(255, 220, 120))

    # --- легенда зон ---
    rows = [('ЦУ', C_CU, f"корневая зона: {zone_dh[t.root]} ДХ · "
                         f"{db['zones'][0]['splitters']}×1:64 · кросс {db['zones'][0]['orsh_ports']} портов")]
    for c in order:
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
    ld.text((20, 14), f"ЗОНЫ ОРШ (схема D, S_MIN = {ctx.P('s_min_km'):g})", font=fl_t,
            fill=(240, 240, 240))
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
    ld.line([(20, yy), (52, yy)], fill=C_TRUNK[:3], width=6)
    ld.text((64, yy - 15), 'ствол сети: волокна зоны ЦУ + фидеры зон', font=fl_r, fill=(228, 232, 238))
    yy += 52
    ld.line([(20, yy), (52, yy)], fill=PALETTE[0], width=6)
    ld.text((64, yy - 15), 'распределительная сеть зоны (цвет зоны)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    draw_dashed(ld, [(20, yy), (52, yy)], PALETTE[1] + (235,), 7)
    ld.text((64, yy - 15), 'фидер ЦУ → зонный ОРШ (ceil(1,25 × сплиттеры зоны))',
            font=fl_r, fill=(228, 232, 238))
    yy += 52
    ld.line([(20, yy), (52, yy)], fill=C_DROP[:3], width=4)
    ld.text((64, yy - 15), 'дроп-кабель к домохозяйству', font=fl_r, fill=(228, 232, 238))
    yy += 52
    ld.rectangle([28, yy - 12, 44, yy + 12], fill=C_COUP[:3], outline=(0, 60, 60), width=2)
    ld.text((64, yy - 15), 'муфта оптическая (ветвление)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    ld.rectangle([30, yy - 9, 42, yy + 9], fill=PALETTE[2], outline=(25, 25, 25))
    ld.text((64, yy - 15), 'домохозяйство (цвет его зоны)', font=fl_r, fill=(228, 232, 238))
    yy += 52
    draw_orsh(ld, 36, yy, 14, PALETTE[3], 1)
    ld.text((64, yy - 15), 'зонный ОРШ-N — уличный шкаф (номер зоны на шкафе)',
            font=fl_r, fill=(228, 232, 238))
    yy += 52
    draw_olt_node(ld, 36, yy, 14)
    ld.text((64, yy - 15), 'ЦУ · OLT — центральный узел: станция OLT, вход магистрали',
            font=fl_r, fill=(228, 232, 238))

    # --- авто-размещение легенды: 5 позиций по минимуму взвешенного перекрытия ---
    hh_pts = [T(d['poly'][-1]) for d in net['drops']]
    coup_pts = [T((c['x'], c['y'])) for c in net['couplers']]
    orsh_pts = [T(c) for c in order]
    positions = {
        'BL': (16, HH_HDR + H - LHH - 16),
        'BR': (W - LW - 16, HH_HDR + H - LHH - 16),
        'ML': (16, HH_HDR + (H - LHH) // 2),
        'MR': (W - LW - 16, HH_HDR + (H - LHH) // 2),
        'TL': (16, HH_HDR + 16),
    }
    best_pos, best_w, best_name = None, None, None
    for pname, (px, py) in positions.items():
        if px < 0 or py < HH_HDR:
            continue
        w = legend_weight((px, py, px + LW, py + LHH), hh_pts, coup_pts, orsh_pts, (ax, ay))
        if best_w is None or w < best_w:
            best_pos, best_w, best_name = (px, py), w, pname
    canvas.paste(lg, best_pos, lg)

    # --- масштабная линейка ---
    cand = [100, 200, 500, 1000, 2000]
    sb_m = max((m2 for m2 in cand if m2 / mpp <= 1400), key=lambda m2: m2 / mpp)
    sb_px = sb_m / mpp
    x0 = W - int(sb_px) - 60
    y0 = HH_HDR + H - 46
    txt = f'{sb_m} м' if sb_m < 1000 else f'{sb_m // 1000} км'
    dh2.line([(x0, y0), (x0 + sb_px, y0)], fill=(255, 255, 255), width=5)
    for xx in (x0, x0 + sb_px / 2, x0 + sb_px):
        dh2.line([(xx, y0 - 9), (xx, y0 + 9)], fill=(255, 255, 255), width=4)
    dh2.text((x0 + sb_px / 2 - 34, y0 - 44), txt, font=fnt(27), fill=(255, 255, 255))

    nx, ny = W - 70, HH_HDR + 64
    dh2.polygon([(nx, ny - 34), (nx - 13, ny + 16), (nx, ny + 6), (nx + 13, ny + 16)],
                outline=(255, 255, 255), width=3)
    dh2.text((nx - 8, ny + 18), 'С', font=fnt(27), fill=(255, 255, 255))

    # --- сохранение ---
    fname = os.path.join(ctx.dl, f"{db['num']}_{db['name']}_зоны_ОРШ.jpg")
    canvas.save(fname, quality=90, subsampling=0)
    qa_dir = os.path.join(ctx.work, 'qa', 'zone_maps')
    os.makedirs(qa_dir, exist_ok=True)
    prev = canvas.copy()
    prev.thumbnail((1800, 1800), Image.LANCZOS)
    prev_path = os.path.join(qa_dir, f"{db['num']}_preview.png")
    prev.save(prev_path)
    sz = os.path.getsize(fname) / 1e6
    print(f"{db['num']} {db['name']:<18} {canvas.width}x{canvas.height}  "
          f"легенда {best_name}  "
          f"{os.path.basename(fname)} ({sz:.1f} МБ)  [{time.time() - t0:.0f} с]", flush=True)
    del base, ov, map_rgb, canvas, prev
    return fname, prev_path


def stage_map(ctx, vlm=False):
    for v in ctx.villages:
        fname, prev_path = render_village_map(ctx, v)
        if vlm:
            answer = vlm_check(prev_path,
                               'Проверь карту FTTH: 1) линии сети идут вдоль улиц? '
                               '2) маркеры домохозяйств на дворах? 3) подписи и легенда читаемы? '
                               '4) есть ли перекрытия легенды с сетью/ОРШ? Ответь кратко по пунктам.')
            if answer:
                print(f'  VLM: {answer[:600]}')
            else:
                print('  VLM: недоступен (z-ai vision) — пропущено')


# ============================================================================
# xlsx — спецификация материалов
# ============================================================================
# Встроенные дизайн-токены (порт templates/base.py навыка xlsx, палитра professional)
_X = dict(
    FONT_NAME='Calibri', HEADER_BOLD=True,
    PRIMARY='1B2A4A', PRIMARY_LIGHT='D6E4F0', SECONDARY='D6E4F0',
    NEUTRAL_900='37352F', NEUTRAL_600='8C8A84', NEUTRAL_200='E9E9E8',
    NEUTRAL_100='F7F7F5', NEUTRAL_0='FFFFFF', HEADER_TEXT='FFFFFF',
)


def _f_title():
    from openpyxl.styles import Font
    return Font(name=_X['FONT_NAME'], size=16, bold=_X['HEADER_BOLD'], color=_X['PRIMARY'])


def _f_header():
    from openpyxl.styles import Font
    return Font(name=_X['FONT_NAME'], size=11, bold=_X['HEADER_BOLD'], color=_X['HEADER_TEXT'])


def _f_subheader():
    from openpyxl.styles import Font
    return Font(name=_X['FONT_NAME'], size=11, bold=_X['HEADER_BOLD'], color=_X['PRIMARY'])


def _f_body():
    from openpyxl.styles import Font
    return Font(name=_X['FONT_NAME'], size=11, color=_X['NEUTRAL_900'])


def _f_caption():
    from openpyxl.styles import Font
    return Font(name=_X['FONT_NAME'], size=9, color=_X['NEUTRAL_600'])


def _fill(color):
    from openpyxl.styles import PatternFill
    return PatternFill('solid', fgColor=color)


def _style_header_row(ws, row_num, col_start, col_end):
    from openpyxl.styles import Alignment, Border, Side
    for col in range(col_start, col_end + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = _fill(_X['PRIMARY'])
        cell.font = _f_header()
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(bottom=Side(style='thin', color=_X['NEUTRAL_200']))
    ws.row_dimensions[row_num].height = 28


def _style_total_row(ws, row_num, col_start, col_end):
    from openpyxl.styles import Border, Side
    for col in range(col_start, col_end + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = _fill(_X['SECONDARY'])
        cell.font = _f_subheader()
        cell.border = Border(top=Side(style='medium', color=_X['NEUTRAL_200']))
    ws.row_dimensions[row_num].height = 26


def _setup_sheet(ws, title, last_col):
    from openpyxl.styles import Alignment
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 3
    ws.row_dimensions[1].height = 15
    ws.row_dimensions[2].height = 32
    ws.row_dimensions[3].height = 8
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_col)
    cell = ws.cell(row=2, column=2, value=title)
    cell.font = _f_title()
    cell.alignment = Alignment(horizontal='left', vertical='center')


def stage_xlsx(ctx):
    """Книга Excel: Сводная (D) / Параметры сетей / Схемы A и D / Методика."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    D = load_json(os.path.join(ctx.work, 'boq_total.json'))
    V = D['villages']
    VN = [v['name'] for v in V]
    T = D['totals']
    M = D['model']
    DATE = date.today().strftime('%d.%m.%Y')
    F_INT, F_KM, F_PCT = '#,##0', '#,##0.0', '+0.0%;-0.0%;0.0%'

    wb = Workbook()

    # =========================================================== Сводная ====
    ws = wb.active
    ws.title = 'Сводная (схема D)'
    HDRS = ['№', 'Наименование', 'Ед. изм.', 'Расчёт / норма'] + VN + ['ИТОГО']
    LAST = 1 + len(HDRS)
    _setup_sheet(ws, f'Сводная таблица материалов — FTTH (GPON), схема D: зонные ОРШ,'
                     f' единый узел OLT — {len(V)} СНП', LAST)
    ws['B3'] = ('Сеть спроектирована по спутниковым снимкам с привязкой к дорогам OSM • '
                'допущения — лист «Методика» • подготовлено ' + DATE)
    ws['B3'].font = _f_caption()
    ws.row_dimensions[3].height = 14
    for i, h in enumerate(HDRS, start=2):
        ws.cell(row=4, column=i, value=h)
    _style_header_row(ws, 4, 2, LAST)
    widths = {'A': 3, 'B': 5, 'C': 44, 'D': 9, 'E': 26}
    for ci in range(6, LAST + 1):
        widths[get_column_letter(ci)] = 12.5
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    SECTIONS = [
        ('А. Оборудование и узлы', [
            ('Шкаф ОРШ на здании ЦУ (основа сети, единый узел OLT)', 'шт',
             '1 на СНП (здание-якорь по проекту)', 'orsh_cu', 'int'),
            ('Шкаф ОРШ зонный уличный (в муфте ветвления)', 'шт',
             f'по разбиению на зоны (S_MIN = {M["s_min_km"]:g} волокно-км)', 'orsh_zone', 'int'),
            ('Сплиттер PLC 1×64 (в ЦУ и зонных ОРШ)', 'шт',
             'Σ ceil(ДХ зоны / 64)', 'splitters', 'int'),
            ('Пигтейль SC/UPC для кроссов ОРШ', 'шт', 'ДХ + 2 × сплиттеры', 'pigtails', 'int'),
            ('Порт PON OLT — справочно (активное оборудование)', 'шт',
             'по числу сплиттеров 1:64', 'olt_ports', 'int'),
        ]),
        ('Б. Кабельная продукция (длины с запасом на монтаж 10 %)', [
            (f'Кабель оптический самонесущий, {s} волокон', 'км',
             'волокна участка = 1,25 × ДХ потока', f'cable_{s}', 'km')
            for s in M['std_fibers']
        ] + [
            ('Кабель дроп-кабельный самонесущий, 2 волокна (1 раб. + 1 рез.)', 'км',
             'Σ длин дропов × 1,05', 'drop_cable_km', 'km'),
            ('Справочно: суммарная ёмкость магистрального кабеля', 'волокно-км',
             'Σ (длина участка × волокна)', 'fiber_km', 'km'),
        ]),
        ('В. Пассивные узлы', [
            ('Муфта оптическая (проходная / тупиковая)', 'шт',
             'ветвления и подключения (кроме узлов, ставших зонными ОРШ)', 'mufty', 'int'),
        ]),
        ('Г. Материалы для монтажа', [
            ('Бокс абонентский оптический с адаптером SC/UPC', 'шт', '1 на ДХ',
             'abonent_boxes', 'int'),
            ('Коннектор оптический механический SC/UPC', 'шт', 'ДХ × 1,1', 'fast_conn', 'int'),
            ('Сварное соединение (оценка объёма работ)', 'шт',
             '(2 × ДХ + 2 × сплиттеры) × 1,1', 'splices', 'int'),
            ('Гильза КДЗС, 60 мм', 'шт', 'по числу сварных соединений', 'kdzs', 'int'),
            ('Комплект подвеса магистрали (кронштейн + спиральный зажим)', 'компл',
             '30 на 1 км кабеля', 'suspend_kits', 'int'),
            ('Анкерный зажим дроп-кабеля', 'шт', '2 на ДХ', 'drop_anchors', 'int'),
            ('Крепёж дроп-кабеля (скобы / хомуты)', 'шт', '6 на ДХ', 'drop_fix', 'int'),
        ]),
    ]

    row, num = 5, 0
    for sect_title, items in SECTIONS:
        ws.cell(row=row, column=3, value=sect_title)
        for c in range(2, LAST + 1):
            cell = ws.cell(row=row, column=c)
            cell.fill = _fill(_X['SECONDARY'])
            cell.font = _f_subheader()
            cell.alignment = Alignment(horizontal='left', vertical='center')
        ws.row_dimensions[row].height = 24
        row += 1
        for idx, (name, unit, norma, mkey, kind) in enumerate(items):
            num += 1
            ws.cell(row=row, column=2, value=num)
            ws.cell(row=row, column=3, value=name)
            ws.cell(row=row, column=4, value=unit)
            ws.cell(row=row, column=5, value=norma)
            for vi, vv in enumerate(V):
                m = dict(vv['materials'])
                m['fiber_km'] = vv['fiber_km']
                val = m.get(mkey)
                if val in (0, 0.0, None):
                    val = None
                ws.cell(row=row, column=6 + vi, value=val)
            col_from = get_column_letter(6)
            col_to = get_column_letter(5 + len(V))
            ws.cell(row=row, column=LAST, value=f'=SUM({col_from}{row}:{col_to}{row})')
            fill = _fill(_X['NEUTRAL_0'] if idx % 2 == 0 else _X['NEUTRAL_100'])
            for c in range(2, LAST + 1):
                cell = ws.cell(row=row, column=c)
                cell.fill = fill
                cell.font = _f_body()
                if c == 2:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                elif c in (3, 5):
                    cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
                elif c == 4:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='right', vertical='center')
                    cell.number_format = F_KM if kind == 'km' else F_INT
            ws.cell(row=row, column=LAST).font = _f_subheader()
            ws.row_dimensions[row].height = 24
            row += 1

    row += 1
    for t in ('Значения в графах сел — потребность по проекту; графа «ИТОГО» — сумма по всем СНП. '
              'Единицы измерения разнородны, итог по столбцам не приводится.',
              'Позиция А.5 (порты PON OLT) — справочно, активное оборудование. '
              'Нормы и допущения — лист «Методика»; параметры сетей — лист «Параметры сетей».',
              'Фидер ЦУ → зонный ОРШ идёт по дереву сети совместно с распределительными '
              'волокнами; межселённый транспорт до ЦУ — за рамками расчёта.'):
        ws.cell(row=row, column=2, value=t).font = _f_caption()
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=LAST)
        ws.row_dimensions[row].height = 14
        row += 1
    ws.freeze_panes = f'{get_column_letter(6)}5'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '4:4'

    # ====================================================== Параметры сетей ==
    ws2 = wb.create_sheet('Параметры сетей')
    H2 = ['№', 'СНП', 'Район / с.о.', 'ДХ (заказ)', 'ДХ (проект)', 'Δ к заказу',
          'Зонных ОРШ', 'Муфты', 'Магистраль, км', 'Дропы, км', 'Ср. дроп, м', 'Макс. дроп, м',
          'Волокно-км (D)', 'Волокно-км (A)', 'Сплиттеры 1:64', 'Верх. участок, волокон',
          'Ср. маршрут волокна, м']
    L2 = 1 + len(H2)
    _setup_sheet(ws2, 'Параметры спроектированных FTTH-сетей по СНП (схема D)', L2)
    ws2['B3'] = ('ДХ — домохозяйства. «Верхний участок» — максимум волокон на участке; '
                 '«маршрут волокна» — от обслуживающего ОРШ зоны до муфты ДХ. Подготовлено ' + DATE)
    ws2['B3'].font = _f_caption()
    ws2.row_dimensions[3].height = 14
    for i, h in enumerate(H2, start=2):
        ws2.cell(row=4, column=i, value=h)
    _style_header_row(ws2, 4, 2, L2)
    for col, w in {'A': 3, 'B': 5, 'C': 17, 'D': 22, 'E': 10, 'F': 10, 'G': 9, 'H': 8,
                   'I': 11, 'J': 9.5, 'K': 9.5, 'L': 10, 'M': 10, 'N': 10, 'O': 10,
                   'P': 10, 'Q': 11}.items():
        ws2.column_dimensions[col].width = w

    r = 5
    for i, v in enumerate(V):
        so = f"{v['raion']} / {v['so']}" if v.get('so') and v['so'] != '—' else v['raion']
        vals = [v['num'], v['name'], so, v['dhx_excel'], v['dhx_served'],
                f'=IFERROR(F{r}/E{r}-1,"")', v['n_zones'], v['mufty'], v['feeder_km'],
                v['drop_km'], v['avg_drop_m'], v['max_drop_m'], v['fiber_km'],
                v['scheme_a']['fiber_km'], v['splitters64'], v['top_fibers'],
                v['routes']['avg_m']]
        for ci, val in enumerate(vals, start=2):
            ws2.cell(row=r, column=ci, value=val)
        fill = _fill(_X['NEUTRAL_0'] if i % 2 == 0 else _X['NEUTRAL_100'])
        for ci in range(2, L2 + 1):
            cell = ws2.cell(row=r, column=ci)
            cell.fill = fill
            cell.font = _f_body()
            if ci in (2, 4, 8):
                cell.alignment = Alignment(horizontal='center', vertical='center')
            elif ci == 3:
                cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal='right', vertical='center')
        for ci, fmt in [(6, F_INT), (7, F_INT), (8, F_PCT), (9, F_INT), (10, F_INT),
                        (11, '#,##0.00'), (12, '#,##0.00'), (13, F_INT), (14, F_INT),
                        (15, F_INT), (16, F_INT), (17, F_INT), (18, F_INT)]:
            ws2.cell(row=r, column=ci).number_format = fmt
        ws2.row_dimensions[r].height = 26
        r += 1
    tr = r
    ws2.cell(row=tr, column=3, value='ИТОГО')
    for ci, f in [(5, f'=SUM(E5:E{tr-1})'), (6, f'=SUM(F5:F{tr-1})'),
                  (7, f'=IFERROR(F{tr}/E{tr}-1,"")'), (8, f'=SUM(H5:H{tr-1})'),
                  (9, f'=SUM(I5:I{tr-1})'), (10, f'=SUM(J5:J{tr-1})'),
                  (11, f'=SUM(K5:K{tr-1})'), (12, f'=IFERROR(K{tr}*1000/F{tr},"")'),
                  (13, f'=MAX(M5:M{tr-1})'), (14, f'=SUM(N5:N{tr-1})'),
                  (15, f'=SUM(O5:O{tr-1})'), (16, f'=SUM(P5:P{tr-1})'),
                  (17, f'=MAX(Q5:Q{tr-1})'),
                  (18, f'=IFERROR(SUMPRODUCT(R5:R{tr-1},F5:F{tr-1})/F{tr},"")')]:
        ws2.cell(row=tr, column=ci, value=f)
    _style_total_row(ws2, tr, 2, L2)
    for ci, fmt in [(5, F_INT), (6, F_INT), (7, F_PCT), (8, F_INT), (9, F_INT),
                    (10, '#,##0.00'), (11, '#,##0.00'), (12, F_INT), (13, F_INT),
                    (14, F_KM), (15, F_KM), (16, F_INT), (17, F_INT), (18, F_INT)]:
        c = ws2.cell(row=tr, column=ci)
        c.number_format = fmt
        c.alignment = Alignment(horizontal='right', vertical='center')
    ws2.freeze_panes = 'F5'
    ws2.page_setup.orientation = 'landscape'
    ws2.page_setup.fitToWidth = 1
    ws2.page_setup.fitToHeight = 0

    # ======================================================= Схемы A и D ====
    ws3 = wb.create_sheet('Схемы A и D')
    H3 = ['Показатель', 'A — централизованная 1:64', 'D — зонные ОРШ 1:64', 'Δ D к A']
    L3 = 1 + len(H3)
    _setup_sheet(ws3, 'Сравнение схем: централизованная (A) и децентрализованная (D)', L3)
    ws3['B3'] = ('Топология сетей, муфты и дропы в обеих схемах одинаковы — различается '
                 'размещение сплиттеров и формирование ёмкостей. Подготовлено ' + DATE)
    ws3['B3'].font = _f_caption()
    ws3.row_dimensions[3].height = 14
    for i, h in enumerate(H3, start=2):
        ws3.cell(row=4, column=i, value=h)
    _style_header_row(ws3, 4, 2, L3)
    for col, w in {'A': 3, 'B': 46, 'C': 22, 'D': 22, 'E': 14}.items():
        ws3.column_dimensions[col].width = w

    sum_a_cable = round(sum(v['scheme_a']['cable_km_raw'] for v in V), 1)
    sum_a_drop = round(sum(v['scheme_a']['drop_cable_km'] for v in V), 1)
    ROWS3 = [
        ('Обслуживаемые ДХ', T['dhx_served'], T['dhx_served'], 'int'),
        ('ОРШ (шкафы), шт', len(V), T['orsh'], 'int'),
        ('Волокно-км магистрали', T['fiber_km_a'], T['fiber_km'], 'km1'),
        ('Магистральный кабель (с запасом 10 %), км', sum_a_cable, T['cable_km_raw'], 'km1'),
        ('Дроп-кабель (с запасом 5 %), км', sum_a_drop, T['drop_cable_km'], 'km1'),
        ('ВСЕГО кабельной продукции, км', T['total_length_km_a'], T['total_length_km'], 'km1'),
        ('Муфты, шт', sum(v['scheme_a']['mufty'] for v in V), T['mufty'], 'int'),
        ('Сплиттеры 1:64, шт', sum(v['scheme_a']['splitters64'] for v in V),
         T['splitters64'], 'int'),
        ('Сварные соединения, шт', sum(v['scheme_a']['splices'] for v in V), T['splices'], 'int'),
        ('Кросс ОРШ, портов', sum(v['scheme_a']['orsh_ports'] for v in V),
         T['orsh_ports'], 'int'),
    ]
    r = 5
    for i, (name, va, vd, kind) in enumerate(ROWS3):
        ws3.cell(row=r, column=2, value=name)
        ws3.cell(row=r, column=3, value=va)
        ws3.cell(row=r, column=4, value=vd)
        ws3.cell(row=r, column=5, value=f'=IFERROR(D{r}/C{r}-1,"")')
        fill = _fill(_X['NEUTRAL_0'] if i % 2 == 0 else _X['NEUTRAL_100'])
        for ci in range(2, L3 + 1):
            cell = ws3.cell(row=r, column=ci)
            cell.fill = fill
            cell.font = _f_body()
            if ci == 2:
                cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal='right', vertical='center')
                cell.number_format = ('#,##0.0' if kind == 'km1' else
                                      F_PCT if ci == 5 else F_INT)
        ws3.row_dimensions[r].height = 24
        r += 1
    ws3.cell(row=r + 1, column=2,
             value='Схема D минимизирует суммарную длину кабельной продукции и волокно-км; '
                   'схема A проще в эксплуатации (все сплиттеры в ЦУ, OTDR-тест из одной точки), '
                   'но требует больших ёмкостей магистрали у ЦУ.').font = _f_caption()
    ws3.merge_cells(start_row=r + 1, start_column=2, end_row=r + 1, end_column=L3)

    # =========================================================== Методика ====
    ws4 = wb.create_sheet('Методика')
    H4 = ['№', 'Положение', 'Принято / описание']
    L4 = 1 + len(H4)
    _setup_sheet(ws4, 'Методика расчёта и принятые допущения', L4)
    ws4['B3'] = ('Расчёт выполнен по геометрии спроектированных сетей (ЦУ → зонные ОРШ → '
                 'муфты → ДХ). Подготовлено ' + DATE)
    ws4['B3'].font = _f_caption()
    ws4.row_dimensions[3].height = 14
    for i, h in enumerate(H4, start=2):
        ws4.cell(row=4, column=i, value=h)
    _style_header_row(ws4, 4, 2, L4)
    for col, w in {'A': 3, 'B': 5, 'C': 34, 'D': 88}.items():
        ws4.column_dimensions[col].width = w

    ROWS4 = [
        ('S', '1. Исходные данные', None),
        ('Геометрия сетей', 'Проектные FTTH-сети построены по спутниковым снимкам высокого '
         'разрешения (Google z18, ~0,38 м/px) с привязкой к дорожной сети OSM; дропы '
         'проложены вдоль улиц, дворов и фасадов, все ветвления — в муфтах.'),
        ('Число ДХ по данным заказа', f'{T["dhx_excel"]} по всем СНП (см. config проекта).'),
        ('Обслужено проектом', f'{T["dhx_served"]} ДХ. Отклонения от данных заказа связаны '
         'с покрытием дорог OSM и фактической застройкой; при больших расхождениях '
         'проверьте домохозяйства по превью стадии households.'),
        ('Длины', 'Длины участков и дропов — по геометрии проекта с пересчётом пикселей '
         'в метры по масштабу мозаики.'),
        ('S', '2. Архитектура (схема D)', None),
        ('Схема сети', 'GPON, децентрализованная: дерево села режется на зоны, в корне зоны '
         '(существующая муфта ветвления) ставится зонный ОРШ со сплиттерами 1:64 своей '
         'зоны; единый узел OLT; фидер от ЦУ к зонным ОРШ идёт по кратчайшему пути '
         'дорожного графа (Дейкстра) — путь внутри дерева распределения может быть '
         'существенно длиннее.'),
        ('Разбиение на зоны', f'Жадный выбор врезов по максимальной маржинальной экономии '
         f'волокно-км; зона >= {M["min_zone"]} ДХ (заполнение сплиттера 1:64 >= 75 %); '
         f'экономия вреза >= S_MIN = {M["s_min_km"]:g} волокно-км (порог окупаемости шкафа).'),
        ('Дроп-линия', 'Дроп-кабель 2-волоконный (1 рабочее + 1 резервное), самонесущий, '
         'от обслуживающей муфты вдоль улицы/двора к зданию.'),
        ('S', '3. Кабельная продукция', None),
        ('Магистральный кабель', f'Самонесущий, стандартные ёмкости '
         f'{" / ".join(str(s) for s in M["std_fibers"])} волокон; при потребности свыше '
         f'{M["std_fibers"][-1]} — параллельная прокладка кабелей меньшей ёмкости.'),
        ('Число волокон на участке', f'ДХ ниже по потоку × {M["fiber_reserve"]:g} (резерв '
         f'{int((M["fiber_reserve"]-1)*100)} %), минимум {M["min_fibers"]} волокон; '
         'фидер зоны добавляется к распределительным волокнам на общих с деревом '
         'участках; на участках вне дерева — отдельный кабель не менее '
         f'{M["min_fibers"]} волокон.'),
        ('Запас на монтаж', f'+{int((M["cable_stock"]-1)*100)} % к магистрали и '
         f'+{int((M["drop_stock"]-1)*100)} % к дроп-кабелю; округление вверх до 0,1 км.'),
        ('Справочно', f'Суммарная ёмкость магистрали — {T["fiber_km"]} волокно-км '
         f'(централизованная схема: {T["fiber_km_a"]}).'),
        ('S', '4. Узлы и монтажные нормы', None),
        ('Муфты', 'Все точки ветвления магистрали и подключения групп дропов, кроме узлов, '
         'получивших зонный ОРШ. Тип муфты и ёмкость — по рабочему проекту.'),
        ('ОРШ', 'ЦУ — на здании-якоре в центре села; зонные — уличные шкафы в муфтах '
         'ветвления. Ёмкость портов — ДХ × 1,1 с округлением вверх до ряда '
         f'{" / ".join(str(p) for p in M["orsh_ports_row_zone"])} (зонные) и '
         f'{" / ".join(str(p) for p in M["orsh_ports_row"])} (ЦУ).'),
        ('Сварные соединения', f'(2 × ДХ + 2 × сплиттеры) × {M["consum_stock"]:g}; '
         'гильзы КДЗС — по числу сварок.'),
        ('Подвес магистрали', f'{M["suspend_per_km"]} комплектов на 1 км кабеля; новые опоры '
         'не предусмотрены — предполагается использование существующих опорных конструкций.'),
        ('Крепёж дропа', f'{M["drop_anchors_per_dh"]} анкерных зажима и {M["drop_fix_per_dh"]} '
         'промежуточных креплений на одно ДХ.'),
        ('S', '5. Прочее', None),
        ('Активное оборудование', 'Порты PON OLT приведены справочно; модель и комплектацию '
         'уточняет заказчик.'),
        ('За рамками расчёта', 'Межселённый транспорт до ЦУ, строительство/аренда опор, '
         'заземление, оборудование абонентов (ONT), СМР, накладные расходы.'),
    ]
    r = 5
    n4 = 0
    for item in ROWS4:
        if item[0] == 'S':
            ws4.cell(row=r, column=3, value=item[1])
            for c in range(2, L4 + 1):
                cell = ws4.cell(row=r, column=c)
                cell.fill = _fill(_X['SECONDARY'])
                cell.font = _f_subheader()
                cell.alignment = Alignment(horizontal='left', vertical='center')
            ws4.row_dimensions[r].height = 24
        else:
            n4 += 1
            name, desc = item
            ws4.cell(row=r, column=2, value=n4)
            ws4.cell(row=r, column=3, value=name)
            ws4.cell(row=r, column=4, value=desc)
            fill = _fill(_X['NEUTRAL_0'] if n4 % 2 == 0 else _X['NEUTRAL_100'])
            for c in range(2, L4 + 1):
                cell = ws4.cell(row=r, column=c)
                cell.fill = fill
                cell.font = _f_body()
                if c == 2:
                    cell.alignment = Alignment(horizontal='center', vertical='top')
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            lines = max(math.ceil(len(desc) / 105), math.ceil(len(name) / 30), 1)
            ws4.row_dimensions[r].height = max(22, lines * 14 + 8)
        r += 1
    ws4.page_setup.orientation = 'landscape'
    ws4.page_setup.fitToWidth = 1
    ws4.page_setup.fitToHeight = 0

    wb.properties.creator = 'Z.ai'
    project = ctx.cfg.get('project', 'project')
    out = os.path.join(ctx.dl, f'BoQ_FTTH_{project}.xlsx')
    wb.save(out)
    print('Сохранено:', out)
    print('Листы:', wb.sheetnames)
    return out
