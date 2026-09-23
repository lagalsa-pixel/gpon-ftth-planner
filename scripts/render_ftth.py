#!/usr/bin/env python3
"""Отрисовка проекта FTTH (GPON) на космоснимках полного разрешения для 6 СНП ВКО.

Слои (снизу вверх): подложка Google z18 (из кэша) -> заливка домохозяйств ->
абонентская разводка (жёлтая) -> распределительный кабель (голубой) ->
магистральный кабель (красный) -> маркеры OLT/М1/зон -> номера ДХ -> плашка-легенда.

Геометрия OSM смещается на offset_px из реестра ДХ (автосовмещение Task 3).

Использование: python3 render_ftth.py <index 0..5|all>
"""
import sys, os, json, math, time
sys.path.insert(0, "/home/z/my-project/scripts")
import download_and_stitch as ds
import mark_households as mh
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

DESIGN_DIR = "/home/z/my-project/scripts/ftth_design"
HH_DIR = "/home/z/my-project/scripts/households"
OUT = "/home/z/my-project/download/snp_vko/ftth"
PREV = os.path.join(OUT, "previews")
os.makedirs(PREV, exist_ok=True)

Z = 18
RES_OK = {"yes", "house", "residential", "detached", "semidetached_house",
          "bungalow", "farm", "villa", "terrace", "apartments", "dormitory",
          "cottage", "static_caravan", "mixed_use"}
MIN_AREA = 20.0
NUM_SIZE = 22

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

FEEDER_C = (255, 59, 0, 255)
DIST_C = (0, 200, 255, 255)
DROP_C = (255, 234, 0, 215)
UNDER_C = (0, 0, 0, 140)
M1_C = (255, 149, 0, 255)
OLT_C = (230, 0, 0, 255)
ZONE_C = (0, 190, 240, 255)
HH_FILL = (255, 255, 255, 55)
HH_LINE = (255, 255, 255, 190)


def feeder_w(fibers):
    return 7 if fibers >= 24 else (6 if fibers >= 12 else 5)


def dist_w(fibers):
    return 5 if fibers >= 12 else 4


def drop_w(load):
    return 3 if load >= 8 else 2


def project_factory(bbox, dx, dy):
    ox, oy = mh.crop_origin(bbox)

    def to_px(lon, lat):
        gx, gy = mh.to_global(lon, lat)
        return (gx - ox + dx, gy - oy + dy)

    return to_px


def annotate_ftth(img, v, design, mpp):
    W, H = img.size
    s = design["stats"]
    title_size = max(44, min(104, int(W / 85)))
    sub_size = int(title_size * 0.50)
    text_size = int(title_size * 0.48)
    leg_size = int(title_size * 0.44)
    attr_size = max(26, int(title_size * 0.36))
    f_t = ImageFont.truetype(FONT_BOLD, title_size)
    f_s = ImageFont.truetype(FONT_REG, sub_size)
    f_x = ImageFont.truetype(FONT_BOLD, text_size)
    f_l = ImageFont.truetype(FONT_REG, leg_size)
    f_a = ImageFont.truetype(FONT_REG, attr_size)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    margin = max(28, int(W * 0.015))
    pad = int(title_size * 0.55)
    gap_t = int(title_size * 0.30)
    gap_i = int(title_size * 0.40)
    gap_l = int(title_size * 0.34)

    sub = f"{v['district']} · {v['okrug']} · Восточно-Казахстанская область" if v["okrug"] != "—" \
        else f"{v['district']} · Восточно-Казахстанская область"

    l1 = "Проект FTTH · GPON, каскад сплиттеров 1×4 + 1×16 (1:64)"
    l2 = (f"Абонентов (ДХ): {s['n_households']} · зон ODN: {s['n_zones']} · "
          f"PON-портов: {s['n_groups']} · бюджет потерь {s['loss_db']:.1f}/{s['budget_db']:.0f} дБ")
    l3 = (f"Кабель: магистраль {s['feeder_km']:.1f} км · распределение {s['dist_km']:.1f} км · "
          f"абонентская разводка {s['drop_cable_km']:.1f} км")
    l4 = "Маршруты прокладки — по фактическим улицам (OSM), подвеска на существующих опорах"

    legends = [
        ("line", FEEDER_C, feeder_w(24), "магистральный кабель: OLT → муфты М1 (сплиттер 1×4)"),
        ("line", DIST_C, dist_w(8), "распределительный кабель: М1 → боксы зон (сплиттер 1×16)"),
        ("line", DROP_C, 2, "абонентская разводка по улицам и вводы в дома"),
        ("sq", OLT_C, "OLT — узел доступа (станция оператора)"),
        ("sq", M1_C, "М1 — муфта со сплиттером 1×4 (№ PON-порта)"),
        ("circ", ZONE_C, "бокс зоны со сплиттером 1×16, до 12 ДХ (№ зоны)"),
        ("poly", "домохозяйство — абонент (порядковый №)"),
    ]

    def tw(txt, font):
        b = d.textbbox((0, 0), txt, font=font)
        return b[2] - b[0], b[3] - b[1], b[1]

    sw_line = leg_size * 4
    sw_gap = int(leg_size * 0.8)
    sw_sq = int(leg_size * 1.05)
    rows = [("title", v["name"])]
    rows.append(("sub", sub))
    rows.append(("gap",))
    for t in (l1, l2, l3):
        rows.append(("text", t))
    rows.append(("note", l4))
    rows.append(("gap",))
    rows.append(("gap",))
    for lg in legends:
        rows.append(("leg",) + lg)

    widths, heights = [], []
    for r in rows:
        kind = r[0]
        if kind == "title":
            w, h, _ = tw(r[1], f_t); heights.append(h); widths.append(w)
        elif kind == "sub":
            w, h, _ = tw(r[1], f_s); heights.append(h); widths.append(w)
        elif kind in ("text", "note"):
            w, h, _ = tw(r[1], f_x if kind == "text" else f_l); heights.append(h); widths.append(w)
        elif kind == "gap":
            heights.append(gap_i); widths.append(0)
        else:  # leg
            txt = r[-1]
            w, h, _ = tw(txt, f_l)
            extra = sw_line + sw_gap if r[1] == "line" else (sw_sq + sw_gap if r[1] in ("sq", "circ", "poly") else 0)
            heights.append(max(h, sw_sq)); widths.append(w + extra)

    panel_w = max(widths) + 2 * pad
    panel_h = sum(heights) + 2 * pad
    panel = [margin, margin, margin + panel_w, margin + panel_h]
    d.rounded_rectangle(panel, radius=int(title_size * 0.38), fill=(10, 12, 14, 185))

    y = margin + pad
    x0 = margin + pad
    for r, rh in zip(rows, heights):
        kind = r[0]
        if kind == "gap":
            y += rh
            continue
        if kind == "title":
            _, _, b1 = tw(r[1], f_t)
            d.text((x0, y - b1), r[1], font=f_t, fill=(255, 255, 255, 255))
        elif kind == "sub":
            _, _, b1 = tw(r[1], f_s)
            d.text((x0, y - b1), r[1], font=f_s, fill=(225, 228, 232, 255))
        elif kind == "text":
            _, _, b1 = tw(r[1], f_x)
            d.text((x0, y - b1), r[1], font=f_x, fill=(255, 222, 89, 255))
        elif kind == "note":
            _, _, b1 = tw(r[1], f_l)
            d.text((x0, y - b1), r[1], font=f_l, fill=(178, 190, 200, 255))
        elif kind == "leg":
            lkind = r[1]
            txt = r[-1]
            _, h, b1 = tw(txt, f_l)
            cy = y + max(h, sw_sq) / 2
            if lkind == "line":
                color, wpx = r[2], r[3]
                d.line([x0, cy, x0 + sw_line, cy], fill=(0, 0, 0, 150), width=wpx + 3)
                d.line([x0, cy, x0 + sw_line, cy], fill=color, width=wpx)
                tx = x0 + sw_line + sw_gap
            elif lkind in ("sq", "circ"):
                color = r[2]
                half = sw_sq / 2
                if lkind == "sq":
                    d.rectangle([x0, cy - half, x0 + sw_sq, cy + half], fill=color,
                                outline=(255, 255, 255, 230), width=max(2, leg_size // 16))
                else:
                    d.ellipse([x0, cy - half, x0 + sw_sq, cy + half], fill=color,
                              outline=(255, 255, 255, 230), width=max(2, leg_size // 16))
                tx = x0 + sw_sq + sw_gap
            else:  # poly
                d.rectangle([x0, y + max(0, (h - sw_sq) // 2), x0 + sw_sq, y + max(0, (h - sw_sq) // 2) + sw_sq],
                            fill=HH_FILL, outline=HH_LINE, width=max(2, leg_size // 18))
                tx = x0 + sw_sq + sw_gap
            d.text((tx, y - b1), txt, font=f_l, fill=(225, 228, 232, 255))
        y += rh

    attr = (f"Спутниковая съёмка: Google · зум {Z} · ≈{mpp:.2f} м/пиксель · {W}×{H} px · "
            f"Улицы/здания: © OpenStreetMap (ODbL) · Схема FTTH — проектная, требует уточнения по месту")
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
    with open(os.path.join(DESIGN_DIR, f"{v['key']}.json"), encoding="utf-8") as f:
        design = json.load(f)
    with open(os.path.join(HH_DIR, f"{v['key']}_numbered.geojson"), encoding="utf-8") as f:
        numbered = json.load(f)
    with open(os.path.join(HH_DIR, f"{v['key']}.geojson"), encoding="utf-8") as f:
        orig = json.load(f)
    dx, dy = numbered["offset_px"]
    to_px = project_factory(bbox, dx, dy)

    img, mpp, stats = ds.stitch(bbox)
    if img is None:
        return None
    W, H = img.size
    print(f"  кадр: {W}x{H} px, {mpp:.3f} м/px, из кэша: {stats['cached']} тайлов", flush=True)

    # домохозяйства: полигоны + номера
    src = {ft["properties"]["osm_id"]: ft for ft in orig["features"]}
    items = []
    for ft in numbered["features"]:
        p = ft["properties"]
        o = src.get(p["osm_id"])
        if o is None:
            continue
        ring = o["geometry"]["coordinates"][0]
        pts = [to_px(lon, lat) for lon, lat in ring]
        items.append(dict(num=p["num"], pts=pts, cx=p["px_x"], cy=p["px_y"]))
    print(f"  домохозяйств к отрисовке: {len(items)}", flush=True)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # 1) заливка зданий
    for it in items:
        d.polygon(it["pts"], fill=HH_FILL)
        d.line(it["pts"], fill=HH_LINE, width=2, joint="curve")

    # 2) абонентская разводка: уличные рёбра + вводные сегменты
    for c in design["cables"]["drop"]:
        (x1, y1), (x2, y2) = [to_px(lon, lat) for lon, lat in c["pts"]]
        d.line([x1, y1, x2, y2], fill=DROP_C, width=drop_w(c["load"]))
    for num, q, hp in design["cables"]["entries"]:
        (x1, y1) = to_px(q[0], q[1])
        (x2, y2) = to_px(hp[0], hp[1])
        d.line([x1, y1, x2, y2], fill=DROP_C, width=2)

    # 3) распределительный кабель (с тёмной подложкой для контраста)
    for c in design["cables"]["dist"]:
        (x1, y1), (x2, y2) = [to_px(lon, lat) for lon, lat in c["pts"]]
        wpx = dist_w(c["fibers"])
        d.line([x1, y1, x2, y2], fill=UNDER_C, width=wpx + 3)
    for c in design["cables"]["dist"]:
        (x1, y1), (x2, y2) = [to_px(lon, lat) for lon, lat in c["pts"]]
        wpx = dist_w(c["fibers"])
        d.line([x1, y1, x2, y2], fill=DIST_C, width=wpx)

    # 4) магистральный кабель
    for c in design["cables"]["feeder"]:
        (x1, y1), (x2, y2) = [to_px(lon, lat) for lon, lat in c["pts"]]
        wpx = feeder_w(c["fibers"])
        d.line([x1, y1, x2, y2], fill=UNDER_C, width=wpx + 4)
    for c in design["cables"]["feeder"]:
        (x1, y1), (x2, y2) = [to_px(lon, lat) for lon, lat in c["pts"]]
        wpx = feeder_w(c["fibers"])
        d.line([x1, y1, x2, y2], fill=FEEDER_C, width=wpx)

    # 5) маркеры: OLT, М1, зоны
    f_m = ImageFont.truetype(FONT_BOLD, 15)
    f_z = ImageFont.truetype(FONT_BOLD, 13)
    f_o = ImageFont.truetype(FONT_BOLD, 24)
    for z in design["zones"]:
        x, y = to_px(z["lon"], z["lat"])
        r = 11
        d.ellipse([x - r, y - r, x + r, y + r], fill=ZONE_C,
                  outline=(255, 255, 255, 240), width=2)
        s = str(z["id"])
        bb = d.textbbox((0, 0), s, font=f_z)
        d.text((x - (bb[2] - bb[0]) / 2 - bb[0], y - (bb[3] - bb[1]) / 2 - bb[1]),
               s, font=f_z, fill=(0, 25, 40, 255))
    for g in design["groups"]:
        x, y = to_px(g["lon"], g["lat"])
        h = 13
        d.rectangle([x - h, y - h, x + h, y + h], fill=M1_C,
                    outline=(255, 255, 255, 240), width=3)
        s = f"M{g['id']:02d}"
        bb = d.textbbox((0, 0), s, font=f_m)
        d.text((x + h + 4, y - (bb[3] - bb[1]) / 2 - bb[1]), s, font=f_m,
               fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 220))
    ox_, oy_ = to_px(design["olt"]["lon"], design["olt"]["lat"])
    h = 16
    d.rectangle([ox_ - h, oy_ - h, ox_ + h, oy_ + h], fill=OLT_C,
                outline=(255, 255, 255, 255), width=4)
    bb = d.textbbox((0, 0), "OLT", font=f_o)
    d.text((ox_ - (bb[2] - bb[0]) / 2 - bb[0], oy_ + h + 6), "OLT", font=f_o,
           fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 230))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    del overlay

    # 6) номера абонентов
    d2 = ImageDraw.Draw(img)
    f_n = ImageFont.truetype(FONT_BOLD, NUM_SIZE)
    for it in items:
        s = str(it["num"])
        bb = d2.textbbox((0, 0), s, font=f_n, stroke_width=2)
        d2.text((it["cx"] - (bb[2] - bb[0]) / 2 - bb[0], it["cy"] - (bb[3] - bb[1]) / 2 - bb[1]),
                s, font=f_n, fill=(0, 0, 0), stroke_width=2, stroke_fill=(255, 255, 255))

    # 7) плашка
    img = annotate_ftth(img, v, design, mpp)

    fname = f"{idx+1:02d}_{v['name'].replace('с. ', '')}_FTTH_z{Z}.png"
    fpath = os.path.join(OUT, fname)
    t1 = time.time()
    img.save(fpath, "PNG", compress_level=6)
    size_mb = os.path.getsize(fpath) / 1e6
    print(f"  сохранён: {fname} ({size_mb:.1f} МБ, {time.time()-t1:.0f}с)", flush=True)

    prev = img.copy()
    prev.thumbnail((1600, 1600), Image.LANCZOS)
    ppath = os.path.join(PREV, fname.replace(".png", "_preview.jpg"))
    prev.convert("RGB").save(ppath, "JPEG", quality=87)
    print(f"  превью: previews/{os.path.basename(ppath)}; время села {time.time()-t0:.0f}с", flush=True)
    return dict(index=idx, key=v["key"], name=v["name"], file=fname, W=W, H=H,
                mpp=round(mpp, 3), size_mb=round(size_mb, 1))


def main():
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    idxs = range(len(villages)) if arg == "all" else [int(arg)]
    for i in idxs:
        dp = os.path.join(DESIGN_DIR, f"{villages[i]['key']}.json")
        if not os.path.exists(dp):
            print(f"[{i}] {villages[i]['name']}: нет проекта ({dp}) — пропуск", flush=True)
            continue
        process(villages[i], i)
    print("\nГотово.", flush=True)


if __name__ == "__main__":
    main()
