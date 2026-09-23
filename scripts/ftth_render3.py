#!/usr/bin/env python3
"""Отрисовка FTTH-сетей v3 на космоснимках Google Satellite z18 (кэш тайлов).

Отличия v2 -> v3: дропы прокладываются к ФАСАДАМ зданий (ближайшая точка контура
главного жилого дома), ОРШ размещены в 1-медиане дорожного графа (приоритет
перекрёсткам), ввод в здание 10 м. В легенде — статистика длин дропов."""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
DESIGN_DIR = os.path.join(BASE, 'ftth_out')

from ftth_render import (download_tiles, lon2mx, lat2my,
                         load_font, star_points, CACHE,
                         C_TRUNK, C_TRUNK_CASE, C_DIST, C_DIST_CASE, C_DROP,
                         C_HH, C_HH_FILL, C_SPL, C_POP, C_AERIAL)

OUT_DIR = '/home/z/my-project/download/snp_vko_ftth_v3'
PREV_DIR = os.path.join(OUT_DIR, 'previews')
os.makedirs(PREV_DIR, exist_ok=True)

C_EXTRA = (190, 255, 190, 255)          # заливка маркера доп. абонента
C_EXTRA_OUT = (0, 110, 0, 255)          # кайма маркера


def render_village3(d, idx):
    name = d['name']
    key = d['key']
    lat_min, lon_min, lat_max, lon_max = d['bbox']
    mx0, mx1 = lon2mx(lon_min), lon2mx(lon_max)
    my0, my1 = lat2my(lat_max), lat2my(lat_min)
    ox, oy = math.floor(mx0), math.floor(my0)
    W = int(math.ceil(mx1)) - ox
    H = int(math.ceil(my1)) - oy
    mpp = (40075016.686 * math.cos(math.radians((lat_min + lat_max) / 2))) / (2 ** 18 * 256)

    tx0, tx1 = math.floor(mx0 / 256), math.floor(mx1 / 256)
    ty0, ty1 = math.floor(my0 / 256), math.floor(my1 / 256)
    tiles = [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]
    print(f'[{key}] кадр {W}x{H} px ({(mx1-mx0)*mpp:.0f}x{(my1-my0)*mpp:.0f} м, {mpp:.3f} м/px), '
          f'тайлов {len(tiles)}', flush=True)
    ok, fail = download_tiles(tiles)
    if fail:
        print(f'[{key}] !!! не скачано тайлов: {fail}')

    img = Image.new('RGB', (W, H), (28, 28, 28))
    for tx, ty in tiles:
        p = os.path.join(CACHE, f'{tx}_{ty}.png')
        if os.path.exists(p) and os.path.getsize(p) > 3000:
            tile = Image.open(p).convert('RGB')
            img.paste(tile, (tx * 256 - ox, ty * 256 - oy))

    def PX(lat, lon):
        return (lon2mx(lon) - ox, lat2my(lat) - oy)

    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)

    # ---- 1. выявленные домохозяйства: заливка + контуры построек ----
    n_poly = 0
    for h in d['households']:
        if h.get('extra'):
            continue
        for poly in h.get('polygons', []):
            pts = [PX(la, lo) for la, lo in poly]
            if len(pts) >= 3:
                dr.polygon(pts, fill=C_HH_FILL, outline=C_HH, width=3)
                n_poly += 1

    # ---- 2. дропы: от снапа на дороге к фасаду здания ----
    for dp in d['drops']:
        a = PX(dp['snap'][0], dp['snap'][1])
        b = PX(dp['to'][0], dp['to'][1])
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1:
            dr.line([a, b], fill=C_DROP, width=2)

    # ---- 3. воздушные перемычки ----
    for seg in d.get('aerial', []):
        a = PX(seg[0][0], seg[0][1])
        b = PX(seg[1][0], seg[1][1])
        dr.line([a, b], fill=C_AERIAL, width=3)

    # ---- 4. распределительная сеть ----
    for poly in d['dist_polylines']:
        pts = [PX(la, lo) for la, lo in poly]
        if len(pts) >= 2:
            dr.line(pts, fill=C_DIST_CASE, width=9, joint='curve')
            dr.line(pts, fill=C_DIST, width=5, joint='curve')

    # ---- 5. магистраль ----
    for poly in d['trunk_polylines']:
        pts = [PX(la, lo) for la, lo in poly]
        if len(pts) >= 2:
            dr.line(pts, fill=C_TRUNK_CASE, width=14, joint='curve')
            dr.line(pts, fill=C_TRUNK, width=9, joint='curve')

    # ---- 6. маркеры доп. абонентов и номера «ОРШ.№» с защитой от наложений ----
    f_num = load_font(15)
    for h in d['households']:
        if h.get('extra'):
            x, y = PX(h['lat'], h['lon'])
            r = 8
            dr.ellipse([x - r, y - r, x + r, y + r], fill=C_EXTRA,
                       outline=C_EXTRA_OUT, width=3)

    CELL = 64
    _grid = {}

    def _collide(r):
        for gx in range(int(r[0] // CELL), int(r[2] // CELL) + 1):
            for gy in range(int(r[1] // CELL), int(r[3] // CELL) + 1):
                for q in _grid.get((gx, gy), ()):
                    if not (r[2] < q[0] or r[0] > q[2] or r[3] < q[1] or r[1] > q[3]):
                        return True
        return False

    def _occupy(r):
        for gx in range(int(r[0] // CELL), int(r[2] // CELL) + 1):
            for gy in range(int(r[1] // CELL), int(r[3] // CELL) + 1):
                _grid.setdefault((gx, gy), []).append(r)

    th = 16
    for h in d['households']:
        x, y = PX(h['lat'], h['lon'])
        txt = h['label']
        tw = dr.textlength(txt, font=f_num)
        cands = [(x + 5, y - 10), (x + 11, y + 8), (x - 5 - tw, y - 10),
                 (x - 5 - tw, y + 8), (x + 5, y - 27), (x + 5, y + 24)]
        chosen = cands[0]
        for c in cands:
            r = (c[0] - 1, c[1] - 1, c[0] + tw + 1, c[1] + th + 1)
            if 0 <= r[0] and r[2] < W and 0 <= r[1] and r[3] < H and not _collide(r):
                chosen = c
                break
        r = (chosen[0] - 1, chosen[1] - 1, chosen[0] + tw + 1, chosen[1] + th + 1)
        _occupy(r)
        if h.get('extra'):
            dr.text(chosen, txt, font=f_num, fill=(225, 255, 225, 255),
                    stroke_width=2, stroke_fill=(0, 60, 0, 255))
        else:
            dr.text(chosen, txt, font=f_num, fill=(255, 255, 255, 255),
                    stroke_width=2, stroke_fill=(0, 0, 0, 255))

    # ---- 7. ОРШ (шкафы со сплиттерами GPON 1:32, 1-медиана дорожного графа) ----
    f_spl = load_font(24)
    for s in d['splitters']:
        x, y = PX(s['lat'], s['lon'])
        r = 11
        dr.rectangle([x - r, y - r, x + r, y + r], fill=C_SPL,
                     outline=(255, 255, 255, 255), width=3)
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 255, 255, 255))
        dr.text((x + r + 6, y - 14), s['id'], font=f_spl, fill=(255, 220, 120, 255),
                stroke_width=2, stroke_fill=(0, 0, 0, 255))

    # ---- 8. POP ----
    px, py = PX(d['pop']['lat'], d['pop']['lon'])
    dr.polygon(star_points(px, py, 26, 11), fill=C_POP, outline=(255, 255, 255, 255))
    f_pop = load_font(30)
    dr.text((px + 34, py - 18), 'POP', font=f_pop, fill=(255, 120, 110, 255),
            stroke_width=3, stroke_fill=(0, 0, 0, 255))

    # ---- 9. титульная панель ----
    s = d['stats']
    f_t1 = load_font(64)
    f_t2 = load_font(36)
    f_t3 = load_font(34)
    t1 = f'ОПТИЧЕСКАЯ СЕТЬ FTTH · GPON — с. {name}'
    t2 = (f"{d['district']}" + (f" · {d['okrug']}" if d['okrug'] else '') +
          f" · ВКО · снимок Google Satellite z18 ({mpp:.2f} м/px)")
    t3 = (f"Абоненты: {s['n_hh']} = выявлено {s['n_identified']} + добавлено {s['n_added']} "
          f"(по таблице СНП ВКО — {s['expected']}) · ОРШ: {s['splitters']} · "
          f"оптического кабеля: {s['total_km']:.1f} км · дроп: ср. {s['drop_avg_m']:.0f} / макс {s['drop_max_m']:.0f} м")
    bar_h = 212
    dr.rectangle([0, 0, W, bar_h], fill=(0, 0, 0, 200))
    dr.rectangle([0, bar_h, W, bar_h + 6], fill=C_TRUNK)
    tw = dr.textlength(t1, font=f_t1)
    dr.text(((W - tw) / 2, 18), t1, font=f_t1, fill=(255, 255, 255, 255))
    tw2 = dr.textlength(t2, font=f_t2)
    dr.text(((W - tw2) / 2, 96), t2, font=f_t2, fill=(200, 210, 220, 255))
    tw3 = dr.textlength(t3, font=f_t3)
    dr.text(((W - tw3) / 2, 156), t3, font=f_t3, fill=(255, 236, 160, 255))

    # ---- 10. легенда ----
    f_lh = load_font(40)
    f_l = load_font(33)
    lh = 58
    load_pct = s['n_hh'] / s['splitters'] / 32 * 100
    rows = [
        ('line', C_TRUNK, 9, f"Магистральный кабель POP → ОРШ — {s['trunk_km']:.2f} км"),
        ('line', C_DIST, 5, f"Распределительный кабель по улицам — {s['dist_km']:.2f} км"),
        ('line', C_DROP, 2, f"Дропы к фасадам зданий — {s['drops_km']:.2f} км "
                            f"(ср. {s['drop_avg_m']:.0f} м, медиана {s['drop_med_m']:.0f} м, макс {s['drop_max_m']:.0f} м)"),
        ('line', C_AERIAL, 4, f"Выноски распределения к удалённым ДХ + воздушные перемычки — "
                              f"{s.get('spur_km', 0):.2f} км ({s.get('spur_hh', 0)} ДХ)"
                              if s.get('spur_hh', 0) else "Воздушные перемычки графа дорог"),
        ('poly', C_HH, 0, f"Домохозяйства выявленные (контуры построек) — {s['n_identified']}"),
        ('extra', C_EXTRA, 0,
         f"Доп. абоненты (до числа по таблице) — {s['n_added']}" if s['n_added'] > 0
         else f"Доп. абоненты не требуются: выявлено {s['n_identified']} ≥ {s['expected']} (таблица)"),
        ('spl', C_SPL, 0, f"ОРШ со сплиттерами GPON 1:32 — {s['splitters']} шт. "
                          f"(ср. {s['avg_hh_per_splitter']}, загрузка портов {load_pct:.0f}%)"),
        ('pop', C_POP, 0, "POP — точка приседания оператора"),
        ('num', None, 0, "Нумерация «ОРШ.№»: 12.7 = ОРШ 12, абонент 7"),
        ('text', None, 0, f"Всего оптического кабеля: {s['total_km']:.1f} км · волокон в магистрали: {s['trunk_fibers']}"),
        ('text', None, 0, "ОРШ: 1-медиана дорожного графа (приоритет перекрёсткам) · дропы к фасадам · ввод 10 м · запас 7%"),
    ]
    lw = 1560
    lhh = lh * len(rows) + 130
    lx, ly = W - lw - 40, bar_h + 46
    dr.rounded_rectangle([lx, ly, lx + lw, ly + lhh], radius=22, fill=(0, 0, 0, 195),
                         outline=(255, 255, 255, 255), width=2)
    dr.text((lx + 34, ly + 22), 'ЛЕГЕНДА · ПАРАМЕТРЫ СЕТИ', font=f_lh, fill=(255, 255, 255, 255))
    yy = ly + 96
    for kind, color, wgt, text in rows:
        cy = yy + lh / 2 - 6
        if kind == 'line':
            dr.line([lx + 34, cy, lx + 150, cy], fill=color, width=max(wgt, 4))
        elif kind == 'poly':
            dr.rectangle([lx + 40, cy - 16, lx + 144, cy + 16], outline=C_HH, width=4)
        elif kind == 'extra':
            dr.ellipse([lx + 62, cy - 15, lx + 122, cy + 15], fill=C_EXTRA,
                       outline=C_EXTRA_OUT, width=4)
        elif kind == 'spl':
            dr.rectangle([lx + 62, cy - 15, lx + 122, cy + 15], fill=C_SPL,
                         outline=(255, 255, 255, 255), width=3)
        elif kind == 'pop':
            dr.polygon(star_points(lx + 92, cy, 20, 9), fill=C_POP, outline=(255, 255, 255, 255))
        elif kind == 'num':
            dr.text((lx + 34, yy + 2), '12.7', font=f_l, fill=(255, 255, 255, 255),
                    stroke_width=2, stroke_fill=(0, 0, 0, 255))
        dr.text((lx + 180, yy + 2), text, font=f_l, fill=(235, 240, 245, 255))
        yy += lh

    # ---- 11. масштабная линейка и стрелка севера ----
    bar_m = 500
    bar_px = bar_m / mpp
    bx, by = 60, H - 110
    dr.rectangle([bx, by, bx + bar_px, by + 18], fill=(255, 255, 255, 255))
    for i in range(4):
        if i % 2 == 0:
            dr.rectangle([bx + i * bar_px / 4, by, bx + (i + 1) * bar_px / 4, by + 18], fill=(30, 30, 30, 255))
    dr.rectangle([bx, by, bx + bar_px, by + 18], outline=(255, 255, 255, 255), width=3)
    f_sc = load_font(40)
    dr.text((bx, by - 56), f'{bar_m} м', font=f_sc, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255))
    nx, ny = W - 130, H - 130
    dr.polygon([(nx, ny - 60), (nx - 22, ny + 26), (nx, ny + 8), (nx + 22, ny + 26)],
               fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    dr.text((nx - 12, ny + 34), 'N', font=f_sc, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255))

    # ---- композитинг и сохранение ----
    img = Image.alpha_composite(img.convert('RGBA'), ov).convert('RGB')
    out = os.path.join(OUT_DIR, f'{idx:02d}_{name}_FTTH.png')
    img.save(out, 'PNG', compress_level=6)
    sz = os.path.getsize(out) / 1e6
    print(f'[{key}] сохранено {out} ({sz:.0f} МБ, построек {n_poly})', flush=True)

    prev = img.copy()
    prev.thumbnail((1600, 1600), Image.LANCZOS)
    pv = os.path.join(PREV_DIR, f'{idx:02d}_{name}_preview.jpg')
    prev.convert('RGB').save(pv, 'JPEG', quality=88)
    print(f'[{key}] превью {pv}', flush=True)


def main():
    from ftth_households import VILLAGES
    order = [v['key'] for v in VILLAGES]
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    idx0 = int(os.environ.get('IDX0', '1'))
    items = [(i + idx0, k) for i, k in enumerate(order) if not only or k in only]
    for idx, key in items:
        d = json.load(open(os.path.join(DESIGN_DIR, f'{key}_design3.json')))
        render_village3(d, idx)


if __name__ == '__main__':
    main()
