# -*- coding: utf-8 -*-
"""Проверка OSM-покрытия (дороги, здания связи) по 6 СНП через overpass.osm.ch"""
import requests, time

HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}
OV = "https://overpass.osm.ch/api/interpreter"

VILLAGES = [
    ("Верхнеберезовка", 50.28420545, 82.209512, 940),
    ("Солнечное",        50.0517755,  82.71438134, 366),
    ("Перевальное",      50.24139084, 82.28314297, 339),
    ("Винное",           50.05844487, 82.82687999, 490),
    ("Пригородное",      50.321981,   83.52094976, 365),
    ("Алтайский",        50.24399825, 82.36103064, 716),
]

for name, lat, lon, n in VILLAGES:
    q = f"""
    [out:json][timeout:80];
    (
      way["highway"](around:2500,{lat},{lon});
    );
    out count;
    (
      nwr["amenity"~"post_office|telecom|bank|townhall"](around:2500,{lat},{lon});
      nwr["office"~"telecom|post"](around:2500,{lat},{lon});
      nwr["man_made"="mast"](around:2500,{lat},{lon});
    );
    out center tags 30;
    """
    try:
        r = requests.post(OV, data={'data': q}, headers=HDRS, timeout=100)
        d = r.json()
        els = d.get('elements', [])
        roads = None
        pois = []
        for el in els:
            if el.get('type') == 'count':
                roads = el.get('tags', {}).get('ways')
            else:
                pois.append(el)
        print(f"{name}: roads={roads}, POI={len(pois)}")
        for p in pois[:12]:
            t = p.get('tags', {})
            la = p.get('lat') or p.get('center', {}).get('lat')
            lo = p.get('lon') or p.get('center', {}).get('lon')
            print(f"   {t.get('amenity','')}{t.get('office','')}{t.get('man_made','')} | {t.get('name','(нет имени)')} | {la:.6f},{lo:.6f}")
    except Exception as e:
        print(f"{name}: FAIL {str(e)[:100]}")
    time.sleep(2)
