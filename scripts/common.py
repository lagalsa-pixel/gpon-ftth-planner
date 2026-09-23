# -*- coding: utf-8 -*-
"""
Общий модуль: список СНП, проекции/тайловая математика, HTTP-хелперы, пути.
"""
import math, os, time, json, random
import requests

BASE = '/home/z/my-project'
WORK = f'{BASE}/work'
DL = f'{BASE}/download/snp_vko'
TILE_CACHE = f'{WORK}/tiles'

HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}

# name, lat, lon, expected households, camera range d (м), район, округ
VILLAGES = [
    dict(key='verhneberezovka', name='Верхнеберезовка', raion='Глубоковский район',
         okrug='Верхнеберезовский с.о.', lat=50.28420545, lon=82.20951200, hh=940, rng=2529),
    dict(key='solnechnoe', name='Солнечное', raion='Глубоковский район',
         okrug='Бобровский с.о.', lat=50.05177550, lon=82.71438134, hh=366, rng=2193),
    dict(key='perevalnoe', name='Перевальное', raion='Глубоковский район',
         okrug='Красноярский с.о.', lat=50.24139084, lon=82.28314297, hh=339, rng=3081),
    dict(key='vinnoe', name='Винное', raion='Глубоковский район',
         okrug='Тарханский с.о.', lat=50.05844487, lon=82.82687999, hh=490, rng=2853),
    dict(key='prigorodnoe', name='Пригородное', raion='г. Риддер',
         okrug='Пригородная зона г. Риддер', lat=50.32198100, lon=83.52094976, hh=365, rng=2602),
    dict(key='altaiskiy', name='Алтайский', raion='Глубоковский район',
         okrug='Алтайский с.о.', lat=50.24399825, lon=82.36103064, hh=716, rng=4095),
]

V = {v['key']: v for v in VILLAGES}

# ---------- Web Mercator ----------
def lon2tx(lon, z):
    return (lon + 180.0) / 360.0 * (1 << z)

def lat2ty(lat, z):
    lr = math.radians(lat)
    return (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * (1 << z)

def tx2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0

def ty2lat(y, z):
    n = math.pi * (1.0 - 2.0 * y / (1 << z))
    return math.degrees(math.atan(math.sinh(n)))

def m_per_px(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (1 << z)

# ---------- HTTP с ретраями ----------
def http_get(url, params=None, tries=4, timeout=40, backoff=2.0):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HDRS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503, 504):
                last = f'HTTP {r.status_code}'
            else:
                r.raise_for_status()
        except Exception as e:
            last = str(e)[:100]
        time.sleep(backoff * (i + 1) + random.random())
    raise RuntimeError(f'GET {url[:90]} failed: {last}')

ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
GOOGLE = 'https://mt{m}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
GUA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
       'Referer': 'https://www.google.com/maps'}

def fetch_tile(z, x, y, source='google'):
    """Скачать тайл с дисковым кэшем. Возвращает bytes или None."""
    if source == 'google':
        p = f'{TILE_CACHE}/g{z}/{x}/{y}.jpg'
        url = GOOGLE.format(m=(x + y) % 4, z=z, x=x, y=y)
        hdrs = GUA
    else:
        p = f'{TILE_CACHE}/{z}/{x}/{y}.jpg'
        url = ESRI.format(z=z, x=x, y=y)
        hdrs = HDRS
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p):
        if os.path.getsize(p) > 0:
            with open(p, 'rb') as f:
                return f.read()
        else:
            return None  # ранее известный пустой тайл
    for attempt in range(3):
        try:
            r = requests.get(url, headers=hdrs, timeout=30)
            if r.status_code == 200 and len(r.content) > 500:
                with open(p, 'wb') as f:
                    f.write(r.content)
                return r.content
            if r.status_code in (404,):
                open(p, 'wb').close()  # пустой маркер
                return None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None

def ensure_dirs():
    for d in (WORK, DL, TILE_CACHE, f'{BASE}/scripts'):
        os.makedirs(d, exist_ok=True)

def vdir(key):
    d = f'{WORK}/{key}'
    os.makedirs(d, exist_ok=True)
    return d

def save_json(path, obj):
    import numpy as np
    def _conv(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f'not serializable: {type(o)}')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, default=_conv)

def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
