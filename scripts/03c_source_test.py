# -*- coding: utf-8 -*-
"""Тест Google Satellite и Yandex Satellite тайлов на высоких зумах (z17-z19)."""
import sys, os, io, math, requests
sys.path.insert(0, os.path.dirname(__file__))
from common import lon2tx, lat2ty, HDRS
import numpy as np
from PIL import Image

def ellips_ty(lat, z):
    """Yandex: EPSG:3395 (эллипсоидальная Меркатора)."""
    R = 6378137.0
    lat_r = math.radians(lat)
    # изоширотная проекция Меркатора на эллипсоиде WGS84
    e = 0.0818191908426  # эксцентриситет
    con = ((1 - math.sin(lat_r)) / (1 + math.sin(lat_r))) ** (e / 2)
    ts = math.tan(math.pi / 4 - lat_r / 2) / con
    y = R * math.log(ts)
    n = 2 ** z * 256
    # масштаб как у сферической, но с множителем для широт
    return (1 - y / (math.pi * R)) / 2 * 2 ** z

def test_google(z, lat, lon):
    tx, ty = int(lon2tx(lon, z)), int(lat2ty(lat, z))
    for host in ['mt0', 'mt1']:
        url = f'https://{host}.google.com/vt/lyrs=s&x={tx}&y={ty}&z={z}'
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}, timeout=20)
            if r.status_code == 200 and len(r.content) > 2000:
                im = np.asarray(Image.open(io.BytesIO(r.content)).convert('L'), dtype=np.float32)
                return f'mean={im.mean():.0f} std={im.std():.1f} sz={len(r.content)}'
            return f'HTTP {r.status_code} sz={len(r.content)}'
        except Exception as e:
            return f'ERR {str(e)[:40]}'
    return '?'

def test_yandex(z, lat, lon):
    tx, ty = int(lon2tx(lon, z)), int(ellips_ty(lat, z))
    url = f'https://core-sat.maps.yandex.net/tiles?l=sat&v=3&x={tx}&y={ty}&z={z}'
    try:
        r = requests.get(url, headers=HDRS, timeout=20)
        if r.status_code == 200 and len(r.content) > 2000:
            im = np.asarray(Image.open(io.BytesIO(r.content)).convert('L'), dtype=np.float32)
            return f'mean={im.mean():.0f} std={im.std():.1f} sz={len(r.content)}'
        return f'HTTP {r.status_code} sz={len(r.content)}'
    except Exception as e:
        return f'ERR {str(e)[:40]}'

lat, lon = 50.28420545, 82.209512
print('Верхнеберезовка:')
for z in (17, 18, 19):
    print(f'  Google z{z}: {test_google(z, lat, lon)}')
    print(f'  Yandex z{z}: {test_yandex(z, lat, lon)}')
lat2, lon2 = 50.0517755, 82.71438134
print('Солнечное:')
for z in (18, 19):
    print(f'  Google z{z}: {test_google(z, lat2, lon2)}')
    print(f'  Yandex z{z}: {test_yandex(z, lat2, lon2)}')
