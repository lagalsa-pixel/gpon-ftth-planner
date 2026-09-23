# -*- coding: utf-8 -*-
"""Тест альтернативных Overpass-зеркал и Nominatim"""
import requests

HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}

for host in ["https://overpass.kumi.systems/api/interpreter",
             "https://overpass.osm.ch/api/interpreter",
             "https://overpass.osm.jp/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]:
    q = "[out:json][timeout:25];node(around:100,50.2842,82.2095)[amenity];out 5;"
    try:
        r = requests.post(host, data={'data': q}, headers=HDRS, timeout=30)
        print(host, "->", r.status_code, len(r.content))
        if r.status_code == 200:
            print("   OK, elements:", len(r.json().get('elements', [])))
            break
    except Exception as e:
        print(host, "-> FAIL", str(e)[:80])

# Nominatim: поиск Казпочты в Верхнеберезовке
for q in ["Казпочта Верхнеберезовка", "Казпочта Солнечное Глубоковский", "почта Верхнеберезовка Казахстан"]:
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={'q': q, 'format': 'json', 'limit': 5, 'accept-language': 'ru'},
                         headers=HDRS, timeout=25)
        print("Nominatim:", q, "->", r.status_code, len(r.json()) if r.status_code == 200 else r.text[:100])
        if r.status_code == 200:
            for it in r.json()[:5]:
                print("   ", it.get('display_name', '')[:90], "|", it.get('lat'), it.get('lon'), "|", it.get('type'))
    except Exception as e:
        print("Nominatim FAIL:", q, str(e)[:80])
