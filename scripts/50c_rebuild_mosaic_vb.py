#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50c: восстановление work/verhneberezovka/mosaic.jpg из кэша тайлов.

Мозаика — регенерируемый файл (удалён при чистке диска в прошлой сессии).
Кэш scripts/tiles_cache/z18/{x}_{y}.png (google z18, download_and_stitch)
покрывает bbox ВБ на 100%. Кэш common.fetch_tile — work/tiles/g18/{x}/{y}.jpg:
копируем туда байты тайлов (PIL читает по содержимому), затем собираем
мозаику функцией 03_imagery_z18.mosaic_for (кэш-хиты, без сети).

Контроль: гео против work/mosaic_geo.json['verhneberezovka'] (W/H/mpp/west/north
должны совпасть). Сателлит-PNG в download/snp_vko удаляется, чтобы не менять
состав релизного каталога.
"""
import json, math, os, shutil, importlib.util, sys

BASE = '/home/z/my-project'
KEY = 'verhneberezovka'

# --- 1) пополнить кэш g18 из z18-кэша ---
bf = json.load(open(f'{BASE}/work/bboxes_final.json', encoding='utf-8'))
bbox = bf[KEY]['bbox']

def lon2tx(lon, z): return (lon + 180.0) / 360.0 * (2 ** z)
def lat2ty(lat, z):
    return (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * (2 ** z)

Z = 18
x0, x1 = int(math.floor(lon2tx(bbox[0], Z))), int(math.ceil(lon2tx(bbox[2], Z)))
y0, y1 = int(math.floor(lat2ty(bbox[3], Z))), int(math.ceil(lat2ty(bbox[1], Z)))
copied = skipped = 0
for tx in range(x0, x1):
    for ty in range(y0, y1):
        src = f'{BASE}/scripts/tiles_cache/z18/{tx}_{ty}.png'
        dst = f'{BASE}/work/tiles/g{Z}/{tx}/{ty}.jpg'
        if not os.path.exists(src):
            print(f'! нет в кэше: {tx}_{ty}')
            continue
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
print(f'кэш g18: скопировано {copied}, уже было {skipped}, диапазон {x1-x0}x{y1-y0}')

# --- 2) собрать мозаику функцией 03 ---
spec = importlib.util.spec_from_file_location('m03', f'{BASE}/scripts/03_imagery_z18.py')
m03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m03)
v = next(v for v in m03.VILLAGES if v['key'] == KEY)
geo_new = m03.mosaic_for(v, bbox)
print('geo_new:', json.dumps(geo_new))

# --- 3) контроль геометрии против эталона ---
geo_old = json.load(open(f'{BASE}/work/mosaic_geo.json', encoding='utf-8'))[KEY]
ok = True
for f in ('W', 'H', 'missing'):
    if geo_new[f] != geo_old[f]:
        print(f'!! {f}: {geo_new[f]} != {geo_old[f]}'); ok = False
for f in ('mpp', 'west', 'north'):
    if abs(geo_new[f] - geo_old[f]) > 1e-6:
        print(f'!! {f}: {geo_new[f]} != {geo_old[f]}'); ok = False
sz = os.path.getsize(f'{BASE}/work/{KEY}/mosaic.jpg') / 1e6
print(f'mosaic.jpg: {geo_new["W"]}x{geo_new["H"]}px, {sz:.1f} МБ')
print('ГЕОМЕТРИЯ:', 'СОВПАДАЕТ с эталоном' if ok else 'РАСХОЖДЕНИЕ!')

# --- 4) не менять состав релизного каталога ---
sat = f'{BASE}/download/snp_vko/01_{KEY}_satellite.png'
if os.path.exists(sat):
    os.remove(sat)
    print('сателлит-PNG удалён из download/snp_vko (релизный состав сохранён)')

sys.exit(0 if ok and geo_new['missing'] == 0 else 1)
