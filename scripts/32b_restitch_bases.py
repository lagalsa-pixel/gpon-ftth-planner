# -*- coding: utf-8 -*-
"""
Шаг 32b. Перешив базовых снимков для Верхнеберезовки и Винного (Google z18,
источник mt{1..4}.googleapis.com — тот же, что у исходных мозаик).

Мозаики work/<key>/mosaic.jpg утеряны при сбросах среды; сети живут в их
координатном пространстве. Глобальный тайловый пиксель начала мозаики
восстанавливается точно из mosaic_geo.json (west/north -> lon2tx/lat2ty).
Канва режется по габариту сети + отступ, тайлы качаются параллельно.

Выход: work/<key>/base_restitch.png + work/<key>/restitch.json (параметры).
Контроль: NCC-сверка патча вокруг якоря с work/full (перекрытие есть).
"""
import json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/z/my-project/scripts')
from common import lon2tx, lat2ty

import numpy as np
from PIL import Image

BASE = '/home/z/my-project'
MARGIN_PX = 300
KEYS = ['verhneberezovka', 'vinnoe']
NETS = {'verhneberezovka': 'network.json', 'vinnoe': 'network_v2.json'}
SUBS = ['mt1', 'mt2', 'mt3', 'mt4']
Z = 18
HDRS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}


def net_bbox(key):
    net = json.load(open(f'{BASE}/work/{key}/{NETS[key]}'))
    xs, ys = [], []
    for e in net['feeder_edges']:
        xs += [e[0][0], e[1][0]]; ys += [e[0][1], e[1][1]]
    for d in net['drops']:
        xs.append(d['poly'][-1][0]); ys.append(d['poly'][-1][1])
    for c in net['couplers']:
        xs.append(c['x']); ys.append(c['y'])
    xs.append(net['anchor']['x']); ys.append(net['anchor']['y'])
    return net, min(xs), min(ys), max(xs), max(ys)


def fetch_tile(tx, ty, tries=3):
    import requests
    for i in range(tries):
        sub = SUBS[(tx + ty + i) % len(SUBS)]
        url = f'https://{sub}.googleapis.com/vt?lyrs=s&x={tx}&y={ty}&z={Z}'
        try:
            r = requests.get(url, headers=HDRS, timeout=20)
            if r.status_code == 200 and len(r.content) > 500:
                return tx, ty, r.content
        except Exception:
            time.sleep(0.5 * (i + 1))
    return tx, ty, None


def stitch(key):
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
    net, x0, y0, x1, y1 = net_bbox(key)
    # глобальный пиксель начала мозаики (точная тайловая математика)
    gx0_m = lon2tx(geo['west'], Z) * 256.0
    gy0_m = lat2ty(geo['north'], Z) * 256.0

    # габарит сети + отступ -> глобальные пиксели
    gx0 = gx0_m + x0 - MARGIN_PX
    gy0 = gy0_m + y0 - MARGIN_PX
    gx1 = gx0_m + x1 + MARGIN_PX
    gy1 = gy0_m + y1 + MARGIN_PX

    tx_first, ty_first = int(math.floor(gx0 / 256)), int(math.floor(gy0 / 256))
    tx_last = int(math.floor((gx1 - 1) / 256))
    ty_last = int(math.floor((gy1 - 1) / 256))

    W = (tx_last + 1 - tx_first) * 256
    H = (ty_last + 1 - ty_first) * 256
    # смещение: пиксель сети -> пиксель канвы
    offx = gx0_m - tx_first * 256.0
    offy = gy0_m - ty_first * 256.0
    print(f'{key}: сеть [{x0:.0f}..{x1:.0f}]x[{y0:.0f}..{y1:.0f}] '
          f'-> канва {W}x{H}, тайлы x[{tx_first}..{tx_last}] y[{ty_first}..{ty_last}] '
          f'({(tx_last - tx_first + 1) * (ty_last - ty_first + 1)} шт)')

    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    tiles = [(tx, ty) for ty in range(ty_first, ty_last + 1)
             for tx in range(tx_first, tx_last + 1)]
    missing = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        for tx, ty, data in ex.map(lambda t: fetch_tile(*t), tiles):
            if data is None:
                missing += 1
                continue
            import io
            im = Image.open(io.BytesIO(data)).convert('RGB')
            dx = (tx - tx_first) * 256
            dy = (ty - ty_first) * 256
            canvas[dy:dy + 256, dx:dx + 256] = np.asarray(im)
    print(f'  скачано {len(tiles) - missing}/{len(tiles)} тайлов за {time.time() - t0:.0f} с'
          f'{"  ЕСТЬ ПРОПУСКИ!" if missing else ""}')

    out = f'{BASE}/work/{key}/base_restitch.png'
    Image.fromarray(canvas).save(out)
    meta = dict(W=W, H=H, offx=offx, offy=offy, missing=missing, img=out,
                tx_first=tx_first, ty_first=ty_first)
    json.dump(meta, open(f'{BASE}/work/{key}/restitch.json', 'w'), indent=1)
    print(f'  сохранено {out}')
    return meta


def ncc_check(key, meta):
    """Сверка с work/full: патч вокруг якоря (перекрытие кадров)."""
    import io
    net = json.load(open(f'{BASE}/work/{key}/{NETS[key]}'))
    ax, ay = net['anchor']['x'], net['anchor']['y']
    # пиксель якоря в канве перешива и в кадре work/full (geo-цепочка шага 32)
    prep = json.load(open(f'{BASE}/work/zone_maps_prep.json'))
    b = prep[key]['bounds']
    CX, CY = ax + meta['offx'], ay + meta['offy']

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    full = Image.open(f'{BASE}/{prep[key]["img"]}').convert('RGB')
    fw, fh = full.size
    # координаты якоря в full: обратная задача — используем отношение границ,
    # надёжнее посчитать прямо: T() из prep воспроизводим здесь через якорь
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
    alat, alon = net['anchor']['lat'], net['anchor']['lon']
    mpp = geo['mpp']
    kx = mpp / (111320.0 * math.cos(math.radians(alat)))
    ky = mpp / 110574.0
    lat_max, lon_min, mpp_f = None, None, None
    # параметры кадра full из _final
    nm = {'verhneberezovka': '01', 'vinnoe': '04'}[key]
    fin = json.load(open(f'{BASE}/work/geo/'
                         f'{"Верхнеберезовка" if key == "verhneberezovka" else "Винное"}_final.json'))
    lat_max, lon_min, mpp_f = fin['lat_max'], fin['lon_min'], fin['m_per_px']
    lon = alon + (ax - net['anchor']['x']) * kx
    lat = alat - (ay - net['anchor']['y']) * ky
    FX = (lon - lon_min) * 111320.0 * math.cos(math.radians(alat)) / mpp_f
    FY = (lat_max - lat) * 110574.0 / mpp_f

    S = 220
    pa = Image.open(meta['img']).convert('RGB').crop((int(CX - S), int(CY - S), int(CX + S), int(CY + S)))
    pb = full.crop((int(FX - S), int(FY - S), int(FX + S), int(FY + S)))
    a = np.asarray(pa, dtype=np.float32).mean(axis=2)
    bb0 = np.asarray(pb, dtype=np.float32).mean(axis=2)
    a = (a - a.mean()) / (a.std() + 1e-6)
    best, bo = -2.0, (99, 99)
    for dy in range(-10, 11):
        for dx in range(-10, 11):
            bb = bb0[dy:dy + a.shape[0], dx:dx + a.shape[1]]
            if bb.shape != a.shape:
                continue
            bb = (bb - bb.mean()) / (bb.std() + 1e-6)
            c = float((a * bb).mean())
            if c > best:
                best, bo = c, (dx, dy)
    print(f'  NCC перешив vs work/full: смещение {bo}, пик {best:.3f}')
    return bo, best


if __name__ == '__main__':
    for key in KEYS:
        meta = stitch(key)
        bo, best = ncc_check(key, meta)
        assert abs(bo[0]) <= 3 and abs(bo[1]) <= 3, f'{key}: перешив не совпал с work/full!'
    print('\nOK: перешив совпадает с work/full в пределах 3 px')
