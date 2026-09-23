# -*- coding: utf-8 -*-
"""Проверка доступности источников: ESRI World Imagery + Overpass API"""
import requests, json

HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}

# 1) ESRI World Imagery tile
try:
    url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/15/15000/25000"
    r = requests.get(url, headers=HDRS, timeout=20)
    print("ESRI tile:", r.status_code, r.headers.get('Content-Type'), len(r.content), "bytes")
except Exception as e:
    print("ESRI FAIL:", e)

# 2) Overpass API
q = """
[out:json][timeout:60];
(
  node["amenity"="post_office"](around:3000,50.2842,82.2095);
  way["amenity"="post_office"](around:3000,50.2842,82.2095);
  way["building"](around:1500,50.2842,82.2095);
);
out center tags 100;
"""
try:
    r = requests.post("https://overpass-api.de/api/interpreter", data={'data': q}, headers=HDRS, timeout=70)
    print("Overpass:", r.status_code, len(r.content), "bytes")
    if r.status_code == 200:
        d = r.json()
        print("Elements:", len(d.get('elements', [])))
        for el in d.get('elements', [])[:10]:
            t = el.get('tags', {})
            lat = el.get('lat') or el.get('center', {}).get('lat')
            lon = el.get('lon') or el.get('center', {}).get('lon')
            print(" ", el['type'], el['id'], t.get('name', t.get('amenity', t.get('building', '?'))), lat, lon)
except Exception as e:
    print("Overpass FAIL:", e)
