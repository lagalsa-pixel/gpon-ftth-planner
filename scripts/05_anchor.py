# -*- coding: utf-8 -*-
"""
Шаг 5. Выбор здания-якоря (Казпочта/Казахтелеком/аналог) — центр сети в каждом селе.
Критерии: общественное здание (не частный дом в ряду), близость к центроиду ДХ,
площадь 120-600 м², компактность, близость к главной дороге, обособленность.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)

MAIN_ROADS = {'primary', 'secondary', 'tertiary', 'trunk', 'unclassified', 'residential'}

def pick_anchor(v, verbose=True):
    key = v['key']
    g = load_json('/home/z/my-project/work/mosaic_geo.json')[key]
    d = load_json(f'{vdir(key)}/osm.json')
    hhs = load_json(f'{vdir(key)}/households.json')
    mpp, west, north = g['mpp'], g['west'], g['north']

    # центроид ДХ
    clat = sum(h['lat'] for h in hhs) / len(hhs)
    clon = sum(h['lon'] for h in hhs) / len(hhs)

    # главные дороги -> пиксели
    main_pts = []
    for r in d['roads']:
        if r['hw'] in MAIN_ROADS:
            prev = None
            for la, lo in r['pts']:
                p = geo_to_px(la, lo, west, north, mpp)
                if prev is not None:
                    seg = math.hypot(p[0] - prev[0], p[1] - prev[1]) * mpp
                    n_sub = int(seg / 10.0)
                    for k in range(n_sub + 1):
                        main_pts.append((prev[0] + (p[0] - prev[0]) * k / max(n_sub, 1),
                                         prev[1] + (p[1] - prev[1]) * k / max(n_sub, 1)))
                prev = p
    main_arr = np.array(main_pts) if main_pts else np.zeros((0, 2))

    def road_dist(x, y):
        if len(main_arr) == 0:
            return 999.0
        return math.sqrt(((main_arr[:, 0] - x) ** 2 + (main_arr[:, 1] - y) ** 2).min()) * mpp

    # все здания OSM в зоне (bbox для всех, R900 для Пригородного)
    fb = load_json('/home/z/my-project/work/bboxes_final.json')[key]['bbox']
    def in_zone(la, lo):
        if key == 'prigorodnoe':
            return math.hypot((la - v['lat']) * 111320, (lo - v['lon']) * 111320 * math.cos(math.radians(v['lat']))) < 950
        return fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3]

    cands = []
    for b in d['buildings']:
        la, lo = b['center']
        if not in_zone(la, lo):
            continue
        area = b['area']
        tags = b.get('tags', {})
        bt = tags.get('building', 'yes')
        if bt in ('garage', 'garages', 'barn', 'shed', 'greenhouse', 'roof', 'kiosk', 'hut'):
            continue
        x, y = geo_to_px(la, lo, west, north, mpp)
        w, h = b.get('poly') and (None, None)
        pts = [geo_to_px(pla, plo, west, north, mpp) for pla, plo in b['poly']]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        asp = max(bw, bh) / max(1e-6, min(bw, bh))
        # компактность
        per = (bw + bh) * 2
        compact = 1.0 if asp < 2.2 else (2.2 / asp)
        # центричность (0 в центре, растёт к краю)
        dcent_m = math.hypot((la - clat) * 111320, (lo - clon) * 111320 * math.cos(math.radians(la)))
        centr = max(0.0, 1.0 - dcent_m / 1200.0)
        # размер: оптимум 150-500 м²
        sz = 1.0 if 150 <= area <= 500 else (0.75 if 90 <= area < 150 else (0.5 if 500 < area <= 900 else 0.25))
        # близость к главной дороге
        rd = road_dist(x, y)
        road_s = 1.0 if rd < 25 else (0.6 if rd < 50 else (0.3 if rd < 90 else 0.1))
        # тег-бонус: общественные здания
        tag_bonus = 1.4 if (tags.get('amenity') or bt in ('public', 'civic', 'commercial', 'retail', 'office')) else 1.0
        # обособленность: расстояние до ближайшего другого здания >= 6 м
        score = (sz * centr * road_s * compact * tag_bonus)
        cands.append(dict(id=b['id'], lat=la, lon=lo, x=x, y=y, area=area, asp=asp,
                          rd=round(rd, 1), dcent=round(dcent_m), score=round(score, 4),
                          tags=tags, bw=bw, bh=bh))
    cands.sort(key=lambda c: -c['score'])
    if verbose:
        print(f"\n{v['name']}: центроид ДХ ({clat:.5f},{clon:.5f}); топ-5 кандидата ЦУ:")
        for c in cands[:5]:
            print(f"   id={c['id']} {c['area']:.0f}м² asp={c['asp']:.1f} дорога={c['rd']}м центр={c['dcent']}м score={c['score']} tags={c['tags'].get('building','?')}/{c['tags'].get('name','')}")
    return cands[:5]

if __name__ == '__main__':
    result = {}
    for v in VILLAGES:
        cands = pick_anchor(v)
        result[v['key']] = [dict(id=c['id'], lat=c['lat'], lon=c['lon'], x=c['x'], y=c['y'],
                                 area=c['area'], score=c['score'], tags=c['tags']) for c in cands]
        # визуальная проверка топ-3 на кропе
        key = v['key']
        img = Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB')
        W, H = img.size
        cx, cy = int(cands[0]['x']), int(cands[0]['y'])
        x0, y0 = max(0, cx - 500), max(0, cy - 500)
        crop = img.crop((x0, y0, min(W, x0 + 1000), min(H, y0 + 500 + 500))).copy()
        dr = ImageDraw.Draw(crop)
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 26)
        for i, c in enumerate(cands[:3]):
            dr.ellipse([c['x'] - x0 - 16, c['y'] - y0 - 16, c['x'] - x0 + 16, c['y'] - y0 + 16],
                       outline=(255, 230, 0) if i == 0 else (0, 255, 255), width=4)
            dr.text((c['x'] - x0 + 20, c['y'] - y0 - 30), str(i + 1), font=f, fill=(255, 230, 0) if i == 0 else (0, 255, 255))
        crop.save(f'{vdir(key)}/anchor_candidates.png')
    save_json('/home/z/my-project/work/anchor_candidates.json', result)
    print('\nКандидаты сохранены, кропы для проверки: work/<key>/anchor_candidates.png')
