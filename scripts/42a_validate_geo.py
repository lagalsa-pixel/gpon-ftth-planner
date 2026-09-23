# -*- coding: utf-8 -*-
"""
Шаг 42a. Валидация преобразования px мозаики -> WGS84 (точный Web Mercator).

Мозаика (work/<key>/mosaic.jpg) обрезана точно по bbox: пиксель (0,0) =
(west, north) из mosaic_geo.json. Проверка: якорь сети (OSM-здание с
lat/lon) переводим из px в geo тремя способами и сравниваем:
  1) точный Web Mercator (обратная тайловая математика z18);
  2) аффинная модель шага 05 (111320, mpp);
  3) аффинная модель шага 29 (110574) — как считались lat/lon зон в boq.
"""
import json, math, sys

BASE = '/home/z/my-project'
sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty, tx2lon, ty2lat  # noqa: E402

Z = 18
GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))


def px_to_geo_exact(key, x, y):
    """Точный Web Mercator: пиксель мозаики -> (lat, lon) WGS84."""
    g = GEO[key]
    tx0f = lon2tx(g['west'], Z)          # дробный тайл west-края
    ty0f = lat2ty(g['north'], Z)         # дробный тайл north-края
    gx = tx0f * 256.0 + x                # глобальный пиксель z18
    gy = ty0f * 256.0 + y
    lon = gx / 256.0 / (1 << Z) * 360.0 - 180.0
    lat = ty2lat(gy / 256.0, Z)
    return lat, lon


def m_at_lat(lat):
    """Метры на градус (сфера R=6378137, как в Web Mercator)."""
    return 111319.49079327358


for key in ['prigorodnoe', 'verhneberezovka', 'vinnoe']:
    g = GEO[key]
    import importlib.util
    spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
    de28 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(de28)
    vinfo = next(v for v in de28.VILLAGES if v['key'] == key)
    net = json.load(open(f'{BASE}/work/{key}/{vinfo["net"]}'))
    a = net['anchor']
    ax, ay, alat, alon = a['x'], a['y'], a['lat'], a['lon']
    mpp = g['mpp']

    # 1) точный Web Mercator
    lat_e, lon_e = px_to_geo_exact(key, ax, ay)
    # 2) аффинная 05 (111320)
    lat_5 = g['north'] - ay * mpp / 111320.0
    lon_5 = g['west'] + ax * mpp / (111320.0 * math.cos(math.radians(alat)))
    # 3) аффинная 29 (110574, от якоря)
    lat_29 = alat - (ay - ay) * mpp / 110574.0  # тривиально = alat (сам якорь)

    d = lambda la, lo: math.hypot((la - alat) * 111319.49,
                                   (lo - alon) * 111319.49 * math.cos(math.radians(alat)))
    print(f'== {key} ==  anchor OSM: {alat:.6f}, {alon:.6f}  px=({ax:.1f},{ay:.1f})')
    print(f'  exact WebMerc : {lat_e:.6f}, {lon_e:.6f}   откл {d(lat_e, lon_e):6.1f} м')
    print(f'  affine 111320 : {lat_5:.6f}, {lon_5:.6f}   откл {d(lat_5, lon_5):6.1f} м')

    # зона из boq (lat/lon считались аффинной 110574 от якоря)
    boq = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
    v = next(v for v in boq['villages'] if v['key'] == key)
    for z in v['zones'][1:3]:
        zx, zy = z['px']
        lat_x, lon_x = px_to_geo_exact(key, zx, zy)
        dz = math.hypot((lat_x - z['lat']) * 111319.49,
                        (lon_x - z['lon']) * 111319.49 * math.cos(math.radians(z['lat'])))
        print(f'  зона {zx:.0f},{zy:.0f}: boq {z["lat"]:.6f},{z["lon"]:.6f} | '
              f'exact {lat_x:.6f},{lon_x:.6f} | d={dz:.1f} м (root_dist {z["root_dist_m"]:.0f} м)')
