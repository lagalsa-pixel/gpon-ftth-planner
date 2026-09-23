#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Расширение съёмки Алтайского на север: новый bbox Y[-1750..3250], X[-1500..1500].
Докачивает тайлы в общий кэш, обновляет geo, пересобирает PNG."""
import json, math, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import cv2

WORK = '/home/z/my-project/work'
ZOOM = 18
NAME = 'Алтайский'

snp = [s for s in json.load(open(f'{WORK}/snp_data.json')) if s['name'] == NAME][0]
lat, lon = snp['lat'], snp['lon']

# новый охват
Y_MIN, Y_MAX = -1750, 3250
X_MIN, X_MAX = -1500, 1500
dlat_n = Y_MAX / 111320.0
dlat_s = -Y_MIN / 111320.0
mx = 111320 * math.cos(math.radians(lat))
lon_min, lon_max = lon + X_MIN / mx, lon + X_MAX / mx
lat_min, lat_max = lat - dlat_s, lat + dlat_n

def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    lr = math.radians(lat)
    yt = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n
    return xt, yt

def tile_to_latlon(xt, yt, z):
    n = 2 ** z
    lon_ = xt / n * 360.0 - 180.0
    lat_ = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))
    return lat_, lon_

xt0, yt0 = latlon_to_tile(lat_max, lon_min, ZOOM)
xt1, yt1 = latlon_to_tile(lat_min, lon_max, ZOOM)
tx0, ty0 = int(math.floor(xt0)), int(math.floor(yt0))
tx1, ty1 = int(math.floor(xt1)), int(math.floor(yt1))
nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
print(f"Новый охват: {nx}x{ny} тайлов, "
      f"{(X_MAX-X_MIN)/1000:.1f} x {(Y_MAX-Y_MIN)/1000:.1f} км")

cache = f'{WORK}/tiles/{NAME}'
os.makedirs(cache, exist_ok=True)

SUB = [0]
def tile_url(z, x, y):
    s = SUB[0]; SUB[0] = (SUB[0] + 1) % 4
    return f"https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"

def fetch(url, dest, tries=4):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.google.com/"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if len(data) > 100:
                with open(dest, 'wb') as f:
                    f.write(data)
                return True
        except Exception:
            time.sleep(1 + a)
    return False

jobs = [(tile_url(ZOOM, tx, ty), f'{cache}/{ZOOM}_{tx}_{ty}.jpg')
        for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
ok = 0
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(fetch, u, d): d for u, d in jobs}
    for i, fut in enumerate(as_completed(futs)):
        if fut.result():
            ok += 1
        if (i + 1) % 300 == 0:
            print(f"  {i+1}/{len(jobs)} ({ok})", flush=True)
print(f"тайлы: {ok}/{len(jobs)}")

px_x0 = int((xt0 - tx0) * 256); px_y0 = int((yt0 - ty0) * 256)
W = nx * 256 - px_x0 - int((tx1 + 1 - xt1) * 256)
H = ny * 256 - px_y0 - int((ty1 + 1 - yt1) * 256)
lat_tl, lon_tl = tile_to_latlon(tx0, ty0, ZOOM)
lat_br, lon_br = tile_to_latlon(tx0 + W / 256.0, ty0 + H / 256.0, ZOOM)

geo = {'name': NAME, 'zoom': ZOOM, 'tx0': tx0, 'ty0': ty0,
       'px_x0': px_x0, 'px_y0': px_y0, 'W': W, 'H': H,
       'lat_max': lat_tl, 'lon_min': lon_tl, 'lat_min': lat_br, 'lon_max': lon_br,
       'm_per_px': 156543.03392 * math.cos(math.radians(lat)) / 2 ** ZOOM}
with open(f'{WORK}/geo/{NAME}.json', 'w', encoding='utf-8') as f:
    json.dump(geo, f, ensure_ascii=False, indent=1)
print(f"гео обновлено: {W}x{H}px, {geo['m_per_px']:.3f} м/px")
print(f"bbox: lat[{lat_br:.5f}..{lat_tl:.5f}] lon[{lon_tl:.5f}..{lon_br:.5f}]")
