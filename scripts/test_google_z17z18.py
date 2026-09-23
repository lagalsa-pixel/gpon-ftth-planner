#!/usr/bin/env python3
"""Проверка: z18 подлинный или апскейл z17? Тот же квадрант-метод."""
import requests, io, math
import numpy as np
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

def deg2tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return int(x), int(y)

def gtile(z, x, y):
    url = f"https://mt1.googleapis.com/vt?lyrs=s&x={x}&y={y}&z={z}"
    r = requests.get(url, headers=UA, timeout=20)
    return np.array(Image.open(io.BytesIO(r.content)).convert("RGB")).astype(np.uint8)

def lap(arr):
    a = arr.astype(float).mean(axis=2)
    return float(np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]).mean())

def ssim_simple(a, b):
    a = a.astype(float).mean(axis=2); b = b.astype(float).mean(axis=2)
    a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
    return float((a * b).mean())

VILLAGES = [
    ("Верхнеберезовка", 50.28420545, 82.209512),
    ("Солнечное", 50.0517755, 82.71438134),
    ("Пригородное", 50.321981, 83.52094976),
]

for name, la, lo in VILLAGES:
    x17, y17 = deg2tile(la, lo, 17)
    t17 = gtile(17, x17, y17)
    t18 = gtile(18, 2 * x17, 2 * y17)     # верхний левый квадрант z17
    q17 = t17[:128, :128]
    q17_up = np.array(Image.fromarray(q17).resize((256, 256), Image.BICUBIC))
    mae = np.abs(q17_up.astype(float) - t18.astype(float)).mean()
    sim = ssim_simple(q17_up, t18)
    print(f"{name}: MAE(z17_quad_up vs z18) = {mae:.2f}, corr = {sim:.3f}, "
          f"lap: z17_up={lap(q17_up):.2f} vs z18={lap(t18):.2f}")
    print("   => " + ("z18 содержит НОВЫЕ детали (подлинное разрешение)" if (mae > 12 or sim < 0.90) else "z18 похож на апскейл z17 (но проверьте lap)"))
