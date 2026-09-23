#!/usr/bin/env python3
"""Скачивание тайлов Google Satellite (z18), сшивка в PNG максимального разрешения
для каждого села, обрезка по bbox застройки+300м, аннотирование названия.

Использование: python3 download_and_stitch.py <index 0..5|all>
"""
import requests, io, json, math, os, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont
import numpy as np

Image.MAX_IMAGE_PIXELS = None

ZOOM = 18
TILE = 256
CACHE = "/home/z/my-project/scripts/tiles_cache/z18"
OUTDIR = "/home/z/my-project/download/snp_vko"
PREVIEW_DIR = os.path.join(OUTDIR, "previews")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
      "Referer": "https://www.google.com/maps"}

local = threading.local()
def get_session():
    if not hasattr(local, "s"):
        local.s = requests.Session()
        local.s.headers.update(UA)
    return local.s

def lon_to_tile_x(lon, z):
    return (lon + 180.0) / 360.0 * (2 ** z)

def lat_to_tile_y(lat, z):
    lat_r = math.radians(lat)
    return (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * (2 ** z)

def fetch_google_tile(z, x, y, tries=4):
    """Скачивает тайл с ротацией поддоменов и ретраями. Возвращает bytes или None."""
    for attempt in range(tries):
        sub = (x + y + attempt) % 4
        url = f"https://mt{sub}.googleapis.com/vt?lyrs=s&x={x}&y={y}&z={z}"
        try:
            r = get_session().get(url, timeout=25)
            if r.status_code == 200 and len(r.content) > 500:
                # валидация: открывается, 256x256, не однотонная заглушка
                img = Image.open(io.BytesIO(r.content))
                if img.size == (256, 256):
                    arr = np.array(img.convert("RGB"))
                    if arr.std() > 2.0:
                        return r.content
                    else:
                        print(f"    заглушка (std={arr.std():.1f}) x={x} y={y}", flush=True)
                        return None
            elif r.status_code in (403, 429, 503):
                wait = 15 + attempt * 20 + random.uniform(0, 5)
                print(f"    throttle {r.status_code}, пауза {wait:.0f}с (x={x},y={y})", flush=True)
                time.sleep(wait)
            else:
                print(f"    HTTP {r.status_code} x={x} y={y} (попытка {attempt+1})", flush=True)
                time.sleep(2 + attempt * 3)
        except Exception as e:
            print(f"    {type(e).__name__} x={x} y={y} (попытка {attempt+1})", flush=True)
            time.sleep(2 + attempt * 3)
    return None

def download_tiles(coords):
    """coords: список (x,y). Скачивает с кэшем на диск. Возвращает dict[(x,y)] = bytes + счётчики."""
    todo, result = [], {}
    cached = 0
    for (x, y) in coords:
        p = os.path.join(CACHE, f"{x}_{y}.jpg")
        if os.path.exists(p) and os.path.getsize(p) > 500:
            with open(p, "rb") as f:
                result[(x, y)] = f.read()
            cached += 1
        else:
            todo.append((x, y))
    downloaded, failed = 0, []
    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(fetch_google_tile, ZOOM, x, y): (x, y) for (x, y) in todo}
            for i, fut in enumerate(as_completed(futs)):
                x, y = futs[fut]
                try:
                    content = fut.result()
                except Exception:
                    content = None
                if content:
                    result[(x, y)] = content
                    tp = os.path.join(CACHE, f"{x}_{y}.jpg")
                    with open(tp, "wb") as f:
                        f.write(content)
                    downloaded += 1
                else:
                    failed.append((x, y))
                if (i + 1) % 100 == 0:
                    print(f"    прогресс: {i+1}/{len(todo)} (ошибок: {len(failed)})", flush=True)
    return result, cached, downloaded, failed

def stitch(bbox):
    lat_lo, lat_hi = bbox["lat_lo"], bbox["lat_hi"]
    lon_lo, lon_hi = bbox["lon_lo"], bbox["lon_hi"]
    x0 = math.floor(lon_to_tile_x(lon_lo, ZOOM))
    x1 = math.floor(lon_to_tile_x(lon_hi, ZOOM))
    y0 = math.floor(lat_to_tile_y(lat_hi, ZOOM))
    y1 = math.floor(lat_to_tile_y(lat_lo, ZOOM))
    coords = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    print(f"  тайлов: {len(coords)} (сетка {x1-x0+1}x{y1-y0+1})", flush=True)

    tiles, cached, downloaded, failed = download_tiles(coords)
    print(f"  скачано: {downloaded}, из кэша: {cached}, ошибок: {len(failed)}", flush=True)
    if len(failed) / max(1, len(coords)) > 0.03:
        print("  !! >3% ошибок — стоп, повторите запуск для дозагрузки из кэша", flush=True)
        return None, None, None

    W = (x1 - x0 + 1) * TILE
    H = (y1 - y0 + 1) * TILE
    canvas = Image.new("RGB", (W, H), (120, 120, 120))
    for (x, y), content in tiles.items():
        img = Image.open(io.BytesIO(content)).convert("RGB")
        canvas.paste(img, ((x - x0) * TILE, (y - y0) * TILE))
    for (x, y) in failed:
        d = ImageDraw.Draw(canvas)
        d.rectangle([(x-x0)*TILE, (y-y0)*TILE, (x-x0)*TILE+TILE-1, (y-y0)*TILE+TILE-1], fill=(210, 210, 210))

    # точная обрезка по bbox
    px_left = lon_to_tile_x(lon_lo, ZOOM) * TILE - x0 * TILE
    px_right = lon_to_tile_x(lon_hi, ZOOM) * TILE - x0 * TILE
    px_top = lat_to_tile_y(lat_hi, ZOOM) * TILE - y0 * TILE
    px_bottom = lat_to_tile_y(lat_lo, ZOOM) * TILE - y0 * TILE
    crop = canvas.crop((round(px_left), round(px_top), round(px_right), round(px_bottom)))
    mpp = 40075016.686 * math.cos(math.radians((lat_lo + lat_hi) / 2)) / (TILE * 2 ** ZOOM)
    return crop, mpp, {"tiles": len(coords), "cached": cached, "downloaded": downloaded, "failed": len(failed)}

def annotate(img, title, subtitle, attribution):
    W, H = img.size
    title_size = max(46, min(110, int(W / 85)))
    sub_size = int(title_size * 0.52)
    attr_size = max(28, int(title_size * 0.38))
    font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", title_size)
    font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", sub_size)
    font_a = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", attr_size)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    margin = max(28, int(W * 0.015))
    pad = int(title_size * 0.55)
    gap_t = int(title_size * 0.32)

    bbox_t = d.textbbox((0, 0), title, font=font_t)
    bbox_s = d.textbbox((0, 0), subtitle, font=font_s)
    tw = max(bbox_t[2] - bbox_t[0], bbox_s[2] - bbox_s[0])
    th = (bbox_t[3] - bbox_t[1]) + gap_t + (bbox_s[3] - bbox_s[1])
    panel = [margin, margin, margin + tw + 2 * pad, margin + th + 2 * pad]
    d.rounded_rectangle(panel, radius=int(title_size * 0.38), fill=(10, 10, 10, 165))
    tx = margin + pad
    ty = margin + pad - bbox_t[1]
    d.text((tx, ty), title, font=font_t, fill=(255, 255, 255, 255))
    d.text((tx, margin + pad + (bbox_t[3] - bbox_t[1]) + gap_t), subtitle, font=font_s, fill=(225, 228, 232, 255))

    # атрибуция — правый нижний угол, с обводкой
    bbox_a = d.textbbox((0, 0), attribution, font=font_a)
    aw, ah = bbox_a[2] - bbox_a[0], bbox_a[3] - bbox_a[1]
    ax = W - margin - aw
    ay = H - margin - ah
    d.text((ax, ay), attribution, font=font_a, fill=(255, 255, 255, 235),
           stroke_width=max(1, attr_size // 10), stroke_fill=(0, 0, 0, 200))
    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return out

def main():
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    idxs = range(len(villages)) if arg == "all" else [int(arg)]

    report = []
    for i in idxs:
        v = villages[i]
        print(f"\n===== [{i}] {v['name']} =====", flush=True)
        bbox = v["bbox_final"]
        if bbox is None:
            print("  нет bbox — пропуск", flush=True)
            continue
        t0 = time.time()
        img, mpp, stats = stitch(bbox)
        if img is None:
            continue
        W, H = img.size
        print(f"  размер: {W} x {H} px ({W*H/1e6:.1f} Мп), {mpp:.3f} м/px, "
              f"охват ~{W*mpp:.0f} x {H*mpp:.0f} м, время {time.time()-t0:.0f}с", flush=True)

        sub = f"{v['district']} · {v['okrug']} · Восточно-Казахстанская область" if v["okrug"] != "—" \
              else f"{v['district']} · Восточно-Казахстанская область"
        attr = f"Спутниковая съёмка: Google · зум {ZOOM} · ≈{mpp:.2f} м/пиксель · {W}×{H} px"
        img = annotate(img, v["name"], sub, attr)

        fname = f"{i+1:02d}_{v['name'].replace('с. ', '')}_Google_z{ZOOM}.png"
        fpath = os.path.join(OUTDIR, fname)
        t1 = time.time()
        img.save(fpath, "PNG", compress_level=6)
        size_mb = os.path.getsize(fpath) / 1e6
        print(f"  сохранён: {fname} ({size_mb:.1f} МБ, сжатие {time.time()-t1:.0f}с)", flush=True)

        prev = img.copy()
        prev.thumbnail((1600, 1600), Image.LANCZOS)
        ppath = os.path.join(PREVIEW_DIR, fname.replace(".png", "_preview.jpg"))
        prev.convert("RGB").save(ppath, "JPEG", quality=87)
        print(f"  превью: previews/{os.path.basename(ppath)}", flush=True)

        report.append(dict(index=i, name=v["name"], file=fname, W=W, H=H, mpp=round(mpp, 3),
                           size_mb=round(size_mb, 1), **stats))
        with open("/home/z/my-project/scripts/stitch_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nГотово.", flush=True)

if __name__ == "__main__":
    main()
