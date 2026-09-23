# -*- coding: utf-8 -*-
"""
Шаг 2b. Точная классификация кластеров зданий (сетка 250 м) по названиям НП (Nominatim reverse).
Формирует финальный bbox: кластеры целевого села + кластеры 'вблизи без имени' + 300 м запас.
"""
import sys, os, math, requests, time, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json, HDRS

def dist_m(la1, lo1, la2, lo2):
    return math.hypot((la1-la2)*111320, (lo1-lo2)*111320*math.cos(math.radians((la1+la2)/2)))

rev_cache = {}
def rev(lat, lon, zoom=13):
    k = (round(lat, 4), round(lon, 4), zoom)
    if k in rev_cache:
        return rev_cache[k]
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': zoom, 'accept-language': 'ru'},
                         headers=HDRS, timeout=25)
        if r.status_code == 200:
            a = r.json().get('address', {})
            name = a.get('village') or a.get('town') or a.get('hamlet') or a.get('suburb') or a.get('city_district') or a.get('city') or ''
            res = (name, a.get('city') or a.get('town') or a.get('state_district') or '')
        else:
            res = ('ERR', '')
    except Exception:
        time.sleep(2)
        res = ('ERR', '')
    rev_cache[k] = res
    time.sleep(1.05)  # лимит Nominatim 1 req/s
    return res

# Целевое имя села в OSM (уточним для Пригородного отдельно)
TARGET = {
    'verhneberezovka': ['Верхнеберёзовка', 'Верхнеберезовка'],
    'solnechnoe': ['Солнечное'],
    'perevalnoe': ['Перевальное'],
    'vinnoe': ['Винное'],
    'prigorodnoe': ['Пригородное'],
    'altaiskiy': ['Алтайский'],
}

out = {}
for v in VILLAGES:
    key = v['key']
    d = load_json(f'{vdir(key)}/osm.json')
    clat, clon = v['lat'], v['lon']
    # кластеры 250 м
    grid = {}
    for b in d['buildings']:
        la, lo = b['center']
        gk = (round(la / 0.00225), round(lo / 0.0035))
        grid.setdefault(gk, []).append((la, lo))
    print(f"\n=== {v['name']} ===")
    keep, other = [], {}
    for gk, pts in grid.items():
        if len(pts) < 3:   # одиночки/фермы пропускаем
            continue
        la = sum(p[0] for p in pts)/len(pts); lo = sum(p[1] for p in pts)/len(pts)
        dd = dist_m(la, lo, clat, clon)
        if dd > 2800:  # далеко за пределами интереса
            continue
        nm, parent = rev(la, lo)
        nm_n = nm.replace('ё', 'е').strip().lower()
        tgt = [t.replace('ё', 'е').lower() for t in TARGET[key]]
        if nm_n in tgt or (nm == 'ERR' and dd < 1200):
            keep.extend(pts)
        elif nm == '' and dd < 900:
            keep.extend(pts)  # безымянное рядом — считаем целевым
        elif nm != 'ERR':
            other.setdefault(nm, []).append(len(pts))
    if keep:
        lats = [p[0] for p in keep]; lons = [p[1] for p in keep]
        pad_lat = 300/111320; pad_lon = 300/(111320*math.cos(math.radians(clat)))
        fb = [min(lons)-pad_lon, min(lats)-pad_lat, max(lons)+pad_lon, max(lats)+pad_lat]
        w = (fb[2]-fb[0])*111320*math.cos(math.radians(clat))/1000
        h = (fb[3]-fb[1])*111320/1000
        n_b = len([1 for gk, pts in grid.items() if True for p in pts]) # всего
        print(f"  целевых кластеров зданий: {len(keep)}, bbox: {fb[0]:.4f},{fb[1]:.4f} - {fb[2]:.4f},{fb[3]:.4f} ({w:.2f} x {h:.2f} км)")
        print(f"  соседние НП (исключены): {other}")
        out[key] = dict(bbox=fb, n_target_bld=len(keep), others={k: sum(vv) for k, vv in other.items()})
    save_json(f'{vdir(key)}/bbox_final.json', out.get(key))

# отдельно: что в центре Пригородного?
v = VILLAGES[4]
nm, parent = rev(v['lat'], v['lon'], 15)
print(f"\nЦентр Пригородного ({v['lat']},{v['lon']}) -> {nm} / {parent}")
save_json('/home/z/my-project/work/bboxes_final.json', out)
