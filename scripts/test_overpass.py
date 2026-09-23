#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тест Overpass API: дороги и здания для Верхнеберезовки"""
import json, urllib.request, urllib.parse

LAT, LON = 50.28420545, 82.209512
D = 0.020  # ~±1.5 км широты
bbox = (LAT - D, LON - D * 1.42, LAT + D, LON + D * 1.42)  # s,w,n,e

q = f'''
[out:json][timeout:90];
(
  way["building"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out geom;
'''
url = "https://overpass-api.de/api/interpreter?" + urllib.parse.urlencode({"data": q})
req = urllib.request.Request(url, headers={"User-Agent": "FTTH-design/1.0"})
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    buildings = [el for el in data["elements"] if el.get("type") == "way" and "geometry" in el]
    print(f"Зданий в OSM: {len(buildings)}")
    if buildings:
        b = buildings[0]
        print("Пример:", {k: v for k, v in b.get("tags", {}).items()})
except Exception as e:
    print("ОШИБКА:", e)
