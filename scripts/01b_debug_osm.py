# -*- coding: utf-8 -*-
"""Отладочная визуализация OSM-данных: дороги, здания, bbox застройки, центр камеры."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, WORK
from PIL import Image, ImageDraw, ImageFont

Z = 14  # обзорный масштаб отладки

def geo_to_px(lat, lon, lat_min, lon_min, mpp):
    x = (lon - lon_min) * 111320 * math.cos(math.radians(lat)) / mpp
    y = (lat - lat_min) * 111320 / mpp
    return x, y

for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    bbox = d['bbox']
    # расширяем канву на 20% вокруг bbox
    w_m = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians(v['lat']))
    h_m = (bbox[3] - bbox[1]) * 111320
    pad = max(w_m, h_m) * 0.25
    lat_min = bbox[1] - pad / 111320
    lon_min = bbox[0] - pad / (111320 * math.cos(math.radians(v['lat'])))
    W = int((w_m + 2 * pad) / 2); H = int((h_m + 2 * pad) / 2)
    mpp = (w_m + 2 * pad) / 1400.0
    W, H = 1400, max(400, int((h_m + 2 * pad) / mpp))
    img = Image.new('RGB', (W, H), (18, 22, 28))
    dr = ImageDraw.Draw(img)
    for r in d['roads']:
        pts = [geo_to_px(la, lo, lat_min, lon_min, mpp) for la, lo in r['pts']]
        if len(pts) >= 2:
            col = (120, 130, 140) if r['hw'] in ('residential', 'living_street', 'service', 'unclassified') else (70, 80, 95)
            dr.line(pts, fill=col, width=2)
    for b in d['buildings']:
        pts = [geo_to_px(la, lo, lat_min, lon_min, mpp) for la, lo in b['poly']]
        if len(pts) >= 3:
            dr.polygon(pts, fill=(210, 160, 90))
    x0, y0 = geo_to_px(bbox[1], bbox[0], lat_min, lon_min, mpp)
    x1, y1 = geo_to_px(bbox[3], bbox[2], lat_min, lon_min, mpp)
    dr.rectangle([x0, y0, x1, y1], outline=(0, 255, 120), width=3)
    cx, cy = geo_to_px(v['lat'], v['lon'], lat_min, lon_min, mpp)
    dr.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=(255, 80, 80), width=3)
    dr.text((10, 8), f"{v['name']}: {len(d['roads'])} дор, {len(d['buildings'])} зд, bbox {bbox[0]:.4f},{bbox[1]:.4f},{bbox[2]:.4f},{bbox[3]:.4f}", fill=(255, 255, 255))
    img.save(f'{WORK}/debug_{key}.png')
    print(f"{v['name']}: debug_{key}.png  центр=({v['lat']:.5f},{v['lon']:.5f})")
