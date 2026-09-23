#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рендер итоговых схем FTTH на полноразмерных космоснимках.
Выход: download/snp_vko/<NN>_<Имя>_FTTH.png (полное разрешение)"""
import cv2, json, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WORK = '/home/z/my-project/work'
OUT_DIR = '/home/z/my-project/download/snp_vko'
os.makedirs(OUT_DIR, exist_ok=True)

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

FONT_B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

COL_TREE = (0, 229, 255)      # cyan BGR
COL_DROP = (0, 215, 255)      # yellow BGR
COL_MUFT_B = (0, 128, 255)    # orange
COL_MUFT_T = (0, 90, 255)
COL_ORSH = (60, 60, 255)      # red
COL_HH = (40, 40, 230)

def render(name):
    snp = next(s for s in SNPS if s['name'] == name)
    idx = [i + 1 for i, s in enumerate(SNPS) if s['name'] == name][0]
    geo = json.load(open(f'{WORK}/geo/{name}.json'))
    net = json.load(open(f'{WORK}/net/{name}.json'))
    hh = json.load(open(f'{WORK}/hh/{name}.json'))
    lat0, lon0 = snp['lat'], snp['lon']
    mx = 111320 * math.cos(math.radians(lat0)); my = 111132.0
    n = 2 ** geo['zoom']
    gx0 = geo['tx0'] * 256 + geo['px_x0']; gy0 = geo['ty0'] * 256 + geo['px_y0']

    def m_to_px(x_m, y_m):
        lat = lat0 + y_m / my
        lon = lon0 + x_m / mx
        xt = (lon + 180.0) / 360.0 * n * 256.0
        lr = math.radians(lat)
        yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256.0
        return xt - gx0, yt - gy0

    img = cv2.imread(f'{WORK}/full/{idx:02d}_{name}.png')
    H, W = img.shape[:2]

    # кроп: bbox всех элементов + 300 м
    xs, ys = [], []
    for e in net['tree_edges']:
        for p in e['pts']:
            xs.append(p[0]); ys.append(p[1])
    for m in net['muftas']:
        xs.append(m['x']); ys.append(m['y'])
        for d in m['drops']:
            xs.append(d['x']); ys.append(d['y'])
    buf = 300.0
    x0m, x1m = min(xs) - buf, max(xs) + buf
    y0m, y1m = min(ys) - buf, max(ys) + buf
    px0, py0 = m_to_px(x0m, y1m)   # верхний левый (y инвертирован)
    px1, py1 = m_to_px(x1m, y0m)
    cx0, cy0 = max(0, int(px0)), max(0, int(py0))
    cx1, cy1 = min(W, int(px1)), min(H, int(py1))
    canvas = img[cy0:cy1, cx0:cx1].copy()
    Hc, Wc = canvas.shape[:2]
    print(f"{name}: кроп {Wc}x{Hc} из {W}x{H}")

    def to_canvas(x_m, y_m):
        px, py = m_to_px(x_m, y_m)
        return int(px - cx0), int(py - cy0)

    # --- дропы (тонкие жёлтые) ---
    for m in net['muftas']:
        mxp, myp = to_canvas(m['x'], m['y'])
        for d in m['drops']:
            hx, hy = to_canvas(d['x'], d['y'])
            cv2.line(canvas, (mxp, myp), (hx, hy), COL_DROP, 1, cv2.LINE_AA)

    # --- дерево (по волоконности) ---
    for e in net['tree_edges']:
        f = e['fibers']
        wdt = 5 if f >= 64 else (4 if f >= 24 else 3)
        pts = [to_canvas(p[0], p[1]) for p in e['pts']]
        for i in range(len(pts) - 1):
            cv2.line(canvas, pts[i], pts[i + 1], COL_TREE, wdt, cv2.LINE_AA)

    # --- домохозяйства ---
    for m in net['muftas']:
        for d in m['drops']:
            hx, hy = to_canvas(d['x'], d['y'])
            cv2.circle(canvas, (hx, hy), 3, COL_HH, -1, cv2.LINE_AA)

    # --- муфты ---
    for m in net['muftas']:
        mxp, myp = to_canvas(m['x'], m['y'])
        if m['kind'] == 'branch':
            cv2.rectangle(canvas, (mxp - 7, myp - 7), (mxp + 7, myp + 7), COL_MUFT_B, -1)
            cv2.rectangle(canvas, (mxp - 7, myp - 7), (mxp + 7, myp + 7), (255, 255, 255), 2)
        else:
            cv2.circle(canvas, (mxp, myp), 6, COL_MUFT_T, -1)
            cv2.circle(canvas, (mxp, myp), 6, (255, 255, 255), 2)

    # --- ОРШ ---
    ox, oy = to_canvas(net['orsh']['x'], net['orsh']['y'])
    R = 26
    pts = np.array([[ox, oy - R], [ox + R, oy], [ox, oy + R], [ox - R, oy]], np.int32)
    cv2.fillPoly(canvas, [pts], COL_ORSH)
    cv2.polylines(canvas, [pts], True, (255, 255, 255), 3)

    # --- текстовый слой (PIL, кириллица) ---
    pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    dr = ImageDraw.Draw(pil, 'RGBA')
    S = max(0.55, min(1.0, Wc / 7000.0))  # масштаб текста
    f_title = ImageFont.truetype(FONT_B, int(52 * S))
    f_sub = ImageFont.truetype(FONT_R, int(34 * S))
    f_leg = ImageFont.truetype(FONT_R, int(30 * S))
    f_leg_b = ImageFont.truetype(FONT_B, int(30 * S))

    st = net['stats']
    title = f"с. {name} — оптическая сеть доступа FTTH (GPON)"
    sub = (f"{snp['district']} район, {snp['okrug']} • централизованная древовидная топология • "
           f"домохозяйств: {st['households']} (по лоту: {st['expected']})")

    # заголовок на плашке сверху
    tb = dr.textbbox((0, 0), title, font=f_title)
    sb = dr.textbbox((0, 0), sub, font=f_sub)
    tw = max(tb[2], sb[2]) + 60 * S
    th = tb[3] + sb[3] + 66 * S
    dr.rectangle([0, 0, tw, th], fill=(10, 25, 40, 215))
    dr.text((30 * S, 10 * S), title, font=f_title, fill=(255, 255, 255))
    dr.text((30 * S, tb[3] + 22 * S), sub, font=f_sub, fill=(210, 230, 245))

    # легенда
    leg_items = [
        ('orsh', 'ОРШ — оптическая распределительная шкафа (центр сети)'),
        ('mfb', 'муфта разветвления (узел дерева)'),
        ('mft', 'муфта терминальная (подключение дропов)'),
        ('tree', 'распределительный кабель (волоконность 8-144)'),
        ('drop', 'дроп-кабель до домохозяйства'),
        ('hh', 'домохозяйство'),
    ]
    lx, ly = 24 * S, th + 30 * S
    lh = int(46 * S)
    lw = int(660 * S)
    dr.rectangle([lx, ly, lx + lw, ly + lh * len(leg_items) + 16 * S], fill=(10, 25, 40, 190))
    cy = ly + 8 * S
    for key, txt in leg_items:
        cx = lx + 24 * S
        if key == 'orsh':
            dr.polygon([(cx + 12 * S, cy - 2 * S), (cx + 24 * S, cy + 10 * S),
                        (cx + 12 * S, cy + 22 * S), (cx, cy + 10 * S)],
                       fill=(255, 60, 60), outline=(255, 255, 255))
        elif key == 'mfb':
            dr.rectangle([cx, cy + 2 * S, cx + 22 * S, cy + 20 * S], fill=(255, 128, 0),
                         outline=(255, 255, 255))
        elif key == 'mft':
            dr.ellipse([cx + 2 * S, cy + 3 * S, cx + 20 * S, cy + 21 * S], fill=(255, 90, 0),
                       outline=(255, 255, 255))
        elif key == 'tree':
            dr.line([(cx, cy + 11 * S), (cx + 24 * S, cy + 11 * S)], fill=(0, 229, 255), width=4)
        elif key == 'drop':
            dr.line([(cx, cy + 11 * S), (cx + 24 * S, cy + 11 * S)], fill=(0, 200, 255), width=2)
        elif key == 'hh':
            dr.ellipse([cx + 8 * S, cy + 6 * S, cx + 18 * S, cy + 16 * S], fill=(230, 40, 40))
        dr.text((cx + 40 * S, cy), txt, font=f_leg, fill=(235, 245, 255))
        cy += lh

    # масштабная линейка (200 м)
    mpp = geo['m_per_px']
    bar_px = int(200 / mpp)
    bx, by = 30 * S, Hc - 60 * S
    dr.rectangle([bx, by, bx + bar_px, by + 14 * S], fill=(255, 255, 255))
    for i in range(4):
        if i % 2 == 0:
            dr.rectangle([bx + i * bar_px // 4, by, bx + (i + 1) * bar_px // 4, by + 14 * S],
                         fill=(30, 30, 30))
    dr.text((bx, by - 40 * S), "200 м", font=f_leg_b, fill=(255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0))

    # стрелка севера
    nx, ny = Wc - 120 * S, 90 * S
    dr.polygon([(nx, ny - 50 * S), (nx - 16 * S, ny + 10 * S), (nx, ny - 8 * S), (nx + 16 * S, ny + 10 * S)],
               fill=(255, 255, 255), outline=(0, 0, 0))
    dr.text((nx - 10 * S, ny + 14 * S), "С", font=f_leg_b, fill=(255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0))

    # подпись ОРШ
    dr.text((ox + 34 * S, oy - 22 * S), "ОРШ", font=f_leg_b, fill=(255, 255, 255),
            stroke_width=3, stroke_fill=(120, 0, 0))

    out_path = f'{OUT_DIR}/{idx:02d}_{name}_FTTH.png'
    canvas_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    cv2.imwrite(out_path, canvas_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    print(f"  => {out_path} ({os.path.getsize(out_path)/1e6:.1f} МБ)")

    # превью для QA
    k = max(1, max(Hc, Wc) // 1600)
    prev = cv2.resize(canvas_bgr, (Wc // k, Hc // k), interpolation=cv2.INTER_AREA)
    cv2.imwrite(f'{WORK}/qa/{name}_render.png', prev, [cv2.IMWRITE_PNG_COMPRESSION, 7])

for snp in SNPS:
    render(snp['name'])
