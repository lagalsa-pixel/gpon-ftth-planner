#!/usr/bin/env python3
"""Точная проверка: содержит ли Google z19 подлинные детали сверх z18?
Метод: вырезаем верхний левый квадрант z18-тайла (128x128), увеличиваем до 256,
сравниваем с настоящим z19-тайлом (256x256, та же территория)."""
import requests, io, math
import numpy as np
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
lat, lon = 50.28420545, 82.209512

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
    L = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:])
    return L.mean()

def ssim_simple(a, b):
    a = a.astype(float).mean(axis=2); b = b.astype(float).mean(axis=2)
    a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
    return float((a * b).mean())

for name, la, lo in [("Верхнеберезовка", 50.28420545, 82.209512), ("Пригородное", 50.321981, 83.52094976)]:
    x18, y18 = deg2tile(la, lo, 18)
    t18 = gtile(18, x18, y18)            # 256x256, площадь S
    t19 = gtile(19, 2 * x18, 2 * y18)    # 256x256, площадь S/4 (верхний левый квадрант)
    q18 = t18[:128, :128]                # квадрант z18, 128x128
    q18_up = np.array(Image.fromarray(q18).resize((256, 256), Image.BICUBIC))

    mae = np.abs(q18_up.astype(float) - t19.astype(float)).mean()
    sim = ssim_simple(q18_up, t19)
    print(f"{name}:")
    print(f"  MAE(z18_quadrant_upscaled vs z19) = {mae:.2f} (низкий <8 => z19 это апскейл z18)")
    print(f"  Корреляция структур = {sim:.3f} (близко 1 => одна и та же картинка)")
    print(f"  Laplacian: z18_quad_upscaled={lap(q18_up):.2f}, z19={lap(t19):.2f}")
    print(f"  (если z19 острее в ~2+ раза => подлинное разрешение выше; если сопоставимо => апскейл)")
    Image.fromarray(t18).save(f"/home/z/my-project/scripts/tiles_cache/chk_{name}_z18.png")
    Image.fromarray(t19).save(f"/home/z/my-project/scripts/tiles_cache/chk_{name}_z19.png")
    Image.fromarray(q18_up).save(f"/home/z/my-project/scripts/tiles_cache/chk_{name}_z18up.png")
print("\nСохранены контрольные тайлы в scripts/tiles_cache/ для визуальной проверки")
