#!/usr/bin/env python3
"""Быстрая проверка: Google z19/z20 — подлинное разрешение или апскейл."""
import requests, io, math
from PIL import Image
import numpy as np

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
    return Image.open(io.BytesIO(r.content)).convert("RGB")

def lap_energy(arr):
    a = arr.mean(axis=2)
    lap = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:])
    return lap.mean()

x18, y18 = deg2tile(lat, lon, 18)
t18 = np.array(gtile(18, x18, y18)).astype(float)
t19 = np.array(gtile(19, 2 * x18, 2 * y18)).astype(float)
t19_ds = np.array(Image.fromarray(t19.astype(np.uint8)).resize((256, 256), Image.LANCZOS)).astype(float)

mae = np.abs(t18 - t19_ds).mean()
print(f"MAE(z18 vs z19->downscale) = {mae:.2f} из 255 (меньше ~6 => z19 = апскейл z18)")
print(f"Laplacian (острота деталей): z18={lap_energy(t18):.2f}, z19={lap_energy(t19):.2f}")
print("Если z19 заметно острее z18 => в z19 есть подлинные детали; если близко => апскейл.")

# z20
try:
    t20 = np.array(gtile(20, 4 * x18, 4 * y18)).astype(float)
    print(f"z20: доступен, Laplacian={lap_energy(t20):.2f}")
except Exception as e:
    print(f"z20: недоступен ({e})")

# Сравнение содержимого z19 тайлов в разных квадрантах (проверка, что z19 не заглушка)
q2 = np.array(gtile(19, 2 * x18 + 1, 2 * y18)).astype(float)
print(f"Различие квадрантов z19 (std): {np.abs(t19.mean()-q2.mean()):.1f}, lap q2={lap_energy(q2):.2f}")
