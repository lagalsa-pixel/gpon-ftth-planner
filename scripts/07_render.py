# -*- coding: utf-8 -*-
"""
Шаг 7. Рендер полноразмерных карт FTTH-сети на мозаиках Google z18.
Выход: download/snp_vko/<NN>_<key>_ftth.png (полная карта) + <NN>_<key>_ftth_fragment.png
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json, DL
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

C_FEEDER = (30, 110, 255, 210)
C_DROP = (255, 225, 0, 235)
C_COUP = (0, 255, 225, 255)
C_COUP_OUT = (0, 60, 60, 255)
C_HH = (255, 70, 70, 255)
C_ANCHOR = (255, 255, 255, 255)

def render_village(v):
    key = v['key']
    g = load_json('/home/z/my-project/work/mosaic_geo.json')[key]
    net = load_json(f'{vdir(key)}/network.json')
    hhs = load_json(f'{vdir(key)}/households.json')
    mos = Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB')
    W, H = mos.size
    st = net['stats']

    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)

    # --- дропы ---
    for dd in net['drops']:
        poly = [(p[0], p[1]) for p in dd['poly']]
        if len(poly) >= 2:
            dr.line(poly, fill=C_DROP, width=2)

    # --- магистраль ---
    for seg in net['feeder_edges']:
        dr.line([(seg[0][0], seg[0][1]), (seg[1][0], seg[1][1])], fill=C_FEEDER, width=5)

    # --- домохозяйства ---
    for h in hhs:
        x, y = h['cx'], h['cy']
        dr.rectangle([x - 4, y - 4, x + 4, y + 4], fill=C_HH)

    # --- муфты ---
    f_lbl = ImageFont.truetype(FB, 13)
    for c in net['couplers']:
        x, y = c['x'], c['y']
        dr.rectangle([x - 6, y - 6, x + 6, y + 6], fill=C_COUP, outline=C_COUP_OUT, width=2)
        dr.text((x + 8, y - 7), c['label'], font=f_lbl, fill=(255, 255, 255, 255),
                stroke_width=2, stroke_fill=(0, 40, 40, 255))

    # --- ОРШ ---
    ax, ay = net['anchor']['x'], net['anchor']['y']
    R = 26
    dr.ellipse([ax - R, ay - R, ax + R, ay + R], fill=(255, 255, 255, 90), outline=C_ANCHOR, width=5)
    # звезда
    pts = []
    for i in range(10):
        r = R * (0.55 if i % 2 else 1.0)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    dr.polygon(pts, fill=(255, 40, 40, 255), outline=(255, 255, 255, 255))
    f_big = ImageFont.truetype(FB, 30)
    dr.text((ax + R + 8, ay - 16), "ЦУ — ОРШ", font=f_big, fill=(255, 255, 255, 255),
            stroke_width=3, stroke_fill=(120, 0, 0, 255))

    out = mos.convert('RGBA')
    out.alpha_composite(ov)
    out = out.convert('RGB')

    # --- шапка ---
    HH = 150
    canvas = Image.new('RGB', (W, H + HH), (10, 18, 30))
    canvas.paste(out, (0, HH))
    dh = ImageDraw.Draw(canvas)
    f1 = ImageFont.truetype(FB, 46)
    f2 = ImageFont.truetype(FR, 27)
    f3 = ImageFont.truetype(FB, 27)
    dh.text((26, 12), f"с. {v['name']} — проект FTTH-сети (централизованная древовидная архитектура)", font=f1, fill=(240, 245, 250))
    dh.text((26, 68), f"{v['raion']} · {v['okrug']} · спутник Google z18 ({g['mpp']:.2f} м/px)", font=f2, fill=(170, 185, 200))
    line = (f"Домохозяйств: {st['served']} из {st['households']} определённых (по данным Excel: {v['hh']})   ·   "
            f"Муфт: {st['couplers']}   ·   Магистраль (ОРШ-муфты): {st['feeder_km']} км   ·   "
            f"Дропы: {st['drop_km']} км   ·   Средний дроп: {st['avg_drop_m']} м")
    dh.text((26, 106), line, font=f3, fill=(255, 220, 120))

    # --- легенда ---
    lg_w, lg_h = 560, 268
    lg = Image.new('RGBA', (lg_w, lg_h), (8, 12, 20, 215))
    lgd = ImageDraw.Draw(lg)
    fl = ImageFont.truetype(FB, 24)
    fl2 = ImageFont.truetype(FR, 22)
    lgd.text((16, 10), "УСЛОВНЫЕ ОБОЗНАЧЕНИЯ", font=fl, fill=(240, 240, 240))
    yy = 56
    lgd.ellipse([16, yy - 14, 44, yy + 14], outline=(255, 255, 255), width=3)
    lgd.polygon([(30 - 8, yy), (26, yy - 12), (34, yy - 12)], fill=(255, 40, 40))
    lgd.text((58, yy - 13), "ЦУ / ОРШ — здание связи (почта/аналог)", font=fl2, fill=(230, 230, 230))
    yy += 42
    lgd.rectangle([16, yy - 12, 44, yy + 12], fill=C_COUP[:3], outline=(0, 60, 60), width=2)
    lgd.text((58, yy - 13), "Оптическая муфта (точка ветвления)", font=fl2, fill=(230, 230, 230))
    yy += 42
    lgd.line([(14, yy), (48, yy)], fill=C_FEEDER[:3], width=5)
    lgd.text((58, yy - 13), "Магистральный кабель ОРШ-муфты", font=fl2, fill=(230, 230, 230))
    yy += 42
    lgd.line([(14, yy), (48, yy)], fill=C_DROP[:3], width=3)
    lgd.text((58, yy - 13), "Дроп-кабель к домохозяйству", font=fl2, fill=(230, 230, 230))
    yy += 42
    lgd.rectangle([20, yy - 9, 36, yy + 9], fill=C_HH[:3])
    lgd.text((58, yy - 13), "Домохозяйство", font=fl2, fill=(230, 230, 230))
    canvas.paste(lg, (16, HH + H - lg_h - 16), lg)

    # --- масштабная линейка (200 м) ---
    sb_px = 200.0 / g['mpp']
    x0 = W - int(sb_px) - 40
    y0 = HH + H - 46
    dh.line([(x0, y0), (x0 + sb_px, y0)], fill=(255, 255, 255), width=5)
    for xx in (x0, x0 + sb_px / 2, x0 + sb_px):
        dh.line([(xx, y0 - 8), (xx, y0 + 8)], fill=(255, 255, 255), width=4)
    dh.text((x0 + sb_px / 2 - 30, y0 - 40), "200 м", font=ImageFont.truetype(FB, 26), fill=(255, 255, 255))

    # стрелка севера
    nx, ny = W - 70, HH + 60
    dh.polygon([(nx, ny - 34), (nx - 13, ny + 16), (nx, ny + 6), (nx + 13, ny + 16)],
               outline=(255, 255, 255), width=3)
    dh.text((nx - 8, ny + 18), "С", font=ImageFont.truetype(FB, 26), fill=(255, 255, 255))

    num = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altaiskiy'].index(key) + 1
    fpath = f'{DL}/{num:02d}_{key}_ftth.png'
    canvas.save(fpath)
    print(f"{v['name']}: {fpath} ({canvas.width}x{canvas.height})")

    # --- фрагмент вокруг ОРШ ---
    fs = 2600
    cx = int(max(fs // 2, min(W - fs // 2, ax)))
    cy = int(max(fs // 2, min(H - fs // 2, ay)))
    frag = canvas.crop((cx - fs // 2, cy - fs // 2 + HH, cx + fs // 2, cy + fs // 2 + HH))
    fpath2 = f'{DL}/{num:02d}_{key}_ftth_fragment.png'
    frag.save(fpath2)
    print(f"   фрагмент: {fpath2} (2600x2600 вокруг ОРШ)")
    return fpath

if __name__ == '__main__':
    for v in VILLAGES:
        render_village(v)
