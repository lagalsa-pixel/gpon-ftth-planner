# -*- coding: utf-8 -*-
"""Идентификация дальних кластеров зданий через Nominatim reverse geocoding."""
import sys, os, math, requests, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, HDRS

def dist_m(la1, lo1, la2, lo2):
    return math.hypot((la1-la2)*111320, (lo1-lo2)*111320*math.cos(math.radians((la1+la2)/2)))

def rev(lat, lon):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 14, 'accept-language': 'ru'},
                         headers=HDRS, timeout=25)
        if r.status_code == 200:
            a = r.json().get('address', {})
            return f"{a.get('village') or a.get('town') or a.get('suburb') or a.get('hamlet') or '?'} / {a.get('city') or a.get('state_district') or ''} ({a.get('county','')})".strip()
    except Exception as e:
        return f"ERR {str(e)[:40]}"
    return "?"

# Кластеры зданий по сетке 300 м; вывести кластеры размером >=8 зданий, отсортированные по размеру
for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    clat, clon = v['lat'], v['lon']
    grid = {}
    for b in d['buildings']:
        la, lo = b['center']
        gk = (round(la / 0.0027), round(lo / 0.0042))  # ~300x300 м
        grid.setdefault(gk, []).append((la, lo))
    clusters = sorted(grid.items(), key=lambda kv: -len(kv[1]))
    print(f"\n=== {v['name']} (центр {clat},{clon}) ===")
    shown = 0
    for gk, pts in clusters:
        if len(pts) < 8 or shown >= 6:
            continue
        la = sum(p[0] for p in pts)/len(pts); lo = sum(p[1] for p in pts)/len(pts)
        dd = dist_m(la, lo, clat, clon)
        print(f"  кластер {len(pts):3d} зд @ ({la:.4f},{lo:.4f}) {dd:5.0f} м от центра -> {rev(la, lo)}")
        shown += 1
