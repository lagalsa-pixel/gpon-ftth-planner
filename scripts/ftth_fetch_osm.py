#!/usr/bin/env python3
"""Получение OSM-данных (здания + дороги) для 6 сёл ВКО и адм. границы Риддера.
Ротация зеркал Overpass, повторные попытки, пропуск уже скачанного."""
import json, os, random, sys, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'osm_ftth')
os.makedirs(OUT, exist_ok=True)

# key, name, lat, lon, margin_lat, margin_lon
VILLAGES = [
    ('verkhneberezovka', 'Верхнеберезовка', 50.28420545, 82.20951200, 0.040, 0.050),
    ('solnechnoe',       'Солнечное',       50.05177550, 82.71438134, 0.035, 0.045),
    ('perevalnoe',       'Перевальное',     50.24139084, 82.28314297, 0.040, 0.050),
    ('vinnoe',           'Винное',          50.05844487, 82.82687999, 0.030, 0.040),
    ('prigorodnoe',      'Пригородное',     50.32198100, 83.52094976, 0.025, 0.035),
    ('altayskiy',        'Алтайский',       50.24399825, 82.36103064, 0.050, 0.060),
]

MIRRORS = [
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.osm.jp/api/interpreter',
]
HEADERS = {'User-Agent': 'ftth-network-design-research/1.0 (rural network planning)'}


def run_query(query, tag, max_attempts=15):
    for attempt in range(max_attempts):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            print(f'[{tag}] попытка {attempt+1}: {url}', flush=True)
            r = requests.post(url, data={'data': query}, headers=HEADERS, timeout=300)
            if r.status_code == 429:
                print(f'[{tag}] 429 (rate limit), пауза 40 с', flush=True)
                time.sleep(40); continue
            if r.status_code == 504:
                print(f'[{tag}] 504 (gateway), смена зеркала', flush=True)
                time.sleep(15); continue
            if r.status_code != 200:
                print(f'[{tag}] HTTP {r.status_code}, смена зеркала', flush=True)
                time.sleep(random.uniform(10, 20)); continue
            data = r.json()
            if 'elements' in data:
                n = len(data['elements'])
                print(f'[{tag}] OK: {n} элементов ({len(r.content)/1e6:.1f} МБ)', flush=True)
                if n == 0:
                    print(f'[{tag}] ПУСТО — пропускаю, попробую другое зеркало', flush=True)
                    time.sleep(10); continue
                return data
        except Exception as e:
            print(f'[{tag}] ОШИБКА {url}: {type(e).__name__}: {str(e)[:120]}', flush=True)
        time.sleep(random.uniform(15, 30))
    return None


def village_query(lat, lon, mlat, mlon):
    s, n = lat - mlat, lat + mlat
    w, e = lon - mlon, lon + mlon
    bbox = f'({s:.6f},{w:.6f},{n:.6f},{e:.6f})'
    return f'''[out:json][timeout:240];
(
  way["building"]{bbox};
  way["highway"]{bbox};
);
out geom;'''


RIDDER_QUERY = '''[out:json][timeout:240];
(
  relation["boundary"="administrative"]["name"~"Риддер|Ridder"](50.25,83.35,50.48,83.75);
);
out geom;'''


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for key, name, lat, lon, mlat, mlon in VILLAGES:
        if only and key != only:
            continue
        path = os.path.join(OUT, f'{key}.json')
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f'[{key}] уже скачано, пропуск', flush=True)
            continue
        q = village_query(lat, lon, mlat, mlon)
        data = run_query(q, key)
        if data is None:
            print(f'[{key}] !!! НЕ УДАЛОСЬ получить данные', flush=True)
            continue
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        n_b = sum(1 for e in data['elements'] if e.get('tags', {}).get('building'))
        n_r = sum(1 for e in data['elements'] if e.get('tags', {}).get('highway'))
        print(f'[{key}] сохранено: зданий {n_b}, дорог {n_r}', flush=True)
        time.sleep(random.uniform(20, 35))

    # Граница Риддера для исключения городской застройки (село Пригородное)
    rpath = os.path.join(OUT, 'ridder.json')
    if not only and not (os.path.exists(rpath) and os.path.getsize(rpath) > 1000):
        data = run_query(RIDDER_QUERY, 'ridder')
        if data:
            with open(rpath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            for el in data['elements']:
                if el['type'] == 'relation':
                    t = el.get('tags', {})
                    outer = sum(1 for m in el.get('members', []) if m.get('role') == 'outer')
                    print(f"[ridder] relation {el.get('id')}: name={t.get('name')}, admin_level={t.get('admin_level')}, outer ways={outer}", flush=True)
        else:
            print('[ridder] !!! граница не получена', flush=True)


if __name__ == '__main__':
    main()
