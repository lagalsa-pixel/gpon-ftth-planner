# -*- coding: utf-8 -*-
"""
Шаг 1. Загрузка OSM-данных (дороги, здания, POI) по 6 СНП через api.openstreetmap.org/api/0.6/map.
Чанками ~2x2 км, с дедупликацией. Расчёт bbox застройки (+300 м) для последующей загрузки снимков.
"""
import sys, os, math, json, time
import xml.etree.ElementTree as ET
import requests
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, HDRS, vdir, save_json, WORK

OSM_API = "https://api.openstreetmap.org/api/0.6/map"

# Ручные корректировки bbox (lon_min, lat_min, lon_max, lat_max) при необходимости
OVERRIDE_BBOX = {
    # 'prigorodnoe': (83.49, 50.31, 83.55, 50.335),
}

def meters_to_deg(m, lat):
    dlat = m / 111320.0
    dlon = m / (111320.0 * math.cos(math.radians(lat)))
    return dlat, dlon

def fetch_bbox(lon_min, lat_min, lon_max, lat_max, tag):
    p = f'{WORK}/osm_raw/{tag}_{lon_min:.4f}_{lat_min:.4f}_{lon_max:.4f}_{lat_max:.4f}.xml'
    os.makedirs(f'{WORK}/osm_raw', exist_ok=True)
    if os.path.exists(p) and os.path.getsize(p) > 100:
        with open(p, 'rb') as f:
            return f.read()
    for attempt in range(4):
        try:
            r = requests.get(OSM_API, params={'bbox': f'{lon_min:.6f},{lat_min:.6f},{lon_max:.6f},{lat_max:.6f}'},
                             headers=HDRS, timeout=120)
            if r.status_code == 200:
                with open(p, 'wb') as f:
                    f.write(r.content)
                return r.content
            if r.status_code == 400:
                print('   bbox слишком велик, скип'); return None
            print(f'   HTTP {r.status_code}, повтор...')
        except Exception as e:
            print(f'   {str(e)[:70]}, повтор...')
        time.sleep(3 * (attempt + 1))
    return None

def parse_osm(xml_bytes):
    """-> nodes{id:(lat,lon,tags)}, ways{id:(nd_refs, tags)}"""
    root = ET.fromstring(xml_bytes)
    nodes, ways = {}, {}
    for n in root.iter('node'):
        tags = {t.get('k'): t.get('v') for t in n.findall('tag')}
        nodes[int(n.get('id'))] = (float(n.get('lat')), float(n.get('lon')), tags)
    for w in root.iter('way'):
        tags = {t.get('k'): t.get('v') for t in w.findall('tag')}
        nds = [int(nd.get('ref')) for nd in w.findall('nd')]
        ways[int(w.get('id'))] = (nds, tags)
    return nodes, ways

ROAD_KEYS = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
             'residential', 'living_street', 'service', 'track', 'road', 'pedestrian'}
# дороги, образующие уличную сеть села (для bbox застройки)
URBAN_ROADS = {'residential', 'living_street', 'service', 'unclassified', 'road', 'tertiary', 'secondary'}

def main():
    summary = {}
    for v in VILLAGES:
        key = v['key']
        print(f"=== {v['name']} ({v['hh']} ДХ) ===")
        if key in OVERRIDE_BBOX:
            bbox = OVERRIDE_BBOX[key]
        else:
            side = v['rng'] + 900.0  # м, зондажная область
            dlat, dlon = meters_to_deg(side / 2, v['lat'])
            bbox = (v['lon'] - dlon, v['lat'] - dlat, v['lon'] + dlon, v['lat'] + dlat)

        # чанки ~2.1 км
        n_split = max(1, int(math.ceil((bbox[2] - bbox[0]) * 111320 * math.cos(math.radians(v['lat'])) / 2100)))
        m_split = max(1, int(math.ceil((bbox[3] - bbox[1]) * 111320 / 2100)))
        nodes, ways = {}, {}
        for i in range(n_split):
            for j in range(m_split):
                x0 = bbox[0] + (bbox[2] - bbox[0]) * i / n_split
                x1 = bbox[0] + (bbox[2] - bbox[0]) * (i + 1) / n_split
                y0 = bbox[1] + (bbox[3] - bbox[1]) * j / m_split
                y1 = bbox[1] + (bbox[3] - bbox[1]) * (j + 1) / m_split
                data = fetch_bbox(x0, y0, x1, y1, key)
                if not data:
                    continue
                n2, w2 = parse_osm(data)
                nodes.update(n2); ways.update(w2)
                print(f'   чанк {i},{j}: +{len(n2)} узлов, +{len(w2)} путей')
                time.sleep(0.4)

        # фильтрация
        roads = []        # {id, pts:[[lat,lon]..], hw, name}
        buildings = []    # {id, poly:[[lat,lon]..], tags, center, area}
        pois = []
        for wid, (nds, tags) in ways.items():
            hw = tags.get('highway')
            bld = tags.get('building')
            if hw and hw in ROAD_KEYS and len(nds) >= 2:
                pts = [(nodes[r][0], nodes[r][1]) for r in nds if r in nodes]
                if len(pts) >= 2:
                    roads.append(dict(id=wid, pts=pts, hw=hw, name=tags.get('name', '')))
            if bld and bld not in ('no',) and len(nds) >= 4:
                pts = [(nodes[r][0], nodes[r][1]) for r in nds if r in nodes]
                if len(pts) >= 4:
                    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
                    # площадь (шоelace, м²)
                    a = 0.0
                    for k in range(len(pts)):
                        x1p, y1p = pts[k]; x2p, y2p = pts[(k + 1) % len(pts)]
                        a += (x2p * 111320 * math.cos(math.radians(cy)) if False else 0)  # заглушка ниже
                    a = 0.0
                    for k in range(len(pts)):
                        la1, lo1 = pts[k]; la2, lo2 = pts[(k + 1) % len(pts)]
                        mx = 111320 * math.cos(math.radians(cy))
                        x1p, y1p = lo1 * mx, la1 * 111320
                        x2p, y2p = lo2 * mx, la2 * 111320
                        a += x1p * y2p - x2p * y1p
                    area = abs(a) / 2
                    buildings.append(dict(id=wid, poly=pts, center=[cx, cy], area=round(area, 1),
                                          tags={k: tags[k] for k in ('building', 'name', 'amenity', 'shop', 'office', 'height', 'building:levels') if k in tags}))
            # POI-точки (и точки-ноды тоже добавим ниже)
            if (tags.get('amenity') or tags.get('office') or tags.get('shop')) and not bld:
                if nds and nds[0] in nodes:
                    la, lo, _ = nodes[nds[0]]
                    pois.append(dict(id=wid, lat=la, lon=lo, tags={k: tags[k] for k in ('amenity', 'office', 'shop', 'name') if k in tags}))
        for nid, (la, lo, tags) in nodes.items():
            if (tags.get('amenity') or tags.get('office')) and (tags.get('amenity') in ('post_office', 'bank', 'townhall', 'police', 'clinic', 'telephone') or tags.get('office') in ('telecom', 'government')):
                pois.append(dict(id=nid, lat=la, lon=lo, tags={k: tags[k] for k in ('amenity', 'office', 'name') if k in tags}))

        # bbox застройки: городские дороги + здания, сетка 50 м, компонента вокруг центра
        feats = []
        for r in roads:
            if r['hw'] in URBAN_ROADS:
                feats.extend(r['pts'])
        feats.extend([b['center'] for b in buildings])
        if feats:
            lats = [p[0] for p in feats]; lons = [p[1] for p in feats]
            # сетка
            gs = 50.0
            dlat_c = gs / 111320.0
            dlon_c = gs / (111320.0 * math.cos(math.radians(v['lat'])))
            cells = {}
            for la, lo in feats:
                cells.setdefault((int(math.floor((la - min(lats)) / dlat_c)), int(math.floor((lo - min(lons)) / dlon_c))), 0)
                cells[(int(math.floor((la - min(lats)) / dlat_c)), int(math.floor((lo - min(lons)) / dlon_c)))] += 1
            filled = {c for c, n in cells.items() if n >= 2}
            # связность (BFS по 8-соседям), ищем компоненту, содержащую ячейку центра
            def cell_of(la, lo):
                return (int(math.floor((la - min(lats)) / dlat_c)), int(math.floor((lo - min(lons)) / dlon_c)))
            start = cell_of(v['lat'], v['lon'])
            seen, comp = set(), set()
            stack = [start] if start in filled else [next(iter(filled))]
            while stack:
                c = stack.pop()
                if c in seen or c not in filled:
                    continue
                seen.add(c); comp.add(c)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        stack.append((c[0] + dx, c[1] + dy))
            # bbox компоненты + 300 м
            cl = [c for c in comp]
            rmin = min(c[0] for c in cl); rmax = max(c[0] for c in cl)
            cmin = min(c[1] for c in cl); cmax = max(c[1] for c in cl)
            lat_min = min(lats) + rmin * dlat_c - 300 / 111320.0
            lat_max = min(lats) + (rmax + 1) * dlat_c + 300 / 111320.0
            lon_min = min(lons) + cmin * dlon_c - 300 / (111320.0 * math.cos(math.radians(v['lat'])))
            lon_max = min(lons) + (cmax + 1) * dlon_c + 300 / (111320.0 * math.cos(math.radians(v['lat'])))
            fb = (max(lon_min, bbox[0]), max(lat_min, bbox[1]), min(lon_max, bbox[2]), min(lat_max, bbox[3]))
        else:
            fb = bbox

        w_km = (fb[2] - fb[0]) * 111320 * math.cos(math.radians(v['lat'])) / 1000
        h_km = (fb[3] - fb[1]) * 111320 / 1000
        print(f"  дорог: {len(roads)}, зданий: {len(buildings)}, POI: {len(pois)}")
        print(f"  bbox застройки: {fb[0]:.4f},{fb[1]:.4f} - {fb[2]:.4f},{fb[3]:.4f}  ({w_km:.2f} x {h_km:.2f} км)")

        save_json(f'{vdir(key)}/osm.json', dict(
            bbox=list(fb), roads=roads, buildings=buildings, pois=pois, center=[v['lat'], v['lon']]))
        summary[key] = dict(name=v['name'], roads=len(roads), buildings=len(buildings),
                            pois=len(pois), bbox=list(fb), w_km=round(w_km, 2), h_km=round(h_km, 2))
        time.sleep(1.0)

    save_json(f'{WORK}/osm_summary.json', summary)
    print('\nИТОГО:')
    for k, s in summary.items():
        print(f"  {s['name']}: {s['roads']} дорог, {s['buildings']} зданий, {s['w_km']}x{s['h_km']} км")

if __name__ == '__main__':
    main()
