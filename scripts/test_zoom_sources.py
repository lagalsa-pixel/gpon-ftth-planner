#!/usr/bin/env python3
"""Проверка максимального зума ESRI для всех 6 СНП + альтернативные источники (Yandex) + зеркала Overpass."""
import requests, hashlib, io, math
from PIL import Image
import numpy as np

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SatelliteImageryFetcher/1.0", "Referer": "https://www.arcgis.com/"}

VILLAGES = [
    ("Верхнеберезовка", 50.28420545, 82.209512),
    ("Солнечное", 50.0517755, 82.71438134),
    ("Перевальное", 50.24139084, 82.28314297),
    ("Винное", 50.05844487, 82.82687999),
    ("Пригородное", 50.321981, 83.52094976),
    ("Алтайский", 50.24399825, 82.36103064),
]

def deg2tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y

NODATA_MD5 = set()

def fetch_esri(z, x, y):
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    r = requests.get(url, headers=UA, timeout=30)
    return r.status_code, r.content

def fetch_yandex(z, x, y):
    url = f"https://sat01.maps.yandex.net/?l=sat&x={x}&y={y}&z={z}"
    r = requests.get(url, headers={"User-Agent": UA["User-Agent"]}, timeout=30)
    return r.status_code, r.content

def tile_stats(content):
    try:
        img = Image.open(io.BytesIO(content))
        arr = np.array(img.convert("RGB")).astype(float)
        return img.size, len(content), arr.std()
    except Exception as e:
        return None, 0, -1

print("=== ESRI World Imagery: зум-тест по 6 СНП ===")
for name, lat, lon in VILLAGES:
    row = f"  {name}: "
    for z in [17, 18, 19]:
        x, y = deg2tile(lat, lon, z)
        code, content = fetch_esri(z, int(x), int(y))
        size, nb, std = tile_stats(content)
        md5 = hashlib.md5(content).hexdigest() if code == 200 else f"HTTP{code}"
        is_nodata = (size == (256, 256) and nb < 4000 and std < 10)
        row += f"z{z}={'DATA' if not is_nodata else 'нет'}({nb}b,std={std:.0f}) "
    print(row)

print("\n=== Yandex sat: тест z18/z19 Верхнеберезовка и Пригородное ===")
for name, lat, lon in [VILLAGES[0], VILLAGES[4]]:
    for z in [18, 19]:
        x, y = deg2tile(lat, lon, z)
        code, content = fetch_yandex(z, int(x), int(y))
        size, nb, std = tile_stats(content)
        print(f"  {name} z{z}: HTTP {code}, size={size}, bytes={nb}, std={std:.1f}")

print("\n=== Зеркала Overpass ===")
q = """[out:json][timeout:60];
way["building"](around:1000,50.28420545,82.209512);
out count;"""
for endpoint in [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]:
    try:
        r = requests.post(endpoint, data={"data": q}, headers=UA, timeout=70)
        txt = r.text[:200].replace("\n", " ")
        print(f"  {endpoint}: HTTP {r.status_code} :: {txt}")
    except Exception as e:
        print(f"  {endpoint}: ERROR {e}")
