# -*- coding: utf-8 -*-
"""Точная идентификация субкластеров вокруг Пригородного (zoom 15 reverse geocode)."""
import sys, os, math, requests, time, json
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json, HDRS

d = load_json(f'{vdir("prigorodnoe")}/osm.json')
clat, clon = 50.321981, 83.52094976

grid = {}
for b in d['buildings']:
    la, lo = b['center']
    if not (83.505 <= lo <= 83.555 and 50.310 <= la <= 50.348):
        continue
    gk = (round(la / 0.0036), round(lo / 0.0056))  # ~400x400 м
    grid.setdefault(gk, []).append((la, lo))

def rev(lat, lon):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 15, 'accept-language': 'ru'},
                         headers=HDRS, timeout=25)
        if r.status_code == 200:
            a = r.json().get('address', {})
            return f"{a.get('village') or a.get('hamlet') or a.get('suburb') or a.get('city_district') or a.get('town') or '?'}|{a.get('road','')}"
    except Exception:
        return 'ERR'
    return '?'

clusters = sorted(grid.items(), key=lambda kv: -len(kv[1]))
for gk, pts in clusters[:24]:
    la = sum(p[0] for p in pts)/len(pts); lo = sum(p[1] for p in pts)/len(pts)
    dd = math.hypot((la-clat)*111320, (lo-clon)*111320*math.cos(math.radians(clat)))
    # направление от центра
    ang = math.degrees(math.atan2((la-clat)*111320, (lo-clon)*111320*math.cos(math.radians(clat))))
    dirs = 'С' if 45<=ang<135 else 'В' if -45<=ang<45 else 'Ю' if -135<=ang<-45 else 'З'
    print(f"  {len(pts):4d} зд @({la:.4f},{lo:.4f}) {dd:4.0f} м {dirs} -> {rev(la, lo)}")
    time.sleep(1.05)
