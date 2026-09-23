#!/usr/bin/env python3
"""Маркировка домохозяйств на космоснимках 6 СНП ВКО.

Для каждого села:
- сшивка кадра из кэша тайлов Google z18 (bbox_final из snp_bounds_final.json)
- контуры зданий OSM (scripts/households/<key>.geojson), фильтр: жилые теги + S >= 20 м2
- автосовмещение контуров со снимком: максимизация энергии градиентов вдоль линий
  контуров (двухэтапно: 1/4 и 1/2 масштаба)
- отрисовка: полупрозрачная жёлтая заливка + красный контур + порядковый номер
- плашка (название, район, счётчики, легенда) + атрибуция Google/OSM
- сохранение PNG полного разрешения + превью JPEG + реестр с номерами

Использование: python3 mark_households.py <index 0..5|all>
"""
import sys, os, json, math, time, random
sys.path.insert(0, "/home/z/my-project/scripts")
import download_and_stitch as ds
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

Image.MAX_IMAGE_PIXELS = None

HH_DIR = "/home/z/my-project/scripts/households"
OUT = "/home/z/my-project/download/snp_vko/households"
PREV = os.path.join(OUT, "previews")
os.makedirs(PREV, exist_ok=True)

Z = 18
MIN_AREA = 20.0
RES_OK = {"yes", "house", "residential", "detached", "semidetached_house",
          "bungalow", "farm", "villa", "terrace", "apartments", "dormitory",
          "cottage", "static_caravan", "mixed_use"}

FILL = (255, 215, 0, 90)
LINE = (255, 60, 30, 255)
LINE_W = 3
NUM_SIZE = 26
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def crop_origin(bbox):
    """Глобальные пиксельные координаты (Mercator z18) левого-верхнего угла кадра."""
    x0 = math.floor(ds.lon_to_tile_x(bbox["lon_lo"], Z))
    y0 = math.floor(ds.lat_to_tile_y(bbox["lat_hi"], Z))
    px_left = ds.lon_to_tile_x(bbox["lon_lo"], Z) * 256 - x0 * 256
    px_top = ds.lat_to_tile_y(bbox["lat_hi"], Z) * 256 - y0 * 256
    return x0 * 256 + round(px_left), y0 * 256 + round(px_top)


def to_global(lon, lat):
    n = 256 * (2 ** Z)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _outline_mask(polys, size):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for p in polys:
        d.line(p, fill=255, width=1, joint="curve")
    return np.asarray(m, dtype=bool)


def _search(edges, mask, center, rng):
    """max по (dy,dx) в rng вокруг center: score = mean(sub[mask]) / mean(sub)."""
    Hs, Ws = edges.shape
    pad = rng + max(abs(center[0]), abs(center[1])) + 1
    Epad = np.pad(edges, pad, mode="constant")
    best = dict(score=-1.0, dy=center[0], dx=center[1])
    for dy in range(center[0] - rng, center[0] + rng + 1):
        for dx in range(center[1] - rng, center[1] + rng + 1):
            sub = Epad[pad + dy: pad + dy + Hs, pad + dx: pad + dx + Ws]
            on = float(sub[mask].mean()) if mask.any() else 0.0
            allt = float(sub.mean()) + 1e-6
            score = on / allt
            if score > best["score"]:
                best = dict(score=score, dy=dy, dx=dx)
    return best


def align_offset(img, items):
    """Возвращает (dx, dy, score) в полноразмерных пикселях — сдвиг контуров OSM
    для наилучшего совпадения с краями зданий на снимке."""
    W, H = img.size
    cand = [it["pts"] for it in items if it["area"] >= 60.0]
    if len(cand) < 30:
        cand = [it["pts"] for it in items]
    if len(cand) > 400:
        cand = random.Random(42).sample(cand, 400)

    # этап 1: 1/4 масштаба, поиск в +-12 (=> +-48 полноразмерных px)
    s = 4
    small = img.resize((W // s, H // s), Image.BILINEAR).convert("L")
    edges = np.asarray(small.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    Hs, Ws = edges.shape
    polys_s = [[(x / s, y / s) for x, y in p] for p in cand]
    mask = _outline_mask(polys_s, (Ws, Hs))
    b1 = _search(edges, mask, (0, 0), 12)
    # этап 2: 1/2 масштаба, уточнение в +-3 (=> +-6 полноразмерных px)
    s2 = 2
    half = img.resize((W // s2, H // s2), Image.BILINEAR).convert("L")
    edges2 = np.asarray(half.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    Hh, Wh = edges2.shape
    c2 = (b1["dy"] * 2, b1["dx"] * 2)
    polys_h = [[(x / s2, y / s2) for x, y in p] for p in cand]
    mask2 = _outline_mask(polys_h, (Wh, Hh))
    b2 = _search(edges2, mask2, c2, 3)
    dx_full, dy_full = b2["dx"] * s2, b2["dy"] * s2
    if abs(dx_full) > 30 or abs(dy_full) > 30:
        print(f"  !! подозрительное смещение {dx_full},{dy_full} — обнуляю", flush=True)
        return 0, 0, b2["score"]
    return dx_full, dy_full, b2["score"]


def annotate(img, v, n_marked, n_official, mpp):
    W, H = img.size
    title_size = max(46, min(110, int(W / 85)))
    sub_size = int(title_size * 0.52)
    info_size = int(title_size * 0.50)
    leg_size = int(title_size * 0.46)
    attr_size = max(28, int(title_size * 0.38))
    f_t = ImageFont.truetype(FONT_BOLD, title_size)
    f_s = ImageFont.truetype(FONT_REG, sub_size)
    f_i = ImageFont.truetype(FONT_BOLD, info_size)
    f_l = ImageFont.truetype(FONT_REG, leg_size)
    f_a = ImageFont.truetype(FONT_REG, attr_size)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    margin = max(28, int(W * 0.015))
    pad = int(title_size * 0.55)
    gap_t = int(title_size * 0.30)
    gap_i = int(title_size * 0.42)

    title = v["name"]
    sub = f"{v['district']} · {v['okrug']} · Восточно-Казахстанская область" if v["okrug"] != "—" \
          else f"{v['district']} · Восточно-Казахстанская область"
    info = f"Домохозяйств выявлено: {n_marked}   ·   по данным учёта: {n_official} ДХ"
    leg_txt = "жилое строение (домохозяйство), № — порядковый номер"

    bt = d.textbbox((0, 0), title, font=f_t)
    bs = d.textbbox((0, 0), sub, font=f_s)
    bi = d.textbbox((0, 0), info, font=f_i)
    bl = d.textbbox((0, 0), leg_txt, font=f_l)
    sw = int(leg_size * 1.7)
    sw_gap = int(leg_size * 0.75)
    tw = max(bt[2] - bt[0], bs[2] - bs[0], bi[2] - bi[0], (bl[2] - bl[0]) + sw + sw_gap)
    th = (bt[3] - bt[1]) + gap_t + (bs[3] - bs[1]) + gap_i + (bi[3] - bi[1]) + gap_i + max(bl[3] - bl[1], sw)
    panel = [margin, margin, margin + tw + 2 * pad, margin + th + 2 * pad]
    d.rounded_rectangle(panel, radius=int(title_size * 0.38), fill=(10, 10, 10, 170))

    tx = margin + pad
    ty = margin + pad - bt[1]
    d.text((tx, ty), title, font=f_t, fill=(255, 255, 255, 255))
    d.text((tx, margin + pad + (bt[3] - bt[1]) + gap_t - bs[1]), sub, font=f_s, fill=(225, 228, 232, 255))
    y_info = margin + pad + (bt[3] - bt[1]) + gap_t + (bs[3] - bs[1]) + gap_i
    d.text((tx, y_info - bi[1]), info, font=f_i, fill=(255, 222, 89, 255))
    y_leg = y_info + (bi[3] - bi[1]) + gap_i
    d.rectangle([tx, y_leg + max(0, ((bl[3] - bl[1]) - sw) // 2), tx + sw, y_leg + max(0, ((bl[3] - bl[1]) - sw) // 2) + sw],
                fill=(255, 215, 0, 210), outline=(255, 60, 30, 255), width=max(3, title_size // 30))
    d.text((tx + sw + sw_gap, y_leg - bl[1]), leg_txt, font=f_l, fill=(225, 228, 232, 255))

    attr = f"Спутниковая съёмка: Google · зум {Z} · ≈{mpp:.2f} м/пиксель · {W}×{H} px · Контуры зданий: © OpenStreetMap (ODbL)"
    ba = d.textbbox((0, 0), attr, font=f_a)
    ax = W - margin - (ba[2] - ba[0])
    ay = H - margin - (ba[3] - ba[1])
    d.text((ax, ay), attr, font=f_a, fill=(255, 255, 255, 235),
           stroke_width=max(1, attr_size // 10), stroke_fill=(0, 0, 0, 200))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def process(v, idx):
    print(f"\n===== [{idx}] {v['name']} =====", flush=True)
    t0 = time.time()
    bbox = v["bbox_final"]
    img, mpp, stats = ds.stitch(bbox)
    if img is None:
        return None
    W, H = img.size
    print(f"  кадр: {W}x{H} px, {mpp:.3f} м/px, тайлов из кэша: {stats['cached']}", flush=True)

    with open(os.path.join(HH_DIR, f"{v['key']}.geojson"), encoding="utf-8") as f:
        fc = json.load(f)
    ox, oy = crop_origin(bbox)
    items = []
    for ft in fc["features"]:
        p = ft["properties"]
        if p["building"] not in RES_OK or p["area_m2"] < MIN_AREA:
            continue
        ring = ft["geometry"]["coordinates"][0]
        pts = []
        for lon, lat in ring:
            gx, gy = to_global(lon, lat)
            pts.append((gx - ox, gy - oy))
        cgx, cgy = to_global(p["clon"], p["clat"])
        items.append(dict(osm_id=p["osm_id"], hn=p["housenumber"], area=p["area_m2"],
                          pts=pts, cx=cgx - ox, cy=cgy - oy))
    n_total = len(fc["features"])
    print(f"  зданий в базе: {n_total}; кандидатов домохозяйств: {len(items)}", flush=True)

    dx, dy, score = align_offset(img, items)
    print(f"  совмещение: dx={dx}, dy={dy} px (score {score:.3f})", flush=True)
    for it in items:
        it["pts"] = [(x + dx, y + dy) for x, y in it["pts"]]
        it["cx"] += dx
        it["cy"] += dy

    # нумерация: север->юг, запад->восток
    items.sort(key=lambda it: (round(it["cy"] / 60.0), it["cx"]))
    for n, it in enumerate(items, 1):
        it["num"] = n

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for it in items:
        d.polygon(it["pts"], fill=FILL)
        d.line(it["pts"], fill=LINE, width=LINE_W, joint="curve")
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    del overlay

    d2 = ImageDraw.Draw(img)
    f_n = ImageFont.truetype(FONT_BOLD, NUM_SIZE)
    for it in items:
        s = str(it["num"])
        bb = d2.textbbox((0, 0), s, font=f_n, stroke_width=2)
        d2.text((it["cx"] - (bb[2] - bb[0]) / 2 - bb[0], it["cy"] - (bb[3] - bb[1]) / 2 - bb[1]),
                s, font=f_n, fill=(0, 0, 0), stroke_width=2, stroke_fill=(255, 255, 255))

    img = annotate(img, v, len(items), v["households"], mpp)

    fname = f"{idx+1:02d}_{v['name'].replace('с. ', '')}_домохозяйства.png"
    fpath = os.path.join(OUT, fname)
    t1 = time.time()
    img.save(fpath, "PNG", compress_level=6)
    size_mb = os.path.getsize(fpath) / 1e6
    print(f"  сохранён: {fname} ({size_mb:.1f} МБ, {time.time()-t1:.0f}с)", flush=True)

    prev = img.copy()
    prev.thumbnail((1600, 1600), Image.LANCZOS)
    ppath = os.path.join(PREV, fname.replace(".png", "_preview.jpg"))
    prev.convert("RGB").save(ppath, "JPEG", quality=87)
    print(f"  превью: {os.path.basename(ppath)}", flush=True)

    # реестр с номерами
    reg = {"type": "FeatureCollection", "village": v["name"], "key": v["key"],
           "offset_px": [dx, dy], "mpp": round(mpp, 4),
           "features": [dict(type="Feature",
                             properties=dict(num=it["num"], osm_id=it["osm_id"],
                                             housenumber=it["hn"], area_m2=it["area"],
                                             px_x=round(it["cx"], 1), px_y=round(it["cy"], 1)),
                             geometry=dict(type="Point", coordinates=[it["cx"], it["cy"]]))
                        for it in items]}
    # корректные геокоординаты центроида уже есть в исходном geojson — добавим из него
    src = {ft["properties"]["osm_id"]: ft["properties"] for ft in fc["features"]}
    for it, feat in zip(items, reg["features"]):
        feat["properties"]["clat"] = src[it["osm_id"]]["clat"]
        feat["properties"]["clon"] = src[it["osm_id"]]["clon"]
    with open(os.path.join(HH_DIR, f"{v['key']}_numbered.geojson"), "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False)

    print(f"  время села: {time.time()-t0:.0f}с", flush=True)
    return dict(index=idx, key=v["key"], name=v["name"], file=fname, W=W, H=H,
                mpp=round(mpp, 3), n_buildings_total=n_total, n_households=len(items),
                official=v["households"], offset_px=[dx, dy], align_score=round(score, 3),
                size_mb=round(size_mb, 1))


def main():
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    idxs = range(len(villages)) if arg == "all" else [int(arg)]

    report_path = "/home/z/my-project/scripts/households_report.json"
    report = []
    if os.path.exists(report_path) and arg != "all":
        with open(report_path, encoding="utf-8") as f:
            report = [r for r in json.load(f) if r.get("index") not in list(idxs)]
    for i in idxs:
        r = process(villages[i], i)
        if r:
            report.append(r)
            report.sort(key=lambda r: r["index"])
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nГотово.", flush=True)


if __name__ == "__main__":
    main()
