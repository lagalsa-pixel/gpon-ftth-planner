# -*- coding: utf-8 -*-
"""Тест прямого OSM API (api/0.6/map) и остальных зеркал"""
import requests

HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}

# 1) Прямой OSM map API — bbox Верхнеберезовки ~2.5x2.5 км
# lon_min, lat_min, lon_max, lat_max
bbox = "82.180,50.273,82.240,50.296"
try:
    r = requests.get(f"https://api.openstreetmap.org/api/0.6/map",
                     params={'bbox': bbox}, headers=HDRS, timeout=90)
    print("OSM api/0.6/map:", r.status_code, len(r.content), "bytes")
    if r.status_code == 200:
        import re
        ways = len(re.findall(r'<way ', r.text))
        nodes = len(re.findall(r'<node ', r.text))
        highways = len(re.findall(r'k="highway"', r.text))
        buildings = len(re.findall(r'k="building"', r.text))
        post = r.text.count('post_office') + r.text.count('telecom')
        print(f"  nodes={nodes} ways={ways} highways={highways} buildings={buildings} post/telecom={post}")
except Exception as e:
    print("OSM map API FAIL:", str(e)[:120])

# 2) Ещё зеркала Overpass
for host in ["https://overpass.private.coffee/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]:
    q = "[out:json][timeout:60];way(around:800,50.2842,82.2095)[highway];out count;"
    try:
        r = requests.post(host, data={'data': q}, headers=HDRS, timeout=80)
        ok = "OK" if r.status_code == 200 else f"HTTP {r.status_code}"
        cnt = ""
        if r.status_code == 200:
            try:
                cnt = r.json().get('elements', [{}])[0].get('tags', {})
                cnt = str(cnt)
            except Exception:
                cnt = "?"
        print(f"{host} -> {ok} {cnt[:80]}")
    except Exception as e:
        print(f"{host} -> FAIL {str(e)[:80]}")
