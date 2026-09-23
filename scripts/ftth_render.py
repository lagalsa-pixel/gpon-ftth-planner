#!/usr/bin/env python3
"""Отрисовка FTTH-сетей на космоснимках Google Satellite z18.
Скачивает тайлы по итоговым границам, сшивает кадр, наносит слои:
домохозяйства (+номера), дропы, распределительные и магистральные трассы,
сплиттеры, POP, легенда, масштабная линейка."""
import io, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(BASE, 'ftth_out')
CACHE = os.path.join(BASE, 'tiles_cache', 'z18')
OUT_DIR = '/home/z/my-project/download/snp_vko_ftth'
PREV_DIR = os.path.join(OUT_DIR, 'previews')
os.makedirs(CACHE, exist_ok=True)
os.makedirs(PREV_DIR, exist_ok=True)

Z = 18
WORLD = 2 ** Z * 256
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# цвета
C_TRUNK = (255, 59, 48, 255)
C_TRUNK_CASE = (110, 0, 0, 255)
C_DIST = (0, 200, 255, 255)
C_DIST_CASE = (0, 40, 80, 255)
C_DROP = (255, 224, 102, 225)
C_HH = (80, 255, 80, 255)
C_HH_FILL = (60, 255, 60, 42)
C_SPL = (255, 159, 28, 255)
C_POP = (255, 42, 42, 255)
C_AERIAL = (255, 255, 255, 200)

NUMBERS = True


def lon2mx(lon):
    return (lon + 180.0) / 360.0 * WORLD


def lat2my(lat):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * WORLD


def fetch_tile(tx, ty, retries=4):
    path = os.path.join(CACHE, f'{tx}_{ty}.png')
    if os.path.exists(path) and os.path.getsize(path) > 3000:
        return tx, ty, True
    for att in range(retries):
        sub = att % 4
        url = f'https://mt{sub}.googleapis.com/vt?lyrs=s&x={tx}&y={ty}&z={Z}'
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200 and len(r.content) > 3000:
                magic = r.content[:3]
                if magic == b'\x89PN' or magic[:2] == b'\xff\xd8':
                    with open(path, 'wb') as f:
                        f.write(r.content)
                    return tx, ty, True
        except Exception:
            pass
        time.sleep(0.4 * (att + 1))
    return tx, ty, False


def download_tiles(tiles):
    ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fetch_tile, tx, ty) for tx, ty in tiles]
        for i, fu in enumerate(as_completed(futs), 1):
            _, _, good = fu.result()
            ok += bool(good)
            fail += not good
            if i % 200 == 0:
                print(f'    тайлы {i}/{len(tiles)} ({time.time()-t0:.0f} с), ошибок {fail}', flush=True)
    return ok, fail


def load_font(size):
    return ImageFont.truetype(FONT_BOLD, size)


def star_points(cx, cy, r_out, r_in):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def render_village(d, idx):
    name = d['name']
    key = d['key']
    lat_min, lon_min, lat_max, lon_max = d['bbox']
    mx0, mx1 = lon2mx(lon_min), lon2mx(lon_max)
    my0, my1 = lat2my(lat_max), lat2my(lat_min)
    ox, oy = math.floor(mx0), math.floor(my0)
    W = int(math.ceil(mx1)) - ox
    H = int(math.ceil(my1)) - oy
    mpp = (40075016.686 * math.cos(math.radians((lat_min + lat_max) / 2))) / WORLD

    tx0, tx1 = math.floor(mx0 / 256), math.floor(mx1 / 256)
    ty0, ty1 = math.floor(my0 / 256), math.floor(my1 / 256)
    tiles = [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]
    print(f'[{key}] кадр {W}x{H} px ({(mx1-mx0)*mpp:.0f}x{(my1-my0)*mpp:.0f} м, {mpp:.3f} м/px), тайлов {len(tiles)}', flush=True)
    ok, fail = download_tiles(tiles)
    if fail:
        print(f'[{key}] !!! не скачано тайлов: {fail}')
        missing = [(tx, ty) for tx, ty in tiles
                   if not (os.path.exists(os.path.join(CACHE, f'{tx}_{ty}.png')) and os.path.getsize(os.path.join(CACHE, f'{tx}_{ty}.png')) > 3000)]
        if len(missing) > len(tiles) * 0.02:
            print(f'[{key}] слишком много пропусков, отмена')
            return
        # пустые тайлы зальём серым
    print(f'[{key}] тайлы готовы (ok {ok}, fail {fail}), сшивка...', flush=True)

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

    # ---- 1. домохозяйства: заливка + контуры ----
    for h in d['households']:
        for poly in h['polygons']:
            pts = [PX(la, lo) for la, lo in poly]
            if len(pts) >= 3:
                dr.polygon(pts, fill=C_HH_FILL, outline=C_HH, width=3)

    # ---- 2. дропы ----
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

    # ---- 6. номера домохозяйств ----
    f_num = load_font(15)
    if NUMBERS:
        for h in d['households']:
            x, y = PX(h['lat'], h['lon'])
            dr.text((x + 4, y - 9), str(h['n']), font=f_num, fill=(255, 255, 255, 255),
                    stroke_width=2, stroke_fill=(0, 0, 0, 255))

    # ---- 7. сплиттеры ----
    f_spl = load_font(24)
    for s in d['splitters']:
        x, y = PX(s['lat'], s['lon'])
        r = 11
        dr.rectangle([x - r, y - r, x + r, y + r], fill=C_SPL,
                     outline=(255, 255, 255, 255), width=3)
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
    t1 = f'ОПТИЧЕСКАЯ СЕТЬ FTTH · GPON — с. {name}'
    t2 = (f"{d['district']}" + (f" · {d['okrug']}" if d['okrug'] else '') +
          f" · ВКО · снимок Google Satellite z18 ({mpp:.2f} м/px)")
    tw = dr.textlength(t1, font=f_t1)
    bar_h = 176
    dr.rectangle([0, 0, W, bar_h], fill=(0, 0, 0, 200))
    dr.rectangle([0, bar_h, W, bar_h + 6], fill=C_TRUNK)
    dr.text(((W - tw) / 2, 26), t1, font=f_t1, fill=(255, 255, 255, 255))
    tw2 = dr.textlength(t2, font=f_t2)
    dr.text(((W - tw2) / 2, 118), t2, font=f_t2, fill=(200, 210, 220, 255))

    # ---- 10. легенда ----
    f_lh = load_font(40)
    f_l = load_font(33)
    lh = 58
    rows = [
        ('line', C_TRUNK, 9, f"Магистральный кабель POP → сплиттеры — {s['trunk_km']:.2f} км"),
        ('line', C_DIST, 5, f"Распределительный кабель по улицам — {s['dist_km']:.2f} км"),
        ('line', C_DROP, 2, f"Дроповые линии к домохозяйствам — {s['drops_km']:.2f} км"),
        ('poly', C_HH, 0, f"Домохозяйства (нумерация) — {s['n_hh']} (официально {s['expected']})"),
        ('spl', C_SPL, 0, f"Сплиттеры GPON 1:32 — {s['splitters']} шт. (ср. {s['avg_hh_per_splitter']} ДХ)"),
        ('pop', C_POP, 0, "POP — точка приседания оператора"),
        ('text', None, 0, f"Всего оптического кабеля: {s['total_km']:.1f} км · волокон в магистрали: {s['trunk_fibers']}"),
        ('text', None, 0, f"Запас 7% на магистраль/распределение, 15 м на ввод в здание"),
    ]
    lw = 1420
    lhh = lh * len(rows) + 130
    lx, ly = W - lw - 40, bar_h + 40
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
        elif kind == 'spl':
            dr.rectangle([lx + 62, cy - 15, lx + 122, cy + 15], fill=C_SPL,
                         outline=(255, 255, 255, 255), width=3)
        elif kind == 'pop':
            dr.polygon(star_points(lx + 92, cy, 20, 9), fill=C_POP, outline=(255, 255, 255, 255))
        dr.text((lx + 180, yy + 2), text, font=f_l, fill=(235, 240, 245, 255))
        yy += lh

    # ---- 11. масштабная линейка ----
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
    # стрелка севера
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
    print(f'[{key}] сохранено {out} ({sz:.0f} МБ)', flush=True)

    prev = img.copy()
    prev.thumbnail((1600, 1600), Image.LANCZOS)
    pv = os.path.join(PREV_DIR, f'{idx:02d}_{name}_preview.jpg')
    prev.convert('RGB').save(pv, 'JPEG', quality=88)
    print(f'[{key}] превью {pv}', flush=True)


def main():
    sys.path.insert(0, BASE)
    from ftth_households import VILLAGES
    order = [v['key'] for v in VILLAGES]
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    idx0 = int(os.environ.get('IDX0', '1'))
    items = [(i + idx0, k) for i, k in enumerate(order) if not only or k in only]
    for idx, key in items:
        d = json.load(open(os.path.join(DESIGN_DIR, f'{key}_design.json')))
        render_village(d, idx)


if __name__ == '__main__':
    main()
