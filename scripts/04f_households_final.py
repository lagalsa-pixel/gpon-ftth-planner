# -*- coding: utf-8 -*-
"""
Шаг 4f. Финальная детекция домохозяйств:
- OSM-здания в зоне села (Пригородное: R=900 м от центра Excel; остальные: bbox)
- CV-суплемент (строгий) только для: verhneberezovka, perevalnoe, altaiskiy
- Кластеризация усадеб eps=16 м; двор должен иметь здание >=36 м² и быть <=60 м от дороги
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json
import numpy as np
import cv2
from PIL import Image

CV_SUPPLEMENT = {'verhneberezovka', 'perevalnoe', 'altaiskiy'}
EPS_M = 16.0          # радиус кластеризации усадьбы
ROAD_MAX_M = 60.0     # двор не дальше от дороги
NEAR_RD_M = 75.0      # CV-кандидат ближе к дороге
CTX_M = 90.0          # контекст: другой объект в радиусе
OSM_MIN_SEP_M = 15.0  # CV не ближе к OSM-зданию

def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)

def px_to_geo(x, y, lat_ref, west, north, mpp):
    return (north - y * mpp / 111320,
            west + x * mpp / (111320 * math.cos(math.radians(lat_ref))))

def detect_roofs(mos_rgb, loose=False):
    hsv = cv2.cvtColor(mos_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    blue = (h >= 90) & (h <= 132) & (s > 65) & (v > 50)
    red = ((h <= 12) | (h >= 168)) & (s > 75) & (v > 55)
    orange = (h >= 13) & (h <= 35) & (s > 85) & (v > 95)
    green = (h >= 40) & (h <= 85) & (s > 65) & (v > 50)
    gray = (s < 50) & (v > (125 if loose else 140)) & (v < 248)
    dark = (s < 40) & (v > 85) & (v <= 125)   # тёмные крыши (мягкая кровля)
    mask = blue | red | orange | green | gray | (dark if loose else False)
    m = (mask * 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    res = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 280 or a > 2400:
            continue
        x, y, w_, h_ = cv2.boundingRect(c)
        if w_ < 10 or h_ < 10:
            continue
        if a / (w_ * h_) < (0.45 if loose else 0.5) or max(w_, h_) / max(1, min(w_, h_)) > 4.0:
            continue
        res.append((x + w_ / 2, y + h_ / 2, w_, h_))
    return res

def dist_px(p, q, mpp):
    return math.hypot(p[0] - q[0], p[1] - q[1]) * mpp

def main():
    geo_all = load_json('/home/z/my-project/work/mosaic_geo.json')
    summary = {}
    for v in VILLAGES:
        key = v['key']
        g = geo_all[key]
        mpp, west, north = g['mpp'], g['west'], g['north']
        d = load_json(f'{vdir(key)}/osm.json')
        fb = load_json('/home/z/my-project/work/bboxes_final.json')[key]['bbox']
        mos = np.asarray(Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB'))
        H, W = mos.shape[:2]

        # --- OSM-здания в зоне ---
        def in_zone(la, lo):
            if key == 'prigorodnoe':
                return math.hypot((la - v['lat']) * 111320,
                                  (lo - v['lon']) * 111320 * math.cos(math.radians(v['lat']))) < 900
            return fb[0] <= lo <= fb[2] and fb[1] <= la <= fb[3]

        osm_blds = []
        for b in d['buildings']:
            la, lo = b['center']
            if not in_zone(la, lo):
                continue
            pts = [geo_to_px(pla, plo, west, north, mpp) for pla, plo in b['poly']]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if min(xs) < -80 or min(ys) < -80 or max(xs) > W + 80 or max(ys) > H + 80:
                continue
            osm_blds.append(dict(cx=(min(xs) + max(xs)) / 2, cy=(min(ys) + max(ys)) / 2,
                                 w=max(xs) - min(xs), h=max(ys) - min(ys), src='osm', tags=b.get('tags', {})))

        # --- дороги (пиксельные полилинии, дискретизация ~15 м) ---
        road_pts = []
        for r in d['roads']:
            pts = [geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
            if len(pts) < 2:
                continue
            prev = pts[0]
            road_pts.append(prev)
            for p in pts[1:]:
                seg = math.hypot(p[0] - prev[0], p[1] - prev[1]) * mpp
                n_sub = int(seg / 15.0)
                for k in range(1, n_sub + 1):
                    road_pts.append((prev[0] + (p[0] - prev[0]) * k / max(n_sub, 1),
                                     prev[1] + (p[1] - prev[1]) * k / max(n_sub, 1)))
                if seg < 15.0:
                    road_pts.append(p)
                prev = p
        road_arr = np.array([(x, y) for x, y in road_pts
                             if -100 <= x <= W + 100 and -100 <= y <= H + 100]) if road_pts else np.zeros((0, 2))

        def near_road(x, y, max_m):
            if len(road_arr) == 0:
                return False
            d2 = ((road_arr[:, 0] - x) ** 2 + (road_arr[:, 1] - y) ** 2).min()
            return math.sqrt(d2) * mpp < max_m

        # --- CV-суплемент ---
        cv_blds = []
        n_cv_raw = 0
        if key in CV_SUPPLEMENT:
            loose = False
            rd_max = NEAR_RD_M
            ctx_max = CTX_M
            roofs = detect_roofs(mos, loose=loose)
            # итеративный контекст: сначала возле дорог/OSM, затем расширение
            accepted = []
            for it in range(2):
                for (x, y, w_, h_) in roofs:
                    if any(abs(x - a[0]) < 8 and abs(y - a[1]) < 8 for a in accepted):
                        continue
                    near_osm = any(dist_px((x, y), (b['cx'], b['cy']), mpp) < OSM_MIN_SEP_M for b in osm_blds)
                    if near_osm:
                        continue
                    ctx = (near_road(x, y, rd_max) if it == 0 else
                           any(dist_px((x, y), (b['cx'], b['cy']), mpp) < ctx_max for b in osm_blds + [dict(cx=a[0], cy=a[1]) for a in accepted]))
                    if not ctx:
                        continue
                    accepted.append((x, y, w_, h_))
                n_cv_raw = len(accepted)
            cv_blds = [dict(cx=a[0], cy=a[1], w=a[2], h=a[3], src='cv') for a in accepted]

        all_blds = osm_blds + cv_blds

        # --- кластеризация усадеб ---
        eps = EPS_M / mpp
        used = [False] * len(all_blds)
        yards = []
        order = sorted(range(len(all_blds)), key=lambda i: -(all_blds[i]['w'] * all_blds[i]['h']))
        for i in order:
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
                    if math.hypot(all_blds[j]['cx'] - all_blds[k]['cx'],
                                 all_blds[j]['cy'] - all_blds[k]['cy']) < eps:
                        used[k] = True
                        queue.append(k)
            yards.append(yard)

        # --- фильтрация и сборка ДХ ---
        households = []
        for yard in yards:
            bl = [all_blds[j] for j in yard]
            main = max(bl, key=lambda b: b['w'] * b['h'] * (1.6 if b['src'] == 'osm' else 1.0))
            if main['w'] * main['h'] * mpp * mpp < 36:   # главное здание >= 36 м²
                continue
            cx = sum(b['cx'] for b in bl) / len(bl)
            cy = sum(b['cy'] for b in bl) / len(bl)
            if not near_road(cx, cy, ROAD_MAX_M):
                continue
            la, lo = px_to_geo(main['cx'], main['cy'], v['lat'], west, north, mpp)
            households.append(dict(id=len(households) + 1, cx=main['cx'], cy=main['cy'],
                                   lat=la, lon=lo, n_bld=len(bl),
                                   main_w=main['w'], main_h=main['h'], main_src=main['src']))
        summary[key] = dict(name=v['name'], expected=v['hh'], osm_bld=len(osm_blds),
                            cv_new=len(cv_blds), households=len(households))
        dev = 100 * (len(households) - v['hh']) / v['hh']
        print(f"{v['name']}: OSM {len(osm_blds)} + CV {len(cv_blds)} -> {len(households)} ДХ (Excel {v['hh']}, {dev:+.1f}%)")
        save_json(f'{vdir(key)}/households.json', households)
    save_json('/home/z/my-project/work/hh_summary.json', summary)

if __name__ == '__main__':
    main()
