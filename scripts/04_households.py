# -*- coding: utf-8 -*-
"""
Шаг 4. Детекция домохозяйств (ДХ) по каждому селу:
1) OSM-здания (контуры) -> пиксельные координаты
2) CV-детекция крыш на мозаике Google z18 (HSV + морфология)
3) Слияние (дедупликация), кластеризация усадеб (eps=20 м)
4) Сверка с Excel, сохранение households.json
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json, lon2tx, lat2ty
import numpy as np
import cv2
from PIL import Image

def geo_to_px(lat, lon, west, north, mpp):
    x = (lon - west) * (111320 * math.cos(math.radians(lat))) / mpp
    y = (north - lat) * 111320 / mpp
    return x, y

def px_to_geo(x, y, lat_ref, west, north, mpp):
    lon = west + x * mpp / (111320 * math.cos(math.radians(lat_ref)))
    lat = north - y * mpp / 111320
    return lat, lon

def detect_roofs(mos_rgb):
    """Детекция крыш: цветные (синие/красные/оранжевые/зелёные) + светло-серые.
    Возвращает список контуров (px)."""
    hsv = cv2.cvtColor(mos_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    H, W = h.shape
    # цветные крыши
    blue = (h >= 95) & (h <= 130) & (s > 70) & (v > 60)
    red_orange = ((h <= 12) | (h >= 168)) & (s > 80) & (v > 70)
    orange_yellow = (h >= 13) & (h <= 35) & (s > 90) & (v > 110)
    green = (h >= 40) & (h <= 85) & (s > 70) & (v > 60)
    colored = blue | red_orange | orange_yellow | green
    # светло-серые крыши (шифер/профнастил): яркие, малонасыщенные
    grayroof = (s < 45) & (v > 150) & (v < 245)
    mask = colored | grayroof
    # морфология: закрытие мелких дыр, открытие от шума
    m = (mask * 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    res = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 220 or a > 3500:      # ~32-500 м² при 0.38 м/px
            continue
        x, y, w_, h_ = cv2.boundingRect(c)
        if w_ < 9 or h_ < 9:          # ~3.4 м минимум
            continue
        fill = a / (w_ * h_)
        asp = max(w_, h_) / max(1, min(w_, h_))
        if fill < 0.42 or asp > 4.5:
            continue
        res.append((x + w_ / 2, y + h_ / 2, w_, h_, a))
    return res

def main():
    geo_all = load_json('/home/z/my-project/work/mosaic_geo.json')
    summary = {}
    for v in VILLAGES:
        key = v['key']
        g = geo_all[key]
        mpp = g['mpp']; west, north = g['west'], g['north']
        d = load_json(f'{vdir(key)}/osm.json')
        mos = np.asarray(Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB'))
        H, W = mos.shape[:2]

        # OSM-здания -> px
        osm_blds = []
        for b in d['buildings']:
            pts = [geo_to_px(la, lo, west, north, mpp) for la, lo in b['poly']]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if min(xs) < -50 or min(ys) < -50 or max(xs) > W + 50 or max(ys) > H + 50:
                continue
            osm_blds.append(dict(cx=(min(xs)+max(xs))/2, cy=(min(ys)+max(ys))/2,
                                 w=max(xs)-min(xs), h=max(ys)-min(ys), area=b['area'],
                                 osm_id=b['id'], tags=b.get('tags', {})))
        # CV-детекция
        roofs = detect_roofs(mos)
        # дедупликация: CV-крыша в пределах 4 м (10-11 px) от OSM-здания -> уже известно
        def near_osm(x, y, r=11):
            for b in osm_blds:
                if abs(x - b['cx']) < b['w']/2 + r and abs(y - b['cy']) < b['h']/2 + r:
                    return True
            return False
        new_roofs = [r for r in roofs if not near_osm(r[0], r[1])]
        # отбраковка CV-хлопьев: слишком плотные скопления мелких цветных пятен = техника/мусор во дворах?
        # оставляем как есть — кластеризация усадеб сгладит
        all_blds = ([dict(cx=b['cx'], cy=b['cy'], w=b['w'], h=b['h'], src='osm', tags=b['tags'])
                     for b in osm_blds] +
                    [dict(cx=r[0], cy=r[1], w=r[2], h=r[3], src='cv') for r in new_roofs])
        # кластеризация усадеб: объединение зданий в радиусе 20 м (52 px)
        eps = 20.0 / mpp
        used = [False] * len(all_blds)
        yards = []
        idxs = sorted(range(len(all_blds)), key=lambda i: -all_blds[i]['w'] * all_blds[i]['h'])
        for i in idxs:
            if used[i]:
                continue
            queue, yard = [i], []
            used[i] = True
            while queue:
                j = queue.pop()
                yard.append(j)
                for k in range(len(all_blds)):
                    if used[k]:
                        continue
                    dx = all_blds[k]['cx'] - all_blds[j]['cx']
                    dy = all_blds[k]['cy'] - all_blds[j]['cy']
                    if dx * dx + dy * dy < eps * eps:
                        used[k] = True
                        queue.append(k)
            yards.append(yard)
        households = []
        for yi, yard in enumerate(yards):
            bl = [all_blds[j] for j in yard]
            # главное здание: максимум площади bbox, приоритет OSM с тегом building=house/yes
            best = max(bl, key=lambda b: b['w'] * b['h'] * (1.5 if b['src'] == 'osm' else 1.0))
            cx = sum(b['cx'] for b in bl) / len(bl)
            cy = sum(b['cy'] for b in bl) / len(bl)
            la, lo = px_to_geo(best['cx'], best['cy'], v['lat'], west, north, mpp)
            households.append(dict(id=yi + 1, cx=best['cx'], cy=best['cy'], yx=cx, yy=cy,
                                   lat=la, lon=lo, n_bld=len(bl), main_w=best['w'], main_h=best['h'],
                                   main_src=best['src']))
        n_osm = len(osm_blds); n_cv = len(new_roofs)
        summary[key] = dict(name=v['name'], expected=v['hh'], osm_bld=n_osm, cv_new=n_cv,
                            households=len(households))
        print(f"{v['name']}: OSM {n_osm} + CV {n_cv} зданий -> {len(households)} ДХ (Excel: {v['hh']}, отклонение {100*(len(households)-v['hh'])/v['hh']:+.1f}%)")
        save_json(f'{vdir(key)}/households.json', households)
    save_json('/home/z/my-project/work/hh_summary.json', summary)

if __name__ == '__main__':
    main()
