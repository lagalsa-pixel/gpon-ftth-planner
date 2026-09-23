#!/usr/bin/env python3
"""Определение домохозяйств по OSM-застройке.
Этапы: парсинг зданий -> выделение зоны села (single-linkage 350 м, якорный кластер;
для Пригородного — исключение границы Риддера + радиус 1400 м) -> группировка построек
двора в домохозяйства (калибровка порога по официальному числу ДХ)."""
import json, math, os, sys
from collections import defaultdict
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OSM_DIR = os.path.join(BASE, 'osm_ftth')
OUT_DIR = os.path.join(BASE, 'ftth_out')
os.makedirs(OUT_DIR, exist_ok=True)

VILLAGES = [
    dict(key='verkhneberezovka', name='Верхнеберезовка', district='Глубоковский район', okrug='Верхнеберезовский с.о.', lat=50.28420545, lon=82.20951200, expected=940, special=None, radius=None),
    dict(key='solnechnoe',       name='Солнечное',       district='Глубоковский район', okrug='Бобровский с.о.',        lat=50.05177550, lon=82.71438134, expected=366, special=None, radius=None),
    dict(key='perevalnoe',       name='Перевальное',     district='Глубоковский район', okrug='Красноярский с.о.',      lat=50.24139084, lon=82.28314297, expected=339, special=None, radius=None),
    dict(key='vinnoe',           name='Винное',          district='Глубоковский район', okrug='Тарханский с.о.',        lat=50.05844487, lon=82.82687999, expected=490, special=None, radius=None),
    dict(key='prigorodnoe',      name='Пригородное',     district='г. Риддер',          okrug='',                       lat=50.32198100, lon=83.52094976, expected=365, special='ridder', radius=None),
    dict(key='altayskiy',        name='Алтайский',       district='Глубоковский район', okrug='Алтайский с.о.',         lat=50.24399825, lon=82.36103064, expected=716, special=None, radius=None),
]

EXCLUDE_TAGS = {
    'garages', 'garage', 'shed', 'barn', 'roof', 'industrial', 'warehouse', 'commercial',
    'retail', 'office', 'public', 'civic', 'school', 'kindergarten', 'hospital', 'clinic',
    'church', 'mosque', 'chapel', 'ruins', 'construction', 'greenhouse', 'stable',
    'cowshed', 'container', 'carport', 'bunker', 'silo', 'service', 'technical',
    'transformer_tower', 'kiosk', 'train_station', 'fire_station', 'government',
    'farm_auxiliary', 'hangar', 'storage_tank', 'tower', 'chimney', 'digester',
}
APARTMENT_TAGS = {'apartments', 'dormitory'}
RESIDENTIAL_TAGS = {
    'house', 'yes', 'detached', 'semidetached_house', 'semi_detached_house', 'bungalow',
    'hut', 'residential', 'farm', 'allotment_house', 'terrace', 'cabin', 'static_caravan',
}

MAX_MAIN_AREA = 800.0   # м2: крупнее — хоз. корпус, не главный жилой дом
MIN_AREA = 8.0          # м2: мельче — мелкая постройка (колодец и т.п.)
ZONE_CLUSTER_THR = 350.0  # м: кластеризация застройки для выделения села
# радиусные ограничения зоны (для отсечения дачных массивов / городской застройки)
RADIUS = {
    'solnechnoe': 2000.0,
    'prigorodnoe': 1080.0,
}
# полигоны застройки села Пригородное (остальные residential-полигоны — город Риддер)
PRIGORODNOE_VILLAGE_POLY_IDS = {1338095842, 919956284}


def local_frame(lat0):
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(lat0))
    return ky, kx


def single_linkage(xy, thr):
    """Метlabels single-linkage по порогу расстояния. xy: (n,2) в метрах."""
    n = len(xy)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    if n > 1:
        d2 = thr * thr
        step = 256
        for i0 in range(0, n, step):
            chunk = xy[i0:i0 + step]
            dd = ((xy[None, :, :] - chunk[:, None, :]) ** 2).sum(-1)
            ii, jj = np.where(dd <= d2)
            for a, b in zip(ii, jj):
                union(i0 + int(a), int(b))
    return [find(i) for i in range(n)]


def parse_buildings(data, ky, kx):
    blds = []
    for el in data['elements']:
        if el['type'] != 'way' or 'geometry' not in el:
            continue
        t = el.get('tags', {})
        tag = t.get('building')
        if tag is None:
            continue
        pts = [(p['lat'], p['lon']) for p in el['geometry']]
        if len(pts) < 3:
            continue
        # замыкаем при необходимости
        if pts[0] != pts[-1]:
            pts = pts + [pts[0]]
        # площадь (shoelace в локальных метрах) и центроид
        cx = cy = 0.0
        a2 = 0.0
        for (la1, lo1), (la2, lo2) in zip(pts[:-1], pts[1:]):
            x1, y1 = lo1 * kx, la1 * ky
            x2, y2 = lo2 * kx, la2 * ky
            cr = x1 * y2 - x2 * y1
            a2 += cr
            cx += (x1 + x2) * cr
            cy += (y1 + y2) * cr
        area = abs(a2) / 2.0
        if area > 1e-6:
            cx /= 3.0 * a2
            cy /= 3.0 * a2
        else:
            cx = sum(p[1] for p in pts[:-1]) / (len(pts) - 1) * kx
            cy = sum(p[0] for p in pts[:-1]) / (len(pts) - 1) * ky
        lat_c, lon_c = cy / ky, cx / kx
        blds.append(dict(
            id=el['id'], tag=tag, area=area, lat=lat_c, lon=lon_c,
            poly=pts[:-1], levels=t.get('building:levels'),
        ))
    return blds


def point_in_ring(lat, lon, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat):
            x_int = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_int:
                inside = not inside
        j = i
    return inside


def load_ridder_rings():
    """Кольца: адм. граница Риддер-акимата; полигоны городской застройки Риддера
    (residential, кроме села Пригородное) и дачные массивы (allotments)."""
    path = os.path.join(OSM_DIR, 'ridder.json')
    outers, inners = [], []
    if os.path.exists(path):
        data = json.load(open(path))
        for el in data['elements']:
            if el.get('type') != 'relation':
                continue
            segs_o, segs_i = [], []
            for m in el.get('members', []):
                if m.get('type') == 'way' and m.get('geometry'):
                    pts = [(p['lat'], p['lon']) for p in m['geometry']]
                    if len(pts) >= 2:
                        (segs_o if m.get('role') == 'outer' else segs_i).append(pts)

        def assemble(segs):
            rings = []
            used = [False] * len(segs)
            def key(p):
                return (round(p[0], 7), round(p[1], 7))
            for i, s in enumerate(segs):
                if used[i]:
                    continue
                used[i] = True
                ring = list(s)
                guard = 0
                while key(ring[0]) != key(ring[-1]) and guard < 500:
                    guard += 1
                    changed = False
                    for j, t in enumerate(segs):
                        if used[j]:
                            continue
                        if key(t[0]) == key(ring[-1]):
                            ring.extend(t[1:]); used[j] = True; changed = True; break
                        if key(t[-1]) == key(ring[-1]):
                            ring.extend(list(reversed(t))[1:]); used[j] = True; changed = True; break
                        if key(t[-1]) == key(ring[0]):
                            ring = list(t[:-1]) + ring; used[j] = True; changed = True; break
                        if key(t[0]) == key(ring[0]):
                            ring = list(reversed(t))[:-1] + ring; used[j] = True; changed = True; break
                    if not changed:
                        break
                if key(ring[0]) == key(ring[-1]) and len(ring) >= 4:
                    rings.append(ring[:-1])
            return rings

        outers += assemble(segs_o)
        inners += assemble(segs_i)
    # полигоны застройки: городские residential (Риддер) и дачные allotments
    city_rings, allot_rings = [], []
    ppath = os.path.join(OSM_DIR, 'prigorodnoe_landuse.json')
    if os.path.exists(ppath):
        pdata = json.load(open(ppath))
        for el in pdata['elements']:
            if el.get('type') != 'way' or 'geometry' not in el:
                continue
            pts = [(p['lat'], p['lon']) for p in el['geometry']]
            if len(pts) < 4 or pts[0] != pts[-1]:
                continue
            ring = pts[:-1]
            lu = el.get('tags', {}).get('landuse')
            if lu == 'allotments':
                allot_rings.append(ring)
            elif lu == 'residential' and el.get('id') not in PRIGORODNOE_VILLAGE_POLY_IDS:
                city_rings.append(ring)
    return outers, inners, city_rings, allot_rings


def in_ridder(lat, lon, outers, inners):
    if any(point_in_ring(lat, lon, r) for r in outers):
        if not any(point_in_ring(lat, lon, r) for r in inners):
            return True
    return False


def zone_buildings(v, blds, ky, kx, outers, inners, city_rings, allot_rings, radius=None):
    """Индексы зданий зоны села."""
    n = len(blds)
    xy = np.array([[b['lat'] * ky, b['lon'] * kx] for b in blds])
    axy = np.array([v['lat'] * ky, v['lon'] * kx])
    if v['special'] == 'ridder':
        # село у Риддера: радиус от якоря + исключение городской/дачной застройки
        keep = []
        for i, b in enumerate(blds):
            d = math.hypot(*(xy[i] - axy))
            if d > (radius if radius else 1e9):
                continue
            if any(point_in_ring(b['lat'], b['lon'], r) for r in city_rings):
                continue
            if any(point_in_ring(b['lat'], b['lon'], r) for r in allot_rings):
                continue
            keep.append(i)
        cand = keep
    else:
        cand = list(range(n))
    if not cand:
        return [], []
    cxy = xy[cand]
    labels = single_linkage(cxy, ZONE_CLUSTER_THR)
    # кластер, содержащий здание, ближайшее к якорю
    best_i, best_d = None, 1e18
    for i in cand:
        d = math.hypot(*(xy[i] - axy))
        if d < best_d:
            best_d, best_i = d, i
    target_label = labels[cand.index(best_i)]
    zone = [cand[k] for k in range(len(cand)) if labels[k] == target_label]
    # радиусный кап (для отсечения цепочек дачных массивов)
    if radius and v['special'] != 'ridder':
        zone = [i for i in zone if math.hypot(*(xy[i] - axy)) <= radius]
    return zone, labels


def make_households(zone_blds, thr, ky, kx):
    """Группировка построек в домохозяйства. Возвращает список ДХ."""
    res = [b for b in zone_blds if b['tag'] not in EXCLUDE_TAGS]
    lows = [b for b in res if b['tag'] in RESIDENTIAL_TAGS]
    aparts = [b for b in res if b['tag'] in APARTMENT_TAGS]
    households = []
    if lows:
        xy = np.array([[b['lat'] * ky, b['lon'] * kx] for b in lows])
        labels = single_linkage(xy, thr)
        groups = defaultdict(list)
        for b, lb in zip(lows, labels):
            groups[lb].append(b)
        for g in groups.values():
            main = max(g, key=lambda b: b['area'] if b['area'] <= MAX_MAIN_AREA else -1) \
                if any(b['area'] <= MAX_MAIN_AREA for b in g) else max(g, key=lambda b: b['area'])
            households.append(dict(
                type='house', lat=main['lat'], lon=main['lon'],
                polygons=[b['poly'] for b in g],
                main_area=main['area'], n_bld=len(g),
            ))
    for b in aparts:
        households.append(dict(
            type='mkd', lat=b['lat'], lon=b['lon'], polygons=[b['poly']],
            main_area=b['area'], n_bld=1,
        ))
    return households


def main():
    calibrate = '--calib' in sys.argv
    calib_radius = '--calib-radius' in sys.argv
    outers, inners, city_rings, allot_rings = load_ridder_rings()
    print(f'Риддер: адм. outer-колец {len(outers)}, городских residential-полигонов {len(city_rings)}, дачных {len(allot_rings)}')

    results = {}
    for v in VILLAGES:
        data = json.load(open(os.path.join(OSM_DIR, f"{v['key']}.json")))
        ky, kx = local_frame(v['lat'])
        blds = parse_buildings(data, ky, kx)

        if calib_radius:
            if v['key'] not in ('solnechnoe', 'prigorodnoe'):
                continue
            radii = [1600, 1800, 2000, 2200, 2400, 2600] if v['key'] == 'solnechnoe' else \
                    [800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1700]
            print(f"=== {v['name']} (ожид. {v['expected']} ДХ): калибровка радиуса")
            for R in radii:
                zone, _ = zone_buildings(v, blds, ky, kx, outers, inners, city_rings, allot_rings, radius=R)
                zb = [blds[i] for i in zone]
                if not zb:
                    print(f'    R={R} м: пусто')
                    continue
                hh18 = make_households(zb, 18.0, ky, kx)
                lats = [b['lat'] for b in zb]; lons = [b['lon'] for b in zb]
                print(f"    R={R} м: зданий {len(zb)}, ДХ@18м {len(hh18)}, "
                      f"зона {(max(lons)-min(lons))*kx:.0f}x{(max(lats)-min(lats))*ky:.0f} м")
            continue

        radius = RADIUS.get(v['key'])
        zone, labels = zone_buildings(v, blds, ky, kx, outers, inners, city_rings, allot_rings, radius=radius)
        zb = [blds[i] for i in zone]
        if not zb:
            print(f"=== {v['name']}: ПУСТАЯ ЗОНА — проверить правила!")
            continue
        lats = [b['lat'] for b in zb]
        lons = [b['lon'] for b in zb]
        w_m = (max(lons) - min(lons)) * kx
        h_m = (max(lats) - min(lats)) * ky
        print(f"=== {v['name']}: зданий всего {len(blds)}, в зоне села {len(zb)}"
              + (f" (R={radius} м)" if radius else ""))
        print(f"    зона: {w_m:.0f} x {h_m:.0f} м (+300 м буфер -> итоговый кадр)")
        from collections import Counter as _C
        print(f"    теги зоны: {dict(sorted(_C(b['tag'] for b in zb).items(), key=lambda x: -x[1])[:6])}")

        if calibrate:
            line = '    порог ДХ:'
            for thr in (10, 14, 18, 22, 26, 30):
                hh = make_households(zb, thr, ky, kx)
                line += f'  {thr}м->{len(hh)}'
            print(line + f'  (ожид. {v["expected"]})')

        results[v['key']] = dict(v=v, zone_blds=zb, ky=ky, kx=kx)

    if calibrate and results:
        print('\n=== сводка ошибок по порогам (|det-exp|/exp, среднее по сёлам):')
        for thr in (10, 14, 18, 22, 26, 30):
            errs = []
            for k, r in results.items():
                hh = make_households(r['zone_blds'], thr, r['ky'], r['kx'])
                errs.append(abs(len(hh) - r['v']['expected']) / r['v']['expected'])
            print(f'    {thr} м: средняя ошибка {sum(errs)/len(errs)*100:.1f}%')
        return
    if calib_radius:
        return

    # рабочий порог (после калибровки)
    THR = float(os.environ.get('HH_THR', '18'))
    for k, r in results.items():
        v = r['v']
        hh = make_households(r['zone_blds'], THR, r['ky'], r['kx'])
        hh.sort(key=lambda h: (h['lon'], h['lat']))
        for i, h in enumerate(hh, 1):
            h['n'] = i
        # итоговый bbox: жилая застройка + 300 м буфер
        clats = [h['lat'] for h in hh]
        clons = [h['lon'] for h in hh]
        buf_lat = 300.0 / r['ky']
        buf_lon = 300.0 / r['kx']
        bbox = [min(clats) - buf_lat, min(clons) - buf_lon, max(clats) + buf_lat, max(clons) + buf_lon]
        out = dict(
            key=v['key'], name=v['name'], district=v['district'], okrug=v['okrug'],
            expected=v['expected'], anchor=[v['lat'], v['lon']],
            bbox=bbox, hh_thr=THR, n_buildings_zone=len(r['zone_blds']),
            households=hh,
        )
        with open(os.path.join(OUT_DIR, f"{v['key']}_hh.json"), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
        cov = len(hh) / v['expected'] * 100
        print(f"    -> домохозяйств: {len(hh)} (официально {v['expected']}, покрытие OSM {cov:.0f}%), сохранено {v['key']}_hh.json")


if __name__ == '__main__':
    main()
