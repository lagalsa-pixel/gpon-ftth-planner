#!/usr/bin/env python3
"""Тест альтернативных источников спутниковых тайлов на повышенный зум (z18-19) для с.Верхнеберезовка."""
import requests, io, math, hashlib
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

def stats(content):
    try:
        img = Image.open(io.BytesIO(content))
        arr = np.array(img.convert("RGB")).astype(float)
        return f"size={img.size} bytes={len(content)} std={arr.std():.1f}"
    except Exception as e:
        return f"not-image({e})"

def test(name, url_fn, zooms=(18, 19)):
    print(f"--- {name} ---")
    for z in zooms:
        x, y = deg2tile(lat, lon, z)
        url = url_fn(z, x, y)
        try:
            r = requests.get(url, headers=UA, timeout=25)
            s = stats(r.content) if r.status_code == 200 else "-"
            print(f"  z={z}: HTTP {r.status_code} {s} url={url[:100]}")
        except Exception as e:
            print(f"  z={z}: ERROR {type(e).__name__}")

# 1. ESRI World Imagery Clarity
test("ESRI World_Imagery_Clarity",
     lambda z, x, y: f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery_Clarity/MapServer/tile/{z}/{y}/{x}")

# 2. Yandex: разные варианты endpoints
test("Yandex sat01 + v=2023.09.06.17.00",
     lambda z, x, y: f"https://sat01.maps.yandex.net/?l=sat&v=2023.09.06.17.00&x={x}&y={y}&z={z}")
test("Yandex core-stv-renderer l=sat",
     lambda z, x, y: f"https://core-stv-renderer.maps.yandex.net/2.x/tiles?l=sat&v=2024.09.09.00.00&x={x}&y={y}&z={z}&scale=1")
test("Yandex sat03 l=sat,v=3.",
     lambda z, x, y: f"https://sat03.maps.yandex.net/?l=sat&v=3.563.0&x={x}&y={y}&z={z}")

# 3. Mapy.cz (старый публичный endpoint)
test("Mapy.cz sat-m",
     lambda z, x, y: f"https://m3.mapserver.mapy.cz/sat-m/{z}-{x}-{y}")

# 4. Google Maps satellite (техническая проверка доступности)
test("Google mt1 lyrs=s",
     lambda z, x, y: f"https://mt1.googleapis.com/vt?lyrs=s&x={x}&y={y}&z={z}")
test("Google khms0",
     lambda z, x, y: f"https://khms0.googleapis.com/kh?v=998&x={x}&y={y}&z={z}")
