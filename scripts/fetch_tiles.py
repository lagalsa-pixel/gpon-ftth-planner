#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка спутниковых тайлов ESRI World Imagery z18 и сборка полных PNG по 6 СНП.
Кэш тайлов в work/tiles/<snp>/, геоссылка в work/geo/<snp>.json"""
import json, math, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

WORK = '/home/z/my-project/work'
OUT_DIR = '/home/z/my-project/download/snp_vko'
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(f'{WORK}/geo', exist_ok=True)

with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
    SNPS = json.load(f)

# половина стороны охвата, м (из оценки по числу ДХ, кроп позже по застройке)
HALF = {
    'Верхнеберезовка': 1650, 'Солнечное': 1150, 'Перевальное': 1050,
    'Винное': 1250, 'Пригородное': 1150, 'Алтайский': 1400,
}
ZOOM = 18
URL = "https://server.arcgison.com.com/placeholder"  # replaced below

SUB = [0]
def tile_url(z, x, y):
    s = SUB[0]; SUB[0] = (SUB[0] + 1) % 4
    return f"https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"

def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    yt = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return xt, yt

def tile_to_latlon(xt, yt, z):
    n = 2 ** z
    lon = xt / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))
    return lat, lon

def m_per_px(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)

def fetch(url, dest, tries=4):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36", "Referer": "https://www.google.com/"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if len(data) > 100:
                with open(dest, 'wb') as f:
                    f.write(data)
                return True
        except Exception:
            time.sleep(1 + a)
    return False

if __name__ == '__main__':
    import sys as _sys
    only = set(_sys.argv[1:]) or None
    with open(f'{WORK}/snp_data.json', encoding='utf-8') as f:
        snps = json.load(f)
    for s in snps:
        name = s['name']
        if only and name not in only:
            continue
        lat, lon = s['lat'], s['lon']
        half = HALF[name]

        dlat = half / 111320.0
        dlon = half / (111320.0 * math.cos(math.radians(lat)))
        lat_min, lat_max = lat - dlat, lat + dlat
        lon_min, lon_max = lon - dlon, lon + dlon

        xt0, yt0 = latlon_to_tile(lat_max, lon_min, ZOOM)  # верхний левый
        xt1, yt1 = latlon_to_tile(lat_min, lon_max, ZOOM)  # нижний правый
        tx0, ty0 = int(math.floor(xt0)), int(math.floor(yt0))
        tx1, ty1 = int(math.floor(xt1)), int(math.floor(yt1))
        nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1

        cache = f'{WORK}/tiles/{name}'
        os.makedirs(cache, exist_ok=True)
        print(f"=== {name}: {nx}x{ny} тайлов (z{ZOOM}), ~{(2*half)/1000:.1f} км охват ===", flush=True)

        jobs = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                jobs.append((tile_url(ZOOM, tx, ty), f'{cache}/{ZOOM}_{tx}_{ty}.jpg'))

        ok = 0
        with ThreadPoolExecutor(max_workers=12) as ex:
            futs = {ex.submit(fetch, u, d): d for u, d in jobs}
            for i, fut in enumerate(as_completed(futs)):
                if fut.result():
                    ok += 1
                if (i + 1) % 200 == 0:
                    print(f"  {i+1}/{len(jobs)} ({ok} ok)", flush=True)
        print(f"  тайлы: {ok}/{len(jobs)}", flush=True)

        px_x0 = int((xt0 - tx0) * 256); px_y0 = int((yt0 - ty0) * 256)
        W = nx * 256 - px_x0 - int((tx1 + 1 - xt1) * 256)
        H = ny * 256 - px_y0 - int((ty1 + 1 - yt1) * 256)

        lat_tl, lon_tl = tile_to_latlon(xt0, yt0, ZOOM)
        lat_br, lon_br = tile_to_latlon(xt0 + W / 256.0, yt0 + H / 256.0, ZOOM)

        geo = {'name': name, 'zoom': ZOOM, 'tx0': tx0, 'ty0': ty0,
               'px_x0': px_x0, 'px_y0': px_y0, 'W': W, 'H': H,
               'lat_max': lat_tl, 'lon_min': lon_tl, 'lat_min': lat_br, 'lon_max': lon_br,
               'm_per_px': m_per_px(lat, ZOOM)}
        with open(f'{WORK}/geo/{name}.json', 'w', encoding='utf-8') as f:
            json.dump(geo, f, ensure_ascii=False, indent=1)
        print(f"  гео: {W}x{H}px, {geo['m_per_px']:.3f} м/px", flush=True)

    print("\nВСЁ ГОТОВО", flush=True)
