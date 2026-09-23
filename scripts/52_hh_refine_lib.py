# -*- coding: utf-8 -*-
"""
Библиотека уточнённой детекции домохозяйств (v2, Task 45).

Причина пересмотра (кейс пользователя, Пригородное hh215): OSM-полигон покрывает
ДВА сблокированных дома с разными крышами, разделённые забором; кластеризация
усадеб eps=16 м (шаг 04f) дополнительно склеивает соседние дома в одно ДХ.

Модуль:
  1) reproduce_04f(key) — детерминированное воспроизведение кластеров шага 04f
     (OSM-здания + CV-супplement + кластеризация + фильтры) с сохранением
     членов кластера и полигонов зданий;
  2) roof_split_info(...) — CV-тест «две крыши в одном полигоне»:
     k-means k=2 по хроматике (LAB a,b, БЕЗ яркости — солнечный/теневой скат
     одного дома различаются только L), критерии: площадь частей, ΔE_ab,
     расстояние центроидов, связность компонент;
  3) roof_chroma(...) — средняя хроматика крыши здания (для кластерного сплита).
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json
import numpy as np
import cv2
from PIL import Image

BASE = '/home/z/my-project'

# ---- параметры 04f (воспроизведение 1:1) ----
CV_SUPPLEMENT = {'verhneberezovka', 'perevalnoe', 'altaiskiy'}
EPS_M = 16.0
ROAD_MAX_M = 60.0
NEAR_RD_M = 75.0
CTX_M = 90.0
OSM_MIN_SEP_M = 15.0

# ---- параметры уточнения v3 (Task 46, критерии пользователя) ----
# Признаки ДВУХ владений в одном здании: (1) увеличенные размеры; (2) забор,
# примыкающий к фасаду перпендикулярно ближе к его центру; (3) общая кровля
# одинаковой формы, иногда двух цветов. Различие ЦВЕТА крыш НЕ достаточно:
# пристройка тоже имеет другой цвет кровли, но ОТЛИЧНУЮ форму в плане —
# обычно прямоугольник МЕНЬШЕГО размера => части разного масштаба (ratio).
# OSM-полигоны — сложные контуры (fill 0.28-0.68), поэтому тест формы — не
# по полигону, а по СОПОСТАВИМОСТИ частей сплита.
MIN_BBOX_M2 = 165.0        # «увеличенные размеры»: больше типового дома (P50 ~155-185)
MIN_LONG_M = 12.5          # длинная сторона (фасад) >= ~2 ширин дома
CENTER_T0, CENTER_T1 = 0.38, 0.62  # линия раздела у ЦЕНТРА фасада
MIN_PART_M2_V3 = 36.0      # обе части — дом-размера
MIN_PART_RATIO_V3 = 0.35   # «одинаковая форма»: сопоставимость частей (анти-пристройка)
GEOM_RATIO = 0.30          # одноцветный канал: части сопоставимы чуть мягче
SEAM_GRAD_T = 40.0         # порог градиента яркости для шва/стыка кровель
SEAM_FRAC_MIN = 0.45       # шов считается найденным при покрытии >= 45% среза
# ---- параметры v2 (legacy, см. roof_split_info_v2_legacy) ----
MIN_PART_M2 = 35.0     # мин. площадь части крыши для сплита, м²
MIN_D_EAB = 8.5        # мин. расстояние хроматики между ЧАСТЯМИ (LAB a,b)
STRONG_D_EAB = 18.0    # сильное различие — кандидат без доп. условий
MAX_HUE_SHIFT = 25.0   # солнце/тень: хроматический сдвиг одного материала < 25°
NEUTRAL_TOL = 6.0      # |a-128|+|b-128| < 6 => нейтральная (серая) крыша
COLORED_TOL = 10.0     # удаление от нейтрали >= 10 => окрашенная крыша
MIN_AXIS_SEP_FRAC = 0.30  # центроиды частей разнесены вдоль оси >= 30% размаха
MIN_CENTROID_M = 3.0   # и не ближе 3 м (защита от вырожденных разбиений)
MIN_POLY_M2 = 80.0     # полигон должен вмещать 2 дома (2 x 40 м²)
CLUSTER_BLD_M2 = 60.0  # здание-кандидат кластерного сплита (дом-размер)
B_MIN_SEP_M = 10.0     # мин. расстояние между зданиями кластерного сплита
MS_LEVELS_MIN = 2      # многоэтажка: levels >= 2 ...
MS_AREA_MIN = 300.0    # ... и площадь >= 300 м² (иначе это 2-эт. индивидуальный дом)
MS_AREA_ANY = 450.0    # многоэтажка-кандидат и без levels: площадь >= 450 м²
APT_M2_PER_FLAT = 55.0 # оценка числа квартир: этажи x площадь / 55
MS_HOUSE_TAGS = {'yes', 'house', 'detached', 'residential', 'apartments',
                 'semidetached_house', 'bungalow', 'hut', 'unclassified'}


def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)


def detect_roofs(mos_rgb, loose=False):
    """Верbatim из 04f_households_final."""
    hsv = cv2.cvtColor(mos_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    blue = (h >= 90) & (h <= 132) & (s > 65) & (v > 50)
    red = ((h <= 12) | (h >= 168)) & (s > 75) & (v > 55)
    orange = (h >= 13) & (h <= 35) & (s > 85) & (v > 95)
    green = (h >= 40) & (h <= 85) & (s > 65) & (v > 50)
    gray = (s < 50) & (v > (125 if loose else 140)) & (v < 248)
    dark = (s < 40) & (v > 85) & (v <= 125)
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


def reproduce_04f(key):
    """Воспроизводит кластеры/ДХ шага 04f, сохраняя члены кластеров и полигоны.
    Возвращает dict: blds (все здания с poly/tags), yards (списки индексов),
    hh_map (индекс кластера -> id ДХ из households.json)."""
    v = next(x for x in VILLAGES if x['key'] == key)
    geo_all = load_json(f'{BASE}/work/mosaic_geo.json')
    g = geo_all[key]
    mpp, west, north = g['mpp'], g['west'], g['north']
    d = load_json(f'{vdir(key)}/osm.json')
    fb = load_json(f'{BASE}/work/bboxes_final.json')[key]['bbox']
    mos = np.asarray(Image.open(f'{vdir(key)}/mosaic.jpg').convert('RGB'))
    H, W = mos.shape[:2]

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
                             w=max(xs) - min(xs), h=max(ys) - min(ys), src='osm',
                             tags=b.get('tags', {}), poly=pts))

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

    def dist_px(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1]) * mpp

    cv_blds = []
    if key in CV_SUPPLEMENT:
        loose = False
        rd_max = NEAR_RD_M
        ctx_max = CTX_M
        roofs = detect_roofs(mos, loose=loose)
        accepted = []
        for it in range(2):
            for (x, y, w_, h_) in roofs:
                if any(abs(x - a[0]) < 8 and abs(y - a[1]) < 8 for a in accepted):
                    continue
                near_osm = any(dist_px((x, y), (b['cx'], b['cy'])) < OSM_MIN_SEP_M for b in osm_blds)
                if near_osm:
                    continue
                ctx = (near_road(x, y, rd_max) if it == 0 else
                       any(dist_px((x, y), (b['cx'], b['cy'])) < ctx_max
                           for b in osm_blds + [dict(cx=a[0], cy=a[1]) for a in accepted]))
                if not ctx:
                    continue
                accepted.append((x, y, w_, h_))
        cv_blds = [dict(cx=a[0], cy=a[1], w=a[2], h=a[3], src='cv', tags={},
                        poly=[(a[0] - a[2] / 2, a[1] - a[3] / 2), (a[0] + a[2] / 2, a[1] - a[3] / 2),
                              (a[0] + a[2] / 2, a[1] + a[3] / 2), (a[0] - a[2] / 2, a[1] + a[3] / 2)])
                  for a in accepted]

    all_blds = osm_blds + cv_blds

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

    # сборка ДХ (как 04f) + сопоставление с households.json
    hh_file = load_json(f'{vdir(key)}/households.json')
    hh_by_pos = {}
    for h in hh_file:
        hh_by_pos[(round(h['cx'], 1), round(h['cy'], 1))] = h['id']

    yards_hh = []  # (yard_idx_list, hh_id or None, main_idx)
    for yard in yards:
        bl = [all_blds[j] for j in yard]
        main = max(bl, key=lambda b: b['w'] * b['h'] * (1.6 if b['src'] == 'osm' else 1.0))
        if main['w'] * main['h'] * mpp * mpp < 36:
            continue
        cx = sum(b['cx'] for b in bl) / len(bl)
        cy = sum(b['cy'] for b in bl) / len(bl)
        if not near_road(cx, cy, ROAD_MAX_M):
            continue
        hid = hh_by_pos.get((round(main['cx'], 1), round(main['cy'], 1)))
        yards_hh.append(dict(yard=yard, hh_id=hid, main=all_blds.index(main),
                             cx=cx, cy=cy))
    return dict(key=key, mpp=mpp, mos=mos, H=H, W=W, blds=all_blds,
                yards_hh=yards_hh, v=v)


# ---------------------------------------------------------------- CV ядро
def _poly_local(poly, mpp):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _hue_deg(h8):
    """OpenCV H (0..179) -> градусы."""
    return h8 * 2.0


def roof_split_info(mos, poly, mpp):
    """Тест «в здании два домохозяйства» (v3, Task 46).

    Условие поиска ПО КРЫШАМ скорректировано по пользователю: различие ЦВЕТА
    НЕ достаточно (пристройка тоже другого цвета, но прямоугольник меньшего
    размера). Признаки пары владений: увеличенные размеры + ограждение у
    ЦЕНТРА фасада перпендикулярно ему + общая кровля ОДИНАКОВОЙ формы
    (иногда двух цветов).

    Два канала (OSM-полигоны — сложные контуры, fill 0.28-0.68, поэтому
    форма оценивается по частям сплита, а не по полигону):
      канал 1 «двухцветная пара»: хроматический сплит (как v2) в центре
        фасада (t 0.38..0.62) при СОПОСТАВИМЫХ частях (ratio >= 0.35 —
        анти-пристройка) и частях дом-размера (>= 36 м²);
      канал 2 «одноцветная пара»: геометрический центр-сплит (частям всё
        равно какого цвета) — только при найденном ШВЕ/СТЫКЕ кровель
        (seam_frac >= SEAM_FRAC_MIN) на линии раздела.
    Шов/стык (тонкая тень стыка кровель/стен) — CV-заместитель признака
    «примыкание ограждения перпендикулярно фасаду»; окончательное решение
    об ограждении — за VLM-верификацией кропа.
    Возвращает dict (приоритет 1/2/3, геометрия+хроматика частей) или None."""
    x0, y0, x1, y1 = _poly_local(poly, mpp)
    x0i, y0i = int(max(0, math.floor(x0))), int(max(0, math.floor(y0)))
    x1i, y1i = int(min(mos.shape[1], math.ceil(x1))), int(min(mos.shape[0], math.ceil(y1)))
    W_, H_ = x1i - x0i, y1i - y0i
    if W_ < 14 or H_ < 14:
        return None
    # 1) «увеличенные размеры»
    bbox_m2 = W_ * H_ * mpp * mpp
    if bbox_m2 < MIN_BBOX_M2:
        return None
    long_px = max(W_, H_)
    if long_px * mpp < MIN_LONG_M:
        return None

    crop = mos[y0i:y1i, x0i:x1i]
    pts = np.array([[p[0] - x0i, p[1] - y0i] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    fill = float((mask > 0).sum()) / float(W_ * H_)

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    v_ = hsv[..., 2]
    valid = (mask > 0) & (v_ >= 35) & (v_ <= 250)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    a_ch, b_ch = lab[..., 1].astype(np.float32), lab[..., 2].astype(np.float32)
    hue = hsv[..., 0].astype(np.float32)
    sat = hsv[..., 1].astype(np.float32)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    Xg, Yg = np.meshgrid(np.arange(W_, dtype=np.float32),
                         np.arange(H_, dtype=np.float32))

    # обе оси: сблокированные дома стоят и торцами, и бок о бок
    best_chroma = None   # канал 1 (двухцветная пара)
    best_geom = None     # канал 2 (одноцветная пара, только со швом)
    for axis in (0, 1):
        coord = Xg if axis == 0 else Yg
        span = W_ if axis == 0 else H_
        grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1 if axis == 0 else 0,
                                0 if axis == 0 else 1, ksize=3)) / 4.0
        for t in np.arange(CENTER_T0, CENTER_T1 + 1e-9, 0.02):
            cut = t * span
            m0 = valid & (coord < cut)
            m1 = valid & (coord >= cut)
            a0_m2, a1_m2 = int(m0.sum()) * mpp * mpp, int(m1.sum()) * mpp * mpp
            if a0_m2 < MIN_PART_M2_V3 or a1_m2 < MIN_PART_M2_V3:
                continue
            ratio = min(a0_m2, a1_m2) / max(a0_m2, a1_m2)
            if ratio < GEOM_RATIO:
                continue
            r = {}
            for lb, m in ((0, m0), (1, m1)):
                sat_m = sat[m]
                r[lb] = dict(
                    n=int(m.sum()),
                    a=float(a_ch[m].mean()), b=float(b_ch[m].mean()),
                    cx=float(Xg[m].mean()), cy=float(Yg[m].mean()),
                    hue=float(hue[m][sat_m > 30].mean()) * 2.0
                    if (sat_m > 30).sum() > 30 else None)
            dE = math.hypot(r[0]['a'] - r[1]['a'], r[0]['b'] - r[1]['b'])
            n0n = abs(r[0]['a'] - 128) + abs(r[0]['b'] - 128)
            n1n = abs(r[1]['a'] - 128) + abs(r[1]['b'] - 128)
            neutral_colored = ((n0n < NEUTRAL_TOL and n1n >= COLORED_TOL) or
                               (n1n < NEUTRAL_TOL and n0n >= COLORED_TOL))
            hue_diff = None
            if r[0]['hue'] is not None and r[1]['hue'] is not None:
                dh = abs(r[0]['hue'] - r[1]['hue'])
                hue_diff = min(dh, 360.0 - dh)
            two_color = (dE >= MIN_D_EAB and (dE >= STRONG_D_EAB or neutral_colored or
                          (hue_diff is not None and hue_diff >= MAX_HUE_SHIFT)))
            # шов/стык на линии раздела (тень стыка кровель/стен)
            band = valid & (np.abs(coord - cut) <= 1.5)
            nb = int(band.sum())
            seam_frac = float((grad[band] > SEAM_GRAD_T).sum()) / max(nb, 1) \
                if nb > 0 else 0.0
            has_seam = seam_frac >= SEAM_FRAC_MIN
            cen_m = math.hypot(r[0]['cx'] - r[1]['cx'], r[0]['cy'] - r[1]['cy']) * mpp
            rec = dict(axis=axis, t=round(float(t), 2), ratio=round(ratio, 2),
                       dE_ab=dE, hue_diff=hue_diff, neutral_colored=neutral_colored,
                       two_color=two_color, seam_frac=seam_frac, centroid_m=cen_m, r=r)
            # канал 1: двухцветный сплит с сопоставимыми частями (анти-пристройка)
            if two_color and ratio >= MIN_PART_RATIO_V3:
                score = (2.0 * min(seam_frac / SEAM_FRAC_MIN, 1.0) +
                         min(dE / 15.0, 1.5) + 1.0 - abs(t - 0.5) / 0.13)
                if best_chroma is None or score > best_chroma[0]:
                    best_chroma = (score, rec)
            # канал 2: любой центр-сплит, но только со швом на линии раздела
            if has_seam:
                score = seam_frac + 1.0 - abs(t - 0.5) / 0.13
                if best_geom is None or score > best_geom[0]:
                    best_geom = (score, rec)

    pick = None
    if best_chroma is not None:
        pick = best_chroma[1]
        has_seam = pick['seam_frac'] >= SEAM_FRAC_MIN
        priority = 1 if has_seam else 2
    elif best_geom is not None:
        pick = best_geom[1]
        has_seam = True
        priority = 3 if not pick['two_color'] else 2
    if pick is None:
        return None
    r0, r1 = pick['r'][0], pick['r'][1]
    return dict(
        bbox_m2=round(bbox_m2, 1), long_m=round(long_px * mpp, 1),
        fill=round(fill, 2),
        dE_ab=round(pick['dE_ab'], 1), axis=pick['axis'], t=pick['t'],
        centroid_m=round(pick['centroid_m'], 1), ratio=pick['ratio'],
        hue_diff=(round(pick['hue_diff'], 1) if pick['hue_diff'] is not None else None),
        neutral_colored=bool(pick['neutral_colored']), two_color=bool(pick['two_color']),
        seam_frac=round(pick['seam_frac'], 2), priority=priority,
        part0=dict(area_m2=round(r0['n'] * mpp * mpp, 1),
                   cx=round(r0['cx'] + x0i, 1), cy=round(r0['cy'] + y0i, 1),
                   ab=(round(r0['a'], 1), round(r0['b'], 1))),
        part1=dict(area_m2=round(r1['n'] * mpp * mpp, 1),
                   cx=round(r1['cx'] + x0i, 1), cy=round(r1['cy'] + y0i, 1),
                   ab=(round(r1['a'], 1), round(r1['b'], 1))))


def roof_split_info_v2_legacy(mos, poly, mpp):
    """Поиск линии раздела двух сблокированных домов в полигоне.

    Метод: для каждой оси (x, y) и положения линии t (0.30..0.70) полигон
    делится на две части; вычисляется хроматика (LAB a,b) и оттенок (HSV hue)
    каждой части. Лучшее разделение максимизирует dE_ab. Кандидат, если:
      - обе части >= MIN_PART_M2;
      - центроиды частей разнесены >= MIN_CENTROID_M;
      - dE_ab >= MIN_D_EAB И (dE_ab >= STRONG_D_EAB ИЛИ одна часть нейтральная
        (серая), а другая окрашенная ИЛИ оттенки различаются >= 25°).
    Это отсекает солнечный/теневой скат одного дома (различие почти только
    по яркости L, хроматика и оттенок совпадают).
    Возвращает dict с частями (площади, центроиды, ab, hue) или None."""
    x0, y0, x1, y1 = _poly_local(poly, mpp)
    x0i, y0i = int(max(0, math.floor(x0))), int(max(0, math.floor(y0)))
    x1i, y1i = int(min(mos.shape[1], math.ceil(x1))), int(min(mos.shape[0], math.ceil(y1)))
    if x1i - x0i < 10 or y1i - y0i < 10:
        return None
    crop = mos[y0i:y1i, x0i:x1i]
    pts = np.array([[p[0] - x0i, p[1] - y0i] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    area_px = float((mask > 0).sum())
    min_part_px = MIN_PART_M2 / (mpp * mpp)
    if area_px < max(2 * min_part_px, MIN_POLY_M2 / (mpp * mpp) * 0.8):
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    v_ = hsv[..., 2]
    valid = (mask > 0) & (v_ >= 35) & (v_ <= 250)
    if valid.sum() < 2 * min_part_px:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    a_ch, b_ch = lab[..., 1].astype(np.float32), lab[..., 2].astype(np.float32)
    hue = hsv[..., 0].astype(np.float32)
    sat = hsv[..., 1].astype(np.float32)
    ys_, xs_ = np.nonzero(valid)

    # ось раздела: сблокированные дома могут стоять как вдоль длинной оси
    # (дом-к-дому торцами), так и бок о бок вдоль короткой — проверяем ОБЕ оси;
    # от солнце/тени (различие только по яркости L) защищает хроматический тест.
    W_, H_ = x1i - x0i, y1i - y0i

    valid_splits = []
    for axis in (0, 1):
        coord = xs_ if axis == 0 else ys_
        span = W_ if axis == 0 else H_
        for t in np.arange(0.30, 0.71, 0.05):
            cut = t * span
            m0 = coord < cut
            if m0.sum() < min_part_px or (~m0).sum() < min_part_px:
                continue
            r = {}
            for lb, m in ((0, m0), (1, ~m0)):
                sat_m = sat[ys_[m], xs_[m]]
                r[lb] = dict(
                    n=int(m.sum()),
                    a=float(a_ch[ys_[m], xs_[m]].mean()),
                    b=float(b_ch[ys_[m], xs_[m]].mean()),
                    cx=float(xs_[m].mean()), cy=float(ys_[m].mean()),
                    hue=float(hue[ys_[m], xs_[m]][sat_m > 30].mean()) * 2.0
                    if (sat_m > 30).sum() > 30 else None)
            dE = math.hypot(r[0]['a'] - r[1]['a'], r[0]['b'] - r[1]['b'])
            # разнос центроидов вдоль оси раздела (доли размаха) и абсолютный
            cen_ax0 = r[0]['cx'] if axis == 0 else r[0]['cy']
            cen_ax1 = r[1]['cx'] if axis == 0 else r[1]['cy']
            sep_frac = abs(cen_ax0 - cen_ax1) / max(1.0, span)
            cen_m = math.hypot(r[0]['cx'] - r[1]['cx'], r[0]['cy'] - r[1]['cy']) * mpp
            if sep_frac < MIN_AXIS_SEP_FRAC or cen_m < MIN_CENTROID_M or dE < MIN_D_EAB:
                continue
            # защита от солнце/тень: различие должно быть хроматическим
            n0 = abs(r[0]['a'] - 128) + abs(r[0]['b'] - 128)
            n1 = abs(r[1]['a'] - 128) + abs(r[1]['b'] - 128)
            neutral_colored = (n0 < NEUTRAL_TOL and n1 >= COLORED_TOL) or \
                              (n1 < NEUTRAL_TOL and n0 >= COLORED_TOL)
            hue_diff = None
            if r[0]['hue'] is not None and r[1]['hue'] is not None:
                dh = abs(r[0]['hue'] - r[1]['hue'])
                hue_diff = min(dh, 360.0 - dh)
            ok = (dE >= STRONG_D_EAB or neutral_colored or
                  (hue_diff is not None and hue_diff >= MAX_HUE_SHIFT))
            if ok:
                valid_splits.append(dict(axis=axis, t=round(float(t), 2), dE_ab=dE,
                                         centroid_m=cen_m, sep_frac=round(sep_frac, 2),
                                         hue_diff=hue_diff,
                                         neutral_colored=neutral_colored, r=r))
    if not valid_splits:
        return None
    best = max(valid_splits, key=lambda s: s['dE_ab'])
    r0, r1 = best['r'][0], best['r'][1]
    return dict(
        dE_ab=round(best['dE_ab'], 1), axis=best['axis'], t=best['t'],
        centroid_m=round(best['centroid_m'], 1),
        hue_diff=(round(best['hue_diff'], 1) if best['hue_diff'] is not None else None),
        neutral_colored=bool(best['neutral_colored']),
        part0=dict(area_m2=round(r0['n'] * mpp * mpp, 1),
                   cx=round(r0['cx'] + x0i, 1), cy=round(r0['cy'] + y0i, 1),
                   ab=(round(r0['a'], 1), round(r0['b'], 1))),
        part1=dict(area_m2=round(r1['n'] * mpp * mpp, 1),
                   cx=round(r1['cx'] + x0i, 1), cy=round(r1['cy'] + y0i, 1),
                   ab=(round(r1['a'], 1), round(r1['b'], 1))))


def roof_chroma(mos, poly, mpp):
    """Средняя хроматика (a,b) крыши — для сравнения крыш разных зданий."""
    x0, y0, x1, y1 = _poly_local(poly, mpp)
    x0i, y0i = int(max(0, math.floor(x0))), int(max(0, math.floor(y0)))
    x1i, y1i = int(min(mos.shape[1], math.ceil(x1))), int(min(mos.shape[0], math.ceil(y1)))
    if x1i - x0i < 6 or y1i - y0i < 6:
        return None
    crop = mos[y0i:y1i, x0i:x1i]
    pts = np.array([[p[0] - x0i, p[1] - y0i] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    if (mask > 0).sum() < 60:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    v_ = hsv[..., 2]
    valid = (mask > 0) & (v_ >= 35) & (v_ <= 250)
    if valid.sum() < 40:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    return float(lab[..., 1][valid].mean()), float(lab[..., 2][valid].mean())
