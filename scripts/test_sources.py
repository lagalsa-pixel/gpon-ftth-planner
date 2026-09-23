#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тест источников спутниковых тайлов: сравнение детализации в одной точке."""
import math, urllib.request, os, hashlib
import numpy as np
import cv2

LAT, LON = 50.28420545, 82.209512  # Верхнеберезовка

def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    lr = math.radians(lat)
    yt = (1.0 - math.log(math.tan(lr) + 1.0/math.cos(lr)) / math.pi) / 2.0 * n
    return xt, yt

def fetch(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def detail_score(img):
    """std градиента — мера детализации"""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(g, cv2.CV_64F).var()

tests = []
for z in (17, 18):
    xt, yt = latlon_to_tile(LAT, LON, z)
    x, y = int(xt), int(yt)
    tests.append((f"esri_z{z}", f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"))
    tests.append((f"google_z{z}", f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"))
    tests.append((f"google_z{z}_y", f"https://mt2.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"))

# Yandex (другая проекция z→x,y отличается; используем спутниковый слой)
# Опустим из-за сложной проекции, добавим Bing (quadkey)
def quadkey(x, y, z):
    q = ""
    for i in range(z, 0, -1):
        d = 0
        m = 1 << (i - 1)
        if x & m: d += 1
        if y & m: d += 2
        q += str(d)
    return q

for z in (17, 18):
    xt, yt = latlon_to_tile(LAT, LON, z)
    x, y = int(xt), int(yt)
    qk = quadkey(x, y, z)
    tests.append((f"bing_z{z}", f"https://t3.ssl.ak.tiles.virtualearth.net/tiles/a{qk}.jpeg?g=1"))

os.makedirs('/tmp/tiletest', exist_ok=True)
for name, url in tests:
    try:
        data = fetch(url)
        p = f'/tmp/tiletest/{name}.jpg'
        with open(p, 'wb') as f:
            f.write(data)
        img = cv2.imread(p)
        if img is None:
            print(f"{name:14s}: НЕ ИЗОБРАЖЕНИЕ ({len(data)} байт)")
            continue
        sc = detail_score(img)
        print(f"{name:14s}: {len(data):6d} байт {img.shape} детализация={sc:8.1f} ср.яркость={img.mean():.0f}")
    except Exception as e:
        print(f"{name:14s}: {type(e).__name__} {e}")
