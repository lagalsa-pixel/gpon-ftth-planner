# -*- coding: utf-8 -*-
"""
Шаг 10. Рендер FTTH-сетей на обрезанных пользователем кадрах.
Геометрия network_v2.json (координаты исходной мозаики) переводится в пиксели
кадра через M_inv (crop_transform.json), затем рисуется в стиле шага 07:
шапка со статистикой, легенда, масштабная линейка, стрелка севера, фрагмент вокруг ОРШ.
Выход: download/snp_vko/<NN>_<key>_ftth_crop.png + <NN>_<key>_ftth_crop_fragment.png
"""
import sys, os, math, gc
sys.path.insert(0, os.path.dirname(__file__))
from common import V, vdir, load_json, DL
import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

C_FEEDER = (30, 110, 255, 210)
C_DROP = (255, 225, 0, 235)
C_COUP = (0, 255, 225, 255)
C_COUP_OUT = (0, 60, 60, 255)
C_HH = (255, 70, 70, 255)
C_ANCHOR = (255, 255, 255, 255)

TASKS = ['solnechnoe', 'perevalnoe', 'prigorodnoe', 'altaiskiy']
BASE = '/home/z/my-project'


def render_crop(key):
    v = V[key]
    g = load_json(f'{BASE}/work/mosaic_geo.json')[key]
    t = load_json(f'{vdir(key)}/crop_transform.json')
    net = load_json(f'{vdir(key)}/network_v2.json')
    hhs_all = load_json(f'{vdir(key)}/households.json')
    num = ['verhneberezovka', 'solnechnoe', 'perevalnoe', 'vinnoe',
           'prigorodnoe', 'altaiskiy'].index(key) + 1

    Mi = t['M_inv']                     # old px -> new px (2x3)
    scale = t['scale']                  # new px = scale * old px (по охвату)
    k = 1.0 / scale                     # коэффициент увеличения отрисовки
    mpp_new = g['mpp'] * scale          # м на пиксель кадра
    S = lambda val: max(1, int(round(val * k)))   # размер в px кадра

    def T(p):
        x, y = p
        return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
                Mi[1][0] * x + Mi[1][1] * y + Mi[1][2])

    img_path = t['new_image']
    if not os.path.isabs(img_path):
        img_path = os.path.join(BASE, img_path)
    base = Image.open(img_path).convert('RGBA')
    W, H = base.size
    print(f"{v['name']}: кадр {W}x{H}, k={k:.2f}, {mpp_new:.4f} м/px (номинально)")
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    st = net['stats']

    # --- магистраль (рисуется ПЕРВОЙ — дропы поверх, чтобы не терялись на общих участках) ---
    for seg in net['feeder_edges']:
        a, b = T(seg[0]), T(seg[1])
        dr.line([a, b], fill=C_FEEDER, width=S(5))

    # --- дропы (с тёмной обводкой-футляром для контраста на любом фоне) ---
    for dd in net['drops']:
        poly = [T(p) for p in dd['poly']]
        if len(poly) >= 2:
            dr.line(poly, fill=(50, 42, 0, 200), width=S(3.5))
    for dd in net['drops']:
        poly = [T(p) for p in dd['poly']]
        if len(poly) >= 2:
            dr.line(poly, fill=C_DROP, width=S(2.5))

    # --- домохозяйства (в кадре): обслуженные заливкой, прочие контуром ---
    x0, y0, x1, y1 = net['crop']['rect']
    served_ids = {dd['hh_id'] for dd in net['drops']}
    n_hh = 0
    for h in hhs_all:
        if not (x0 - 2 <= h['cx'] <= x1 + 2 and y0 - 2 <= h['cy'] <= y1 + 2):
            continue
        n_hh += 1
        x, y = T((h['cx'], h['cy']))
        r = S(4)
        if h['id'] in served_ids:
            dr.rectangle([x - r, y - r, x + r, y + r], fill=C_HH)
        else:
            dr.rectangle([x - r, y - r, x + r, y + r], outline=C_HH, width=S(1.5))

    # --- муфты ---
    f_lbl = ImageFont.truetype(FB, S(13))
    for c in net['couplers']:
        x, y = T((c['x'], c['y']))
        r = S(6)
        dr.rectangle([x - r, y - r, x + r, y + r], fill=C_COUP, outline=C_COUP_OUT, width=S(2))
        dr.text((x + S(8), y - S(7)), c['label'], font=f_lbl, fill=(255, 255, 255, 255),
                stroke_width=S(1.5), stroke_fill=(0, 40, 40, 255))

    # --- ОРШ ---
    ax, ay = T((net['anchor']['x'], net['anchor']['y']))
    R = S(26)
    dr.ellipse([ax - R, ay - R, ax + R, ay + R], fill=(255, 255, 255, 90), outline=C_ANCHOR, width=S(5))
    pts = []
    for i in range(10):
        r = R * (0.55 if i % 2 else 1.0)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    dr.polygon(pts, fill=(255, 40, 40, 255), outline=(255, 255, 255, 255))
    f_big = ImageFont.truetype(FB, S(30))
    dr.text((ax + R + S(8), ay - S(16)), "ЦУ — ОРШ", font=f_big, fill=(255, 255, 255, 255),
            stroke_width=S(3), stroke_fill=(120, 0, 0, 255))

    base.alpha_composite(ov)
    del ov
    gc.collect()
    rgb = base.convert('RGB')
    del base
    gc.collect()

    # --- шапка ---
    HH = S(150)
    canvas = Image.new('RGB', (W, H + HH), (10, 18, 30))
    canvas.paste(rgb, (0, HH))
    del rgb
    gc.collect()
    dh = ImageDraw.Draw(canvas)
    f1 = ImageFont.truetype(FB, S(46))
    f2 = ImageFont.truetype(FR, S(27))
    f3 = ImageFont.truetype(FB, S(27))
    dh.text((S(26), S(12)),
            f"с. {v['name']} — проект FTTH-сети (централизованная древовидная архитектура)",
            font=f1, fill=(240, 245, 250))
    dh.text((S(26), S(68)),
            f"{v['raion']} · {v['okrug']} · спутник Google z18 · рабочий кадр пользователя",
            font=f2, fill=(170, 185, 200))
    line = (f"Домохозяйств в кадре: {st['served']} обслужено из {st['households_in_crop']} "
            f"(определено в зоне: {len(hhs_all)}, по данным Excel: {v['hh']})   ·   "
            f"Муфт: {st['couplers']}   ·   Магистраль: {st['feeder_km']} км   ·   "
            f"Дропы: {st['drop_km']} км   ·   Средний дроп: {st['avg_drop_m']} м")
    dh.text((S(26), S(106)), line, font=f3, fill=(255, 220, 120))

    # --- легенда: автоподбор угла (BL/BR) с минимумом перекрываемых ДХ ---
    lg_w, lg_h = S(560), S(268)
    x0c, y0c, x1c, y1c = net['crop']['rect']
    hh_pts = [T((h['cx'], h['cy'])) for h in hhs_all
              if x0c - 2 <= h['cx'] <= x1c + 2 and y0c - 2 <= h['cy'] <= y1c + 2]

    def covered_count(lx, ly):
        cnt = 0
        for (hx_, hy_) in hh_pts:
            if lx - 20 <= hx_ <= lx + lg_w + 20 and ly - 20 <= hy_ <= ly + lg_h + 20:
                cnt += 1
        return cnt

    pos_bl = (S(16), HH + H - lg_h - S(16))
    pos_br = (W - lg_w - S(16), HH + H - lg_h - S(16))
    n_bl = covered_count(*pos_bl)
    n_br = covered_count(*pos_br)
    lg_pos = pos_bl if n_bl <= n_br else pos_br
    legend_right = (lg_pos == pos_br)
    print(f"  легенда: BL перекрывает {n_bl} ДХ, BR — {n_br}; выбор {'правый' if legend_right else 'левый'} нижний угол")
    lg = Image.new('RGBA', (lg_w, lg_h), (8, 12, 20, 215))
    lgd = ImageDraw.Draw(lg)
    fl = ImageFont.truetype(FB, S(24))
    fl2 = ImageFont.truetype(FR, S(22))
    lgd.text((S(16), S(10)), "УСЛОВНЫЕ ОБОЗНАЧЕНИЯ", font=fl, fill=(240, 240, 240))
    yy = S(56)
    lgd.ellipse([S(16), yy - S(14), S(44), yy + S(14)], outline=(255, 255, 255), width=S(3))
    lgd.polygon([(S(30) - S(8), yy), (S(26), yy - S(12)), (S(34), yy - S(12))], fill=(255, 40, 40))
    lgd.text((S(58), yy - S(13)), "ЦУ / ОРШ — здание связи (почта/аналог)", font=fl2, fill=(230, 230, 230))
    yy += S(42)
    lgd.rectangle([S(16), yy - S(12), S(44), yy + S(12)], fill=C_COUP[:3], outline=(0, 60, 60), width=S(2))
    lgd.text((S(58), yy - S(13)), "Оптическая муфта (точка ветвления)", font=fl2, fill=(230, 230, 230))
    yy += S(42)
    lgd.line([(S(14), yy), (S(48), yy)], fill=C_FEEDER[:3], width=S(5))
    lgd.text((S(58), yy - S(13)), "Магистральный кабель ОРШ-муфты", font=fl2, fill=(230, 230, 230))
    yy += S(42)
    lgd.line([(S(14), yy), (S(48), yy)], fill=C_DROP[:3], width=S(3))
    lgd.text((S(58), yy - S(13)), "Дроп-кабель к домохозяйству", font=fl2, fill=(230, 230, 230))
    yy += S(42)
    lgd.rectangle([S(20), yy - S(9), S(36), yy + S(9)], fill=C_HH[:3])
    lgd.text((S(58), yy - S(13)), "Домохозяйство", font=fl2, fill=(230, 230, 230))
    canvas.paste(lg, lg_pos, lg)
    del lg
    gc.collect()

    # --- масштабная линейка (200 м): в углу напротив легенды ---
    sb_px = 200.0 / mpp_new
    if legend_right:
        x0s = S(40)
    else:
        x0s = W - int(sb_px) - S(40)
    y0s = HH + H - S(46)
    dh.line([(x0s, y0s), (x0s + sb_px, y0s)], fill=(255, 255, 255), width=S(5))
    for xx in (x0s, x0s + sb_px / 2, x0s + sb_px):
        dh.line([(xx, y0s - S(8)), (xx, y0s + S(8))], fill=(255, 255, 255), width=S(4))
    dh.text((x0s + sb_px / 2 - S(30), y0s - S(40)), "200 м",
            font=ImageFont.truetype(FB, S(26)), fill=(255, 255, 255))

    # --- стрелка севера ---
    nx, ny = W - S(70), HH + S(60)
    dh.polygon([(nx, ny - S(34)), (nx - S(13), ny + S(16)), (nx, ny + S(6)), (nx + S(13), ny + S(16))],
               outline=(255, 255, 255), width=S(3))
    dh.text((nx - S(8), ny + S(18)), "С", font=ImageFont.truetype(FB, S(26)), fill=(255, 255, 255))

    fpath = f'{DL}/{num:02d}_{key}_ftth_crop.png'
    canvas.save(fpath)
    print(f"  карта: {fpath} ({canvas.width}x{canvas.height})")

    # --- фрагмент вокруг ОРШ ---
    fs = min(S(1400), W, H)   # ~537 м при k=2, но не шире кадра
    cx = int(max(fs // 2, min(W - fs // 2, ax)))
    cy = int(max(fs // 2, min(H - fs // 2, ay)))
    frag = canvas.crop((cx - fs // 2, cy - fs // 2 + HH, cx + fs // 2, cy + fs // 2 + HH))
    fpath2 = f'{DL}/{num:02d}_{key}_ftth_crop_fragment.png'
    frag.save(fpath2)
    print(f"  фрагмент: {fpath2} ({fs}x{fs} вокруг ОРШ)")
    del frag, canvas
    gc.collect()


if __name__ == '__main__':
    import sys as _sys
    keys = _sys.argv[1:] if len(_sys.argv) > 1 else TASKS
    for key in keys:
        if key not in TASKS:
            continue
        render_crop(key)
