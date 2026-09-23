#!/usr/bin/env python3
"""1) Проверка: Google z19 — подлинное разрешение или апскейл z18?
2) Диагностика OSM: place-узлы и landuse=residential возле каждого села."""
import requests, io, math
from PIL import Image
import numpy as np

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

lat, lon = 50.28420545, 82.209512

def deg2tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return int(x), int(y)

def gtile(z, x, y):
    url = f"https://mt1.googleapis.com/vt?lyrs=s&x={x}&y={y}&z={z}"
    r = requests.get(url, headers=UA, timeout=25)
    return Image.open(io.BytesIO(r.content)).convert("RGB")

# Тот же участок: z18 (x,y) и z19 (2x, 2y) — верхний левый квадрант z19-тайла
x18, y18 = deg2tile(lat, lon, 18)
t18 = np.array(gtile(18, x18, y18)).astype(float)
t19 = np.array(gtile(19, 2 * x18, 2 * y18)).astype(float)
t19_ds = np.array(Image.fromarray(t19.astype(np.uint8)).resize((256, 256), Image.LANCZOS)).astype(float)

def lap_energy(arr):
    a = arr.mean(axis=2)
    lap = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:])
    return lap.mean()

mae = np.abs(t18 - t19_ds).mean()
print(f"MAE(z18, z19_downscaled) = {mae:.2f} (0-255; <8 => z19 это апскейл z18)", flush=True)
print(f"Laplacian z19 = {lap_energy(t19):.2f}", flush=True)
print(f"Laplacian z18 = {lap_energy(t18):.2f}", flush=True)

# z20 тест
try:
    x20, y20 = deg2tile(lat, lon, 20)
    t20 = gtile(20, 2 * (2 * x18), 2 * (2 * y18))
    a20 = np.array(t20).astype(float)
    print(f"\nz20 доступен: size={t20.size}, std={a20.std():.1f}, lap={lap_energy(a20):.2f}")
except Exception as e:
    print(f"\nz20: {e}")

# OSM диагностика
print("\n=== OSM: place-узлы (r=6км) и landuse/buildings (r=3км) ===")
VILLAGES = [
    ("Верхнеберезовка", 50.28420545, 82.209512),
    ("Солнечное", 50.0517755, 82.71438134),
    ("Перевальное", 50.24139084, 82.28314297),
    ("Винное", 50.05844487, 82.82687999),
    ("Пригородное", 50.321981, 83.52094976),
    ("Алтайский", 50.24399825, 82.36103064),
]
OV = "https://overpass.kumi.systems/api/interpreter"

for name, la, lo in VILLAGES:
    q = f"""[out:json][timeout:90];
(
  node["place"](around:6000,{la},{lo});
  way["landuse"~"residential"](around:3000,{la},{lo});
);
out tags center;"""
    r = requests.post(OV, data={"data": q}, headers=UA, timeout=100)
    if r.status_code != 200:
        print(f"  Overpass HTTP {r.status_code}: {r.text[:150]}", flush=True)
        continue
    try:
        data = r.json()
    except Exception as e:
        print(f"  JSON error: {e}; text: {r.text[:150]}", flush=True)
        continue
    places = [(el.get("tags", {}).get("name", "?"), el.get("tags", {}).get("place", "?"),
               round(el.get("lat", 0), 4), round(el.get("lon", 0), 4))
              for el in data.get("elements", []) if el["type"] == "node"]
    res = [(el.get("tags", {}).get("name", "?"), round(el.get("center", {}).get("lat", 0), 4), round(el.get("center", {}).get("lon", 0), 4))
           for el in data.get("elements", []) if el["type"] == "way"]
    print(f"\n{name} ({la},{lo}):", flush=True)
    print(f"  place-узлы (r=6км): {places[:12]}", flush=True)
    print(f"  landuse=residential (r=3км): {res[:8]}", flush=True)
    import time; time.sleep(2)
