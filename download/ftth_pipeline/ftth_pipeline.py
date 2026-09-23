#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ftth_pipeline.py — конвейер проектирования FTTH для сельских населённых пунктов.

От координат села (или спутникового кадра) до карты сети с зонами ОРШ и
спецификации материалов (BoQ). Обобщает и автоматизирует методику, отработанную
на проекте «6 СНП ВКО» (2 334 ДХ, схемы A/B/C/D).

СТАДИИ (каждая пишет артефакты в <root>/work/<key>/ и может запускаться отдельно;
повторный запуск стадии идемпотентен, кэши внешних запросов — на диске):

  fetch       OSM-данные (дороги/здания) + граница застройки + мозаика Google z18
              -> osm.json, mosaic.jpg, geo.json
  households  домохозяйства: OSM-здания + CV-детекция крыш + кластеризация усадеб
              -> households.json (+ households_preview.jpg)
  anchor      выбор здания-якоря ЦУ/ОРШ (скоринг, топ-5 кандидатов)
              -> anchor_candidates.json + anchor_preview.png  [точка ручной проверки]
  network     древовидная сеть: дорожный граф, MST/SPT, муфты, дропы
              -> network.json
  crop        (опционально) привязка пользовательского кадра (SIFT+RANSAC) и
              перестроение сети в границах кадра -> crop_transform.json,
              network_v2.json
  boq         расчёт материалов: схема A (централизованная 1:64) и схема D
              (зонные ОРШ 1:64, единый OLT, жадное разбиение по S_MIN)
              -> boq.json (на село), work/boq_total.json (по проекту)
  map         карта зон ОРШ (схема D) на базовом снимке со слоями сети
              -> download/<num>_<Село>_зоны_ОРШ.jpg (+ превью в work/qa/)
  xlsx        спецификация: книга Excel «Сводная / Параметры / Схемы A-D /
              Методика» -> download/BoQ_FTTH_<проект>.xlsx
  all         все стадии по порядку
  qa          контрольные проверки всех артефактов

Использование:
  python3 ftth_pipeline.py --config config.json --stage all
  python3 ftth_pipeline.py --config config.json --stage boq --village prigorodnoe
  python3 ftth_pipeline.py --config config.json --stage map --vlm

Полная методология — README.md рядом с этим файлом.
"""
import argparse
import gc
import hashlib
import io
import json
import math
import os
import random
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

# ----------------------------------------------------------------------------
# Параметры модели (значения по умолчанию; переопределяются в config.json)
# ----------------------------------------------------------------------------
DEFAULTS = dict(
    zoom=18,                    # Google Satellite: ~0.38 м/px на 50° с.ш. (z19 — апскейл)
    probe_margin_m=900.0,       # зондажная область вокруг точки заказа: radius_m + запас
    boundary_grid_m=50.0,       # сетка кластеризации застройки для границы села
    boundary_margin_m=300.0,    # отступ границы села от крайних зданий
    boundary_close_m=100.0,     # замыкание: мост пробелов между кустами застройки
    boundary_min_bld=15,        # мин. зданий в компоненте застройки
    boundary_keep_frac=0.65,    # компоненты с центроидом ближе этой доли зонда
    # --- домохозяйства ---
    hh_eps_m=16.0,              # радиус кластеризации зданий в усадьбу
    hh_road_max_m=60.0,         # двор не дальше от дороги
    hh_main_area_m2=36.0,       # главное здание усадьбы не меньше
    hh_cv_near_road_m=75.0,     # CV-кандидат ближе к дороге
    hh_cv_ctx_m=90.0,           # контекст CV-кандидата (другой объект в радиусе)
    hh_cv_min_sep_m=15.0,       # CV-кандидат не ближе к OSM-зданию
    hh_cv_deficit_pct=15.0,     # дефицит OSM-зданий (>%), при котором включается CV
    # --- сеть ---
    net_densify_m=4.0,          # шаг денсификации дорожного графа
    net_snap_max_m=90.0,        # максимум привязки ДХ к дороге
    net_merge_m=50.0,           # слияние точек подключения в муфту
    net_dedup_m=15.0,           # дедупликация муфт по дереву
    net_max_drop_m=120.0,       # длина дропа, после которой ставится промежуточная муфта
    net_intermediate_m=100.0,   # шаг промежуточной муфты
    # --- оптический бюджет (v2.4; Task 48 — сверка с отраслевыми материалами:
    #     foxes-com «Методика построения xPON», prorostelecom «Построение сети
    #     GPON»: расчёт бюджета потерь — обязательный этап проектирования PON) ---
    ob_alpha_db_km=0.35,        # затухание G.652D @1310 нм (upstream — худший поток)
    ob_splitter_il_db=21.0,     # вносимое затухание PLC 1:64 (верхняя граница спецификации)
    ob_splice_db=0.10,          # сварное соединение
    ob_connector_db=0.50,       # разъём SC/APC (3 шт: ODF ЦУ, кросс ОРШ, ONT)
    ob_penalty_db=0.20,         # штрафные потери (изгибы/наплывы)
    ob_budget_db=28.0,          # GPON Class B+ — рабочий бюджет
    ob_budget_db_c=32.0,        # GPON Class C+ — опция для дальних зон
    ob_margin_min_db=3.0,       # эксплуатационный запас (ремонтные вставки/сростки)
    # --- BoQ ---
    fiber_reserve=1.25,         # резерв волокон магистрали
    min_fibers=8,               # минимальная ёмкость участка
    std_fibers=[8, 12, 16, 24, 32, 48, 64, 72, 96],
    cable_stock=1.10,           # запас магистрального кабеля
    drop_stock=1.05,            # запас дроп-кабеля
    suspend_per_km=30,          # комплектов подвеса на км
    drop_anchors_per_dh=2,
    drop_fix_per_dh=6,
    consum_stock=1.10,          # запас расходников (сварки/коннекторы)
    split_ratio=64,             # коэффициент сплиттера
    orsh_ports_row=[144, 288, 576, 864, 1152],       # кросс ЦУ
    orsh_ports_row_zone=[48, 96, 144, 288, 576],     # кросс зонных ОРШ (уличные шкафы)
    # --- схема D (зонные ОРШ) ---
    s_min_km=15.0,              # порог окупаемости зонного шкафа, волокно-км
    min_zone_dh=48,             # мин. ДХ в зоне (заполнение сплиттера >= 75%)
)

M_PER_DEG_LAT = 111320.0
OSM_API = 'https://api.openstreetmap.org/api/0.6/map'
GOOGLE_TILE = 'https://mt{m}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
HDRS = {'User-Agent': 'FTTH-planning-research/1.0 (rural network design study)'}
GUA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
       'Referer': 'https://www.google.com/maps'}

ROAD_KEYS = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
             'residential', 'living_street', 'service', 'track', 'road', 'pedestrian'}
URBAN_ROADS = {'residential', 'living_street', 'service', 'unclassified', 'road', 'tertiary', 'secondary'}
MAIN_ROADS = {'primary', 'secondary', 'tertiary', 'trunk', 'unclassified', 'residential'}
BAD_BUILDINGS = ('garage', 'garages', 'barn', 'shed', 'greenhouse', 'roof', 'kiosk', 'hut')


# ----------------------------------------------------------------------------
# Утилиты: пути, HTTP, Web Mercator, JSON
# ----------------------------------------------------------------------------
class Ctx:
    """Контекст запуска: конфиг, корень проекта, параметры, пути."""

    def __init__(self, config_path, only=None):
        with open(config_path, encoding='utf-8') as f:
            cfg = json.load(f)
        self.cfg = cfg
        self.root = os.path.abspath(cfg.get('root') or os.path.dirname(os.path.abspath(config_path)))
        self.work = os.path.join(self.root, 'work')
        self.dl = os.path.join(self.root, 'download')
        os.makedirs(self.work, exist_ok=True)
        os.makedirs(self.dl, exist_ok=True)
        self.params = dict(DEFAULTS)
        self.params.update(cfg.get('params') or {})
        vil = cfg['villages']
        if only:
            vil = [v for v in vil if v['key'] == only]
            if not vil:
                raise SystemExit(f'в config нет села с key={only!r}')
        self.villages = vil

    def vdir(self, key):
        d = os.path.join(self.work, key)
        os.makedirs(d, exist_ok=True)
        return d

    def P(self, name, default=None):
        """Параметр пайплайна; default — если параметр не задан (v2.4:
        вызовы hh_refine/hh_split_no_vlm/hh_vlm_verify передают default)."""
        return self.params.get(name, default)


def save_json(path, obj):
    def _conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f'not serializable: {type(o)}')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, default=_conv)


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def lon2tx(lon, z):
    return (lon + 180.0) / 360.0 * (1 << z)


def lat2ty(lat, z):
    lr = math.radians(lat)
    return (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * (1 << z)


def tx2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0


def ty2lat(y, z):
    n = math.pi * (1.0 - 2.0 * y / (1 << z))
    return math.degrees(math.atan(math.sinh(n)))


def m_per_px(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (1 << z)


def http_get(url, params=None, tries=4, timeout=60, backoff=2.0, headers=None):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers or HDRS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503, 504):
                last = f'HTTP {r.status_code}'
            else:
                r.raise_for_status()
        except Exception as e:
            last = str(e)[:100]
        time.sleep(backoff * (i + 1) + random.random())
    raise RuntimeError(f'GET {url[:90]} failed: {last}')


def fetch_tile(z, x, y, cache_dir):
    """Тайл Google Satellite с дисковым кэшем. bytes или None."""
    p = os.path.join(cache_dir, f'g{z}', str(x), f'{y}.jpg')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p):
        if os.path.getsize(p) > 0:
            with open(p, 'rb') as f:
                return f.read()
        return None
    for attempt in range(3):
        try:
            r = requests.get(GOOGLE_TILE.format(m=(x + y) % 4, z=z, x=x, y=y),
                             headers=GUA, timeout=30)
            if r.status_code == 200 and len(r.content) > 500:
                with open(p, 'wb') as f:
                    f.write(r.content)
                return r.content
            if r.status_code == 404:
                open(p, 'wb').close()
                return None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def geo_to_px(lat, lon, west, north, mpp):
    return ((lon - west) * (M_PER_DEG_LAT * math.cos(math.radians(lat))) / mpp,
            (north - lat) * M_PER_DEG_LAT / mpp)


def px_to_geo(x, y, lat_ref, west, north, mpp):
    return (north - y * mpp / M_PER_DEG_LAT,
            west + x * mpp / (M_PER_DEG_LAT * math.cos(math.radians(lat_ref))))


def nkey(p):
    """Ключ узла сети (округление координат мозаики до 0.01 px)."""
    return (round(p[0], 2), round(p[1], 2))


def ceilr(x):
    """ceil без артефактов плавающей точки (770.0000000000001 -> 770)."""
    return math.ceil(round(x, 6))


def roundup01(x):
    return math.ceil(x * 10 - 1e-9) / 10


def decompose(F, std):
    """Число волокон участка -> список параллельных кабелей стандартной ёмкости."""
    if F <= std[-1]:
        for s in std:
            if s >= F:
                return [s]
    n96, rem = divmod(F, std[-1])
    out = [std[-1]] * n96
    if rem > 0:
        for s in std:
            if s >= rem:
                out.append(s)
                break
    return out


def meters_to_deg(m, lat):
    return m / M_PER_DEG_LAT, m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


# ============================================================================
# СТАДИЯ 1: fetch — OSM + граница застройки + мозаика Google z18
# ============================================================================
def fetch_bbox_raw(lon_min, lat_min, lon_max, lat_max, cache_path):
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
        with open(cache_path, 'rb') as f:
            return f.read()
    for attempt in range(4):
        try:
            r = requests.get(OSM_API, params={
                'bbox': f'{lon_min:.6f},{lat_min:.6f},{lon_max:.6f},{lat_max:.6f}'},
                headers=HDRS, timeout=120)
            if r.status_code == 200:
                with open(cache_path, 'wb') as f:
                    f.write(r.content)
                return r.content
            if r.status_code == 400:
                print('   bbox слишком велик для OSM API, скип')
                return None
            print(f'   HTTP {r.status_code}, повтор...')
        except Exception as e:
            print(f'   {str(e)[:70]}, повтор...')
        time.sleep(3 * (attempt + 1))
    return None


def parse_osm(xml_bytes):
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


def osm_features(nodes, ways):
    """-> roads[{id,pts,hw,name}], buildings[{id,poly,center,area,tags}], pois[]"""
    roads, buildings, pois = [], [], []
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
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                a = 0.0
                mx = M_PER_DEG_LAT * math.cos(math.radians(cy))
                for k in range(len(pts)):
                    la1, lo1 = pts[k]
                    la2, lo2 = pts[(k + 1) % len(pts)]
                    x1, y1 = lo1 * mx, la1 * M_PER_DEG_LAT
                    x2, y2 = lo2 * mx, la2 * M_PER_DEG_LAT
                    a += x1 * y2 - x2 * y1
                buildings.append(dict(
                    id=wid, poly=pts, center=[cx, cy], area=round(abs(a) / 2, 1),
                    tags={k: tags[k] for k in ('building', 'name', 'amenity', 'shop',
                                               'office', 'height', 'building:levels') if k in tags}))
        if (tags.get('amenity') or tags.get('office') or tags.get('shop')) and not bld:
            if nds and nds[0] in nodes:
                la, lo, _ = nodes[nds[0]]
                pois.append(dict(id=wid, lat=la, lon=lo,
                                 tags={k: tags[k] for k in ('amenity', 'office', 'shop', 'name') if k in tags}))
    return roads, buildings, pois


def _nominatim_name(lat, lon, cache_path):
    """Имя ближайшего поселения (Nominatim reverse, кэш на диске, отказоустойчиво)."""
    key = f'{lat:.4f},{lon:.4f}'
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding='utf-8'))
        except Exception:
            cache = {}
    if key in cache:
        return cache[key]
    name = None
    try:
        r = requests.get('https://nominatim.openstreetmap.org/reverse',
                         params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 14},
                         headers=HDRS, timeout=20)
        if r.status_code == 200:
            addr = r.json().get('address', {})
            for t in ('village', 'hamlet', 'town', 'city', 'suburb', 'settlement'):
                if addr.get(t):
                    name = addr[t]
                    break
    except Exception:
        name = None
    cache[key] = name
    try:
        json.dump(cache, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass
    time.sleep(1.0)
    return name


def detect_bbox(v, roads, buildings, probe, P, cache_path=None):
    """Граница застройки (v3): только здания; сетка 50 м; замыкание ~100 м (мосты-пробелы
    между кустами застройки); компоненты со связностью; фильтры: >= min_bld зданий,
    центроид в пределах keep_frac зонда; при нескольких компонентах — отсечение чужих
    поселений по имени Nominatim (соседние сёла/город). Дороги в связности НЕ участвуют
    (они соединяют разные сёла «щупальцами»)."""
    if not buildings:
        return list(probe)
    lat_c, lon_c = v['lat'], v['lon']
    grid_m = P('boundary_grid_m')
    margin = P('boundary_margin_m')
    close_cells = max(1, int(round(P('boundary_close_m') / grid_m)))
    min_bld = P('boundary_min_bld')
    keep_frac = P('boundary_keep_frac')

    lats = [b['center'][0] for b in buildings]
    lons = [b['center'][1] for b in buildings]
    dlat = grid_m / M_PER_DEG_LAT
    dlon = grid_m / (M_PER_DEG_LAT * math.cos(math.radians(lat_c)))

    def cell_of(la, lo):
        return (int(math.floor((la - min(lats)) / dlat)),
                int(math.floor((lo - min(lons)) / dlon)))

    bcnt = Counter()
    for b in buildings:
        bcnt[cell_of(*b['center'])] += 1
    filled = set(bcnt)

    # замыкание (дилатация) — мосты через пробелы между кустами застройки
    dil = set()
    for (r_, c_) in filled:
        for dr in range(-close_cells, close_cells + 1):
            for dc in range(-close_cells, close_cells + 1):
                if dr * dr + dc * dc <= close_cells * close_cells + 1:
                    dil.add((r_ + dr, c_ + dc))

    seen = set()
    comps = []
    for cell in dil:
        if cell in seen:
            continue
        stack = [cell]
        comp = set()
        while stack:
            x = stack.pop()
            if x in seen or x not in dil:
                continue
            seen.add(x)
            comp.add(x)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    stack.append((x[0] + dr, x[1] + dc))
        comps.append(comp)

    def comp_buildings(comp):
        return sum(bcnt.get(c2, 0) for c2 in comp if c2 in filled)

    probe_half_w = (probe[2] - probe[0]) * M_PER_DEG_LAT * math.cos(math.radians(lat_c)) / 2
    probe_half_h = (probe[3] - probe[1]) * M_PER_DEG_LAT / 2
    r_max = keep_frac * math.hypot(probe_half_w, probe_half_h)

    kept = []
    for comp in comps:
        if comp_buildings(comp) < min_bld:
            continue
        cla = sum((min(lats) + (c2[0] + 0.5) * dlat) for c2 in comp) / len(comp)
        clo = sum((min(lons) + (c2[1] + 0.5) * dlon) for c2 in comp) / len(comp)
        distm = math.hypot((cla - lat_c) * M_PER_DEG_LAT,
                           (clo - lon_c) * M_PER_DEG_LAT * math.cos(math.radians(lat_c)))
        if distm <= r_max:
            kept.append((comp, cla, clo, distm))
    if not kept:
        kept = [(max(comps, key=comp_buildings), lat_c, lon_c, 0.0)]

    # несколько компонент — отсечь чужие поселения по имени (Nominatim)
    if len(kept) > 1 and cache_path:
        base_name = _nominatim_name(lat_c, lon_c, cache_path)
        if base_name:
            keep2 = []
            for comp, cla, clo, distm in kept:
                if distm < 600:
                    keep2.append((comp, cla, clo, distm))
                    continue
                cname = _nominatim_name(cla, clo, cache_path)
                if cname is None or cname == base_name:
                    keep2.append((comp, cla, clo, distm))
            if keep2:
                kept = keep2

    cells = set().union(*(k[0] for k in kept))
    rmin = min(c2[0] for c2 in cells); rmax = max(c2[0] for c2 in cells)
    cmin = min(c2[1] for c2 in cells); cmax = max(c2[1] for c2 in cells)
    lat_min = min(lats) + rmin * dlat - margin / M_PER_DEG_LAT
    lat_max = min(lats) + (rmax + 1) * dlat + margin / M_PER_DEG_LAT
    lon_min = min(lons) + cmin * dlon - margin / (M_PER_DEG_LAT * math.cos(math.radians(lat_c)))
    lon_max = min(lons) + (cmax + 1) * dlon + margin / (M_PER_DEG_LAT * math.cos(math.radians(lat_c)))
    fb = (max(lon_min, probe[0]), max(lat_min, probe[1]),
          min(lon_max, probe[2]), min(lat_max, probe[3]))
    return list(fb)


def stitch_mosaic(v, bbox, ctx):
    """Мозаика Google z18 по bbox с точной геопривязкой. -> geo dict."""
    from PIL import Image
    Z = ctx.P('zoom')
    key = v['key']
    lat_mid = (bbox[1] + bbox[3]) / 2
    tx0f, tx1f = lon2tx(bbox[0], Z), lon2tx(bbox[2], Z)
    ty0f, ty1f = lat2ty(bbox[3], Z), lat2ty(bbox[1], Z)
    x0, x1 = int(math.floor(tx0f)), int(math.ceil(tx1f))
    y0, y1 = int(math.floor(ty0f)), int(math.ceil(ty1f))
    offx, offy = (tx0f - x0) * 256, (ty0f - y0) * 256
    Wpx, Hpx = int(round((tx1f - tx0f) * 256)), int(round((ty1f - ty0f) * 256))
    tiles = [(tx, ty) for tx in range(x0, x1) for ty in range(y0, y1)]
    print(f"  {v['name']}: {x1-x0}x{y1-y0} тайлов, мозаика {Wpx}x{Hpx}px", flush=True)

    cache = os.path.join(ctx.work, 'tiles')
    tilemap = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (tx, ty), data in ex.map(lambda t: (t, fetch_tile(Z, t[0], t[1], cache)), tiles):
            tilemap[(tx, ty)] = data
    canvas = np.zeros(((y1 - y0) * 256, (x1 - x0) * 256, 3), np.uint8)
    missing = 0
    for (tx, ty), data in tilemap.items():
        if data:
            im = Image.open(io.BytesIO(data)).convert('RGB')
            canvas[(ty - y0) * 256:(ty - y0 + 1) * 256,
                   (tx - x0) * 256:(tx - x0 + 1) * 256] = np.asarray(im)
        else:
            missing += 1
    if missing:
        print(f'  ! пропущено тайлов: {missing}')
    mos = canvas[int(offy):int(offy) + Hpx, int(offx):int(offx) + Wpx]
    Image.fromarray(mos).save(os.path.join(ctx.vdir(key), 'mosaic.jpg'), quality=90)

    mpp = m_per_px(lat_mid, Z)
    geo = dict(west=tx2lon(tx0f, Z), north=ty2lat(ty0f, Z),
               mpp=mpp, W=Wpx, H=Hpx, zoom=Z, missing=missing, bbox=bbox)
    save_json(os.path.join(ctx.vdir(key), 'geo.json'), geo)
    return geo


def stage_fetch(ctx):
    for v in ctx.villages:
        t0 = time.time()
        print(f"=== fetch: {v['name']} ({v.get('hh', '?')} ДХ по заказу) ===")
        key = v['key']
        if v.get('bbox_lock'):
            probe = tuple(v['bbox_lock'])
        else:
            radius = v.get('radius_m', 2500.0) + ctx.P('probe_margin_m')
            dlat, dlon = meters_to_deg(radius, v['lat'])
            probe = (v['lon'] - dlon, v['lat'] - dlat, v['lon'] + dlon, v['lat'] + dlat)
        n_split = max(1, int(math.ceil((probe[2] - probe[0]) * M_PER_DEG_LAT
                                       * math.cos(math.radians(v['lat'])) / 2100)))
        m_split = max(1, int(math.ceil((probe[3] - probe[1]) * M_PER_DEG_LAT / 2100)))
        nodes, ways = {}, {}
        raw_dir = os.path.join(ctx.work, 'osm_raw')
        os.makedirs(raw_dir, exist_ok=True)
        for i in range(n_split):
            for j in range(m_split):
                x0 = probe[0] + (probe[2] - probe[0]) * i / n_split
                x1 = probe[0] + (probe[2] - probe[0]) * (i + 1) / n_split
                y0 = probe[1] + (probe[3] - probe[1]) * j / m_split
                y1 = probe[1] + (probe[3] - probe[1]) * (j + 1) / m_split
                p = os.path.join(raw_dir, f"{key}_{x0:.4f}_{y0:.4f}_{x1:.4f}_{y1:.4f}.xml")
                data = fetch_bbox_raw(x0, y0, x1, y1, p)
                if not data:
                    continue
                n2, w2 = parse_osm(data)
                nodes.update(n2)
                ways.update(w2)
                time.sleep(0.4)
        roads, buildings, pois = osm_features(nodes, ways)
        print(f"  OSM: {len(roads)} дорог, {len(buildings)} зданий, {len(pois)} POI")
        bbox = v.get('bbox_lock') or detect_bbox(v, roads, buildings, probe, ctx.P,
                                                 cache_path=os.path.join(ctx.work, 'nominatim_cache.json'))
        w_km = (bbox[2] - bbox[0]) * M_PER_DEG_LAT * math.cos(math.radians(v['lat'])) / 1000
        h_km = (bbox[3] - bbox[1]) * M_PER_DEG_LAT / 1000
        print(f"  bbox застройки: {bbox[0]:.4f},{bbox[1]:.4f} - {bbox[2]:.4f},{bbox[3]:.4f}"
              f" ({w_km:.2f} x {h_km:.2f} км)")
        save_json(os.path.join(ctx.vdir(key), 'osm.json'),
                  dict(bbox=bbox, roads=roads, buildings=buildings, pois=pois,
                       center=[v['lat'], v['lon']]))
        geo = stitch_mosaic(v, bbox, ctx)
        ratio = len(buildings) / max(1, v.get('hh', len(buildings)))
        print(f"  мозаика {geo['W']}x{geo['H']} ({geo['mpp']:.2f} м/px);"
              f" зданий OSM на ДХ заказа: {ratio:.2f}  [{time.time()-t0:.0f} с]")
        gc.collect()


# ============================================================================
# СТАДИЯ 2: households — домохозяйства
# ============================================================================
def detect_roofs(mos_rgb, mpp):
    """CV-детекция крыш (HSV + морфология). Кандидаты (x, y, w, h)."""
    import cv2
    hsv = cv2.cvtColor(mos_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    blue = (h >= 90) & (h <= 132) & (s > 65) & (v > 50)
    red = ((h <= 12) | (h >= 168)) & (s > 75) & (v > 55)
    orange = (h >= 13) & (h <= 35) & (s > 85) & (v > 95)
    green = (h >= 40) & (h <= 85) & (s > 65) & (v > 50)
    gray = (s < 50) & (v > 140) & (v < 248)
    mask = blue | red | orange | green | gray
    m = (mask * 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    res = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 280 or a > 2400:             # ~40..350 м² при 0.38 м/px
            continue
        x, y, w_, h_ = cv2.boundingRect(c)
        if w_ < 10 or h_ < 10:
            continue
        if a / (w_ * h_) < 0.5 or max(w_, h_) / max(1, min(w_, h_)) > 4.0:
            continue
        res.append((x + w_ / 2, y + h_ / 2, w_, h_))
    return res


def in_zone(la, lo, v, bbox):
    zone = v.get('zone') or {'type': 'bbox'}
    if zone['type'] == 'radius':
        r = zone.get('r', 900.0)
        return math.hypot((la - v['lat']) * M_PER_DEG_LAT,
                          (lo - v['lon']) * M_PER_DEG_LAT * math.cos(math.radians(v['lat']))) < r
    return bbox[0] <= lo <= bbox[2] and bbox[1] <= la <= bbox[3]


def road_points_px(roads, west, north, mpp, W, H, step_m=15.0):
    pts = []
    for r in roads:
        poly = [geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
        if len(poly) < 2:
            continue
        prev = poly[0]
        pts.append(prev)
        for p in poly[1:]:
            seg = math.hypot(p[0] - prev[0], p[1] - prev[1]) * mpp
            n_sub = int(seg / step_m)
            for k in range(1, n_sub + 1):
                pts.append((prev[0] + (p[0] - prev[0]) * k / max(n_sub, 1),
                            prev[1] + (p[1] - prev[1]) * k / max(n_sub, 1)))
            if seg < step_m:
                pts.append(p)
            prev = p
    return np.array([(x, y) for x, y in pts
                     if -100 <= x <= W + 100 and -100 <= y <= H + 100]) if pts else np.zeros((0, 2))


# ============================================================================
# СТАДИЯ 2b: уточнение детекции ДХ (v3) — сблокированные дома и многоэтажки
# ============================================================================
# Кейс (ВКО, Пригородное): OSM-полигон покрывает ДВА сблокированных дома
# с разными крышами, разделённых межевым забором; кластеризация усадеб
# eps=16 м дополнительно склеивает соседние дома в одно ДХ.
#
# Критерии пользователя (Task 46, скорректированное «условие поиска по крышам»):
# различие ЦВЕТА крыш НЕ достаточно — пристройка тоже другого цвета, но
# прямоугольник МЕНЬШЕГО размера, отличной формы в плане. Признаки двух
# владений: (1) увеличенные размеры; (2) ограждение, примыкающее к фасаду
# ПЕРПЕНДИКУЛЯРНО ближе к его ЦЕНТРУ; (3) общая кровля одинаковой формы,
# иногда двух цветов.
#
# A) два канала сплита полигона (линия раздела — только у центра фасада,
#    t=0.38..0.62, обе оси; «увеличенные размеры»: bbox >= 165 м²,
#    длинная сторона >= 12.5 м, части >= 36 м²):
#    A1 «двухцветная пара»: хроматический сплит (dE_ab >= 8.5 И (dE >= 18
#       ИЛИ нейтральная+окрашенная ИЛИ оттенки >= 25°)) при СОПОСТАВИМЫХ
#       частях (ratio >= 0.35 — анти-пристройка);
#    A2 «одноцветная пара»: геометрический центр-сплит — только при
#       найденном ШВЕ/СТЫКЕ кровель (градиент яркости на линии раздела
#       покрывает >= 45% среза) — CV-заместитель признака ограждения;
# B) кластер с 2+ дом-размерными (>= 60 м²) зданиями;
# C) многоэтажки: building=apartments ИЛИ levels>=3 (площадь/этаж 40..3500 м²);
#    N квартир = min(эт x S / 55, эт x подъезды x 4), подъезды = long/28.
#
# Верификация: VLM по кропам (признаки пользователя). Сплит применяется при
# n_properties >= 2 И НЕ пристройка И есть признак раздела (забор у центра
# фасада / стык). Если VLM недоступен — только детерминированные C-кандидаты
# (tier 1), A/B записываются в hh2_pending.json.
HH2_MIN_BBOX_M2 = 165.0     # «увеличенные размеры» (больше типового дома)
HH2_MIN_POLY_M2 = 80.0      # полигон A-сплита должен вмещать 2 дома (2 x 40 м²)
HH2_MIN_LONG_M = 12.5       # длинная сторона (фасад)
HH2_CENTER_T0, HH2_CENTER_T1 = 0.38, 0.62
HH2_MIN_PART_M2 = 36.0      # обе части — дом-размера
HH2_MIN_RATIO = 0.35        # «одинаковая форма»: сопоставимость частей
HH2_GEOM_RATIO = 0.30       # одноцветный канал: чуть мягче
HH2_SEAM_GRAD_T = 40.0      # порог градиента для шва/стыка кровель
HH2_SEAM_FRAC_MIN = 0.45
HH2_MIN_D_EAB = 8.5
HH2_STRONG_D_EAB = 18.0
HH2_NEUTRAL_TOL = 6.0
HH2_COLORED_TOL = 10.0
HH2_MAX_HUE_SHIFT = 25.0
HH2_CLUSTER_BLD_M2 = 60.0
HH2_B_MIN_SEP_M = 10.0
HH2_SANE_FPF = (40.0, 3500.0)


def roof_split_info(mos, poly, mpp):
    """Двухканальный тест «в здании два домохозяйства» (v3, Task 46).

    Канал A1 «двухцветная пара»: хроматический сплит у центра фасада при
    сопоставимых частях; канал A2 «одноцветная пара»: центр-сплит с швом/
    стыком кровель на линии раздела. Цвет — вспомогательный признак;
    решают размер + форма частей + шов (ограждение) + VLM-верификация.
    """
    import cv2
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0i, y0i = int(max(0, math.floor(min(xs)))), int(max(0, math.floor(min(ys))))
    x1i = int(min(mos.shape[1], math.ceil(max(xs))))
    y1i = int(min(mos.shape[0], math.ceil(max(ys))))
    W_, H_ = x1i - x0i, y1i - y0i
    if W_ < 14 or H_ < 14:
        return None
    # 1) «увеличенные размеры»
    if W_ * H_ * mpp * mpp < HH2_MIN_BBOX_M2:
        return None
    if max(W_, H_) * mpp < HH2_MIN_LONG_M:
        return None
    crop = mos[y0i:y1i, x0i:x1i]
    pts = np.array([[p[0] - x0i, p[1] - y0i] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    valid = (mask > 0) & (hsv[..., 2] >= 35) & (hsv[..., 2] <= 250)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    a_ch, b_ch = lab[..., 1].astype(np.float32), lab[..., 2].astype(np.float32)
    hue, sat = hsv[..., 0].astype(np.float32), hsv[..., 1].astype(np.float32)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    Xg, Yg = np.meshgrid(np.arange(W_, dtype=np.float32),
                         np.arange(H_, dtype=np.float32))

    best_chroma = None   # A1: двухцветная пара
    best_geom = None     # A2: одноцветная пара со швом
    for axis in (0, 1):
        coord = Xg if axis == 0 else Yg
        span = W_ if axis == 0 else H_
        grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1 if axis == 0 else 0,
                                0 if axis == 0 else 1, ksize=3)) / 4.0
        for t in np.arange(HH2_CENTER_T0, HH2_CENTER_T1 + 1e-9, 0.02):
            cut = t * span
            m0 = valid & (coord < cut)
            m1 = valid & (coord >= cut)
            a0_m2 = float(m0.sum()) * mpp * mpp
            a1_m2 = float(m1.sum()) * mpp * mpp
            if a0_m2 < HH2_MIN_PART_M2 or a1_m2 < HH2_MIN_PART_M2:
                continue
            ratio = min(a0_m2, a1_m2) / max(a0_m2, a1_m2)
            if ratio < HH2_GEOM_RATIO:
                continue
            r = {}
            for lb, m in ((0, m0), (1, m1)):
                sm = sat[m]
                r[lb] = dict(n=int(m.sum()),
                             a=float(a_ch[m].mean()), b=float(b_ch[m].mean()),
                             cx=float(Xg[m].mean()), cy=float(Yg[m].mean()),
                             hue=float(hue[m][sm > 30].mean()) * 2.0
                             if (sm > 30).sum() > 30 else None)
            dE = math.hypot(r[0]['a'] - r[1]['a'], r[0]['b'] - r[1]['b'])
            n0 = abs(r[0]['a'] - 128) + abs(r[0]['b'] - 128)
            n1 = abs(r[1]['a'] - 128) + abs(r[1]['b'] - 128)
            nc = (n0 < HH2_NEUTRAL_TOL and n1 >= HH2_COLORED_TOL) or \
                 (n1 < HH2_NEUTRAL_TOL and n0 >= HH2_COLORED_TOL)
            hd = None
            if r[0]['hue'] is not None and r[1]['hue'] is not None:
                dh = abs(r[0]['hue'] - r[1]['hue'])
                hd = min(dh, 360.0 - dh)
            two_color = (dE >= HH2_MIN_D_EAB and
                         (dE >= HH2_STRONG_D_EAB or nc or
                          (hd is not None and hd >= HH2_MAX_HUE_SHIFT)))
            band = valid & (np.abs(coord - cut) <= 1.5)
            nb = int(band.sum())
            seam_frac = float((grad[band] > HH2_SEAM_GRAD_T).sum()) / max(nb, 1) \
                if nb > 0 else 0.0
            rec = dict(axis=axis, t=round(float(t), 2), ratio=round(ratio, 2),
                       dE=dE, two_color=two_color, seam_frac=seam_frac, r=r)
            if two_color and ratio >= HH2_MIN_RATIO:
                score = (2.0 * min(seam_frac / HH2_SEAM_FRAC_MIN, 1.0) +
                         min(dE / 15.0, 1.5) + 1.0 - abs(t - 0.5) / 0.13)
                if best_chroma is None or score > best_chroma[0]:
                    best_chroma = (score, rec)
            if seam_frac >= HH2_SEAM_FRAC_MIN:
                score = seam_frac + 1.0 - abs(t - 0.5) / 0.13
                if best_geom is None or score > best_geom[0]:
                    best_geom = (score, rec)

    if best_chroma is not None:
        pick = best_chroma[1]
    elif best_geom is not None:
        pick = best_geom[1]
    else:
        return None
    r0, r1 = pick['r'][0], pick['r'][1]
    return dict(dE_ab=round(pick['dE'], 1), axis=pick['axis'], t=pick['t'],
                ratio=pick['ratio'], two_color=bool(pick['two_color']),
                seam_frac=round(pick['seam_frac'], 2),
                part0=dict(cx=round(r0['cx'] + x0i, 1), cy=round(r0['cy'] + y0i, 1),
                           area_m2=round(r0['n'] * mpp * mpp, 1)),
                part1=dict(cx=round(r1['cx'] + x0i, 1), cy=round(r1['cy'] + y0i, 1),
                           area_m2=round(r1['n'] * mpp * mpp, 1)))


def _hh2_vlm_available():
    """VLM-верификация доступна? Вызовы идут через CLI `z-ai`, поэтому
    доступность определяется наличием CLI (запасной вариант — python-спека
    SDK; в v2.4 спека из python недоступна, из-за чего VLM не вызывался
    вовсе — найдено при возобновлении Task 50). Сами вызовы ловим try/except."""
    global _HH2_VLM_CACHE
    if _HH2_VLM_CACHE is not None:
        return _HH2_VLM_CACHE
    ok = False
    try:
        import shutil
        if shutil.which('z-ai'):
            ok = True
    except Exception:
        ok = False
    if not ok:
        try:
            import importlib.util
            ok = importlib.util.find_spec('z-ai-web-dev-sdk') is not None
        except Exception:
            ok = False
    _HH2_VLM_CACHE = ok
    return _HH2_VLM_CACHE


_HH2_VLM_CACHE = None
_HH2_VLM_VERDICTS = None    # кэш вердиктов {md5(jpeg-кропа): n} — переживает прогоны
_HH2_VLM_CACHE_FILE = None  # <vdir>/vlm_verdicts.json; ставится в refine_households


def _hh2_vlm_save_cache():
    """Атомарное сохранение кэша вердиктов (tmp+rename)."""
    if not _HH2_VLM_CACHE_FILE or _HH2_VLM_VERDICTS is None:
        return
    try:
        tmp = _HH2_VLM_CACHE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_HH2_VLM_VERDICTS, f)
        os.replace(tmp, _HH2_VLM_CACHE_FILE)
    except Exception:
        pass


def _hh2_vlm_nproperties(crop_rgb, note=''):
    """Вопрос VLM: сколько владений на кропе. None = сервис недоступен.
    Вердикты кэшируются по md5 кропа (переживают прогоны и обрывы квоты;
    повторные запросы того же здания — бесплатно)."""
    try:
        import cv2
        import re
        import subprocess, tempfile, os as _os
        ok, buf = cv2.imencode('.jpg', crop_rgb, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            return None
        key = hashlib.md5(buf.tobytes()).hexdigest()
        if _HH2_VLM_VERDICTS is not None and key in _HH2_VLM_VERDICTS:
            return _HH2_VLM_VERDICTS[key]
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(buf.tobytes())
            path = f.name
        try:
            time.sleep(0.6)  # щадящий темп (без кэша — только реальные вызовы)
            prompt = ('Спутниковый снимок села (Восточный Казахстан, ~0.4 м/px). '
                      'Красный контур — строение по геоданным; вокруг — дворы, '
                      'заборы, соседние участки. Признаки ДВУХ и более владений: '
                      '(1) увеличенные размеры — строение крупнее соседних домов; '
                      '(2) забор примыкает к фасаду ПЕРПЕНДИКУЛЯРНО, ближе к '
                      'ЦЕНТРУ фасада, продолжаясь вглубь двора; (3) общая кровля '
                      'одинаковой формы, иногда двух цветов. НЕ признак: пристройка '
                      '— прямоугольник меньшего размера, отличной формы, часто '
                      'другого цвета, без забора. Ответь ТОЛЬКО JSON: '
                      '{"n_properties": <int>, "fence_between": <bool>, '
                      '"annex": <bool>}')
            r = subprocess.run(['z-ai', 'vision', '-p', prompt, '-i', path],
                               capture_output=True, text=True, timeout=120)
            import json as _json
            m = re.search(r'\{[^{}]*\}', r.stdout, re.S)
            js = _json.loads(m.group(0)) if m else None
            if not (js and 'n_properties' in js):
                return None
            # гейт Task 46: пристройка без забора — не владение
            n = 1 if (js.get('annex') and not js.get('fence_between')) \
                else int(js['n_properties'])
            if _HH2_VLM_VERDICTS is not None:
                _HH2_VLM_VERDICTS[key] = n
                _hh2_vlm_save_cache()
            return n
        finally:
            _os.unlink(path)
    except Exception:
        return None


def refine_households(ctx, v, households, yard_map, all_blds, mos, mpp, west, north):
    """Уточнение ДХ: сплиты A/B + квартиры C. Возвращает (n_split, n_apt, pending)."""
    import cv2
    hh_by_id = {h['id']: h for h in households}
    next_id = max(hh_by_id) + 1
    n_split = n_apt = pending = 0
    use_vlm = ctx.P('hh_vlm_verify', True) and _hh2_vlm_available()
    # кэш вердиктов по md5 кропа: переживает прогоны/обрывы квоты (Task 50)
    global _HH2_VLM_VERDICTS, _HH2_VLM_CACHE_FILE
    _HH2_VLM_CACHE_FILE = os.path.join(ctx.vdir(v['key']), 'vlm_verdicts.json')
    if _HH2_VLM_VERDICTS is None:
        try:
            with open(_HH2_VLM_CACHE_FILE, encoding='utf-8') as f:
                _HH2_VLM_VERDICTS = json.load(f)
            print(f'  VLM: кэш вердиктов {len(_HH2_VLM_VERDICTS)} шт.')
        except Exception:
            _HH2_VLM_VERDICTS = {}

    def crop_for(b, pad_m=35.0):
        xs = [p[0] for p in b['poly']]; ys = [p[1] for p in b['poly']]
        pad = pad_m / mpp
        x0 = int(max(0, min(xs) - pad)); y0 = int(max(0, min(ys) - pad))
        x1 = int(min(mos.shape[1], max(xs) + pad)); y1 = int(min(mos.shape[0], max(ys) + pad))
        c = mos[y0:y1, x0:x1].copy()
        pts = np.array([[p[0] - x0, p[1] - y0] for p in b['poly']], dtype=np.int32)
        cv2.polylines(c, [pts], True, (255, 60, 60), 3)
        return c

    vlm_off = [False]

    def vlm_nprop(b):
        """Вердикт VLM по кропу здания; None = вердикта нет (сервис недоступен
        или выключен конфигом) — в этом случае сплит НЕ применяется."""
        if not use_vlm or vlm_off[0]:
            return None
        n = _hh2_vlm_nproperties(crop_for(b))
        if n is None:
            vlm_off[0] = True   # сервис недоступен — до конца прогона не зовём
            global _HH2_VLM_CACHE
            _HH2_VLM_CACHE = False
        return n

    def want_split(b):
        """Решение о сплите: VLM-вердикт n>=2; без вердикта — только явный
        агрессивный режим hh_split_no_vlm (по умолчанию ВЫКЛ: ~половина
        хрома-кандидатов — пристройки, см. валидацию ВКО, Task 45)."""
        n = vlm_nprop(b)
        if n is not None:
            return n >= 2
        return bool(ctx.P('hh_split_no_vlm', False))

    # --- A: сплит главного здания по хроматике ---
    for h in list(households):
        bl, main = yard_map.get(h['id'], ([], None))
        if main is None or 'poly' not in main:
            continue
        if main['w'] * main['h'] * mpp * mpp < HH2_MIN_POLY_M2:
            continue
        info = roof_split_info(mos, main['poly'], mpp)
        if not info:
            continue
        if not want_split(main):
            pending += 1
            continue
        p0, p1 = info['part0'], info['part1']
        d0 = math.hypot(h['cx'] - p0['cx'], h['cy'] - p0['cy'])
        d1 = math.hypot(h['cx'] - p1['cx'], h['cy'] - p1['cy'])
        near, far = (p0, p1) if d0 <= d1 else (p1, p0)
        h['cx'], h['cy'] = near['cx'], near['cy']
        h['lat'], h['lon'] = px_to_geo(near['cx'], near['cy'], v['lat'], west, north, mpp)
        la, lo = px_to_geo(far['cx'], far['cy'], v['lat'], west, north, mpp)
        households.append(dict(id=next_id, cx=far['cx'], cy=far['cy'],
                               lat=round(la, 6), lon=round(lo, 6), n_bld=1,
                               main_w=h['main_w'], main_h=h['main_h'],
                               main_src=h['main_src'], parent_id=h['id'],
                               source='split_roof', dE_ab=info['dE_ab']))
        next_id += 1
        n_split += 1

    # --- B: кластеры с 2+ дом-размерными зданиями ---
    for h in list(households):
        if h.get('source'):
            continue
        bl, main = yard_map.get(h['id'], ([], None))
        bigs = [b for b in bl
                if b is not main and b['w'] * b['h'] * mpp * mpp >= HH2_CLUSTER_BLD_M2
                and math.hypot(b['cx'] - main['cx'], b['cy'] - main['cy']) * mpp >= HH2_B_MIN_SEP_M]
        if len(bigs) < 1:
            continue
        n = vlm_nprop(main)
        if n is not None:
            k = int(min(n - 1, len(bigs)))
        elif ctx.P('hh_split_no_vlm', False):
            k = len(bigs)
        else:
            pending += 1
            continue
        for b in bigs[:k]:
            la, lo = px_to_geo(b['cx'], b['cy'], v['lat'], west, north, mpp)
            households.append(dict(id=next_id, cx=b['cx'], cy=b['cy'],
                                   lat=round(la, 6), lon=round(lo, 6), n_bld=1,
                                   main_w=b['w'], main_h=b['h'], main_src=b['src'],
                                   parent_id=h['id'], source='split_yard'))
            next_id += 1
            n_split += 1

    # --- C: многоэтажки (детерминированно по OSM-тегам, все здания зоны) ---
    seen_apt = set()
    hh_pos = [(h['cx'], h['cy'], h) for h in households]
    for b in all_blds:
        if b['src'] != 'osm' or id(b) in seen_apt:
            continue
        t = b.get('tags', {})
        try:
            lv = float(t.get('building:levels', 1) or 1)
        except ValueError:
            lv = 1
        area = b['w'] * b['h'] * mpp * mpp
        fpf = area / max(1.0, lv)
        if not (t.get('building') == 'apartments' or
                (lv >= 3 and HH2_SANE_FPF[0] <= fpf <= HH2_SANE_FPF[1])):
            continue
        seen_apt.add(id(b))
        # родитель: ближайшее ДХ (для привязки дропа к муфте); многоэтажка
        # сама может быть ДХ (тогда обновляем его позицию) или сиротой
        best_h, best_d = None, 1e18
        for (cx, cy, h) in hh_pos:
            d = math.hypot(b['cx'] - cx, b['cy'] - cy) * mpp
            if d < best_d:
                best_h, best_d = h, d
        h = best_h
        long_m = max(b['w'], b['h']) * mpp
        n_a = round(min(lv * area / 55.0, lv * max(1, round(long_m / 28.0)) * 4))
        N = max(2, min(n_a, 400))
        horiz = b['w'] >= b['h']
        spacing = min(6.0, long_m / (N + 1)) / mpp
        pos = []
        for i in range(N):
            off = (i - (N - 1) / 2.0) * spacing
            pos.append((b['cx'] + off, b['cy']) if horiz else (b['cx'], b['cy'] + off))
        first = (h is not None and math.hypot(h['cx'] - b['cx'], h['cy'] - b['cy']) * mpp < 1.0)
        for (px_, py_) in pos:
            la, lo = px_to_geo(px_, py_, v['lat'], west, north, mpp)
            if first:
                h.update(cx=px_, cy=py_, lat=round(la, 6), lon=round(lo, 6),
                         n_bld=1, main_w=b['w'], main_h=b['h'], main_src='osm',
                         apt_total=N, source='apartments_main')
                first = False
                continue
            households.append(dict(id=next_id, cx=px_, cy=py_,
                                   lat=round(la, 6), lon=round(lo, 6), n_bld=1,
                                   main_w=b['w'], main_h=b['h'], main_src='osm',
                                   parent_id=h['id'] if h else None,
                                   apt_total=N, source='apartments'))
            next_id += 1
            n_apt += 1
    return n_split, n_apt, pending


def stage_households(ctx):
    from PIL import Image, ImageDraw
    for v in ctx.villages:
        print(f"=== households: {v['name']} ===")
        key = v['key']
        d = load_json(os.path.join(ctx.vdir(key), 'osm.json'))
        geo = load_json(os.path.join(ctx.vdir(key), 'geo.json'))
        mpp, west, north = geo['mpp'], geo['west'], geo['north']
        bbox = d['bbox']
        mos = np.asarray(Image.open(os.path.join(ctx.vdir(key), 'mosaic.jpg')).convert('RGB'))
        H, W = mos.shape[:2]
        road_arr = road_points_px(d['roads'], west, north, mpp, W, H)

        def near_road(x, y, max_m):
            if len(road_arr) == 0:
                return False
            d2 = ((road_arr[:, 0] - x) ** 2 + (road_arr[:, 1] - y) ** 2).min()
            return math.sqrt(d2) * mpp < max_m

        osm_blds = []
        for b in d['buildings']:
            la, lo = b['center']
            if not in_zone(la, lo, v, bbox):
                continue
            pts = [geo_to_px(pla, plo, west, north, mpp) for pla, plo in b['poly']]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if min(xs) < -80 or min(ys) < -80 or max(xs) > W + 80 or max(ys) > H + 80:
                continue
            osm_blds.append(dict(cx=(min(xs) + max(xs)) / 2, cy=(min(ys) + max(ys)) / 2,
                                 w=max(xs) - min(xs), h=max(ys) - min(ys),
                                 src='osm', tags=b.get('tags', {}), poly=pts))

        cv_mode = v.get('cv_supplement', 'auto')
        deficit = 100 * (1 - len(osm_blds) / max(1, v.get('hh', len(osm_blds))))
        use_cv = (cv_mode == 'on') or (cv_mode == 'auto' and deficit > ctx.P('hh_cv_deficit_pct'))
        cv_blds = []
        if use_cv:
            print(f"  CV-супплект: ON (дефицит OSM {deficit:.0f}%)")
            roofs = detect_roofs(mos, mpp)
            accepted = []
            for it in range(2):   # итеративный контекст: возле дорог -> возле принятых
                for (x, y, w_, h_) in roofs:
                    if any(abs(x - a[0]) < 8 and abs(y - a[1]) < 8 for a in accepted):
                        continue
                    if any(math.hypot(x - b['cx'], y - b['cy']) * mpp < ctx.P('hh_cv_min_sep_m')
                           for b in osm_blds):
                        continue
                    ctx_ok = (near_road(x, y, ctx.P('hh_cv_near_road_m')) if it == 0 else
                              any(math.hypot(x - b['cx'], y - b['cy']) * mpp < ctx.P('hh_cv_ctx_m')
                                  for b in osm_blds + [dict(cx=a[0], cy=a[1]) for a in accepted]))
                    if ctx_ok:
                        accepted.append((x, y, w_, h_))
            cv_blds = [dict(cx=a[0], cy=a[1], w=a[2], h=a[3], src='cv', tags={},
                        poly=[(a[0] - a[2] / 2, a[1] - a[3] / 2), (a[0] + a[2] / 2, a[1] - a[3] / 2),
                              (a[0] + a[2] / 2, a[1] + a[3] / 2), (a[0] - a[2] / 2, a[1] + a[3] / 2)])
                  for a in accepted]
        else:
            print(f"  CV-супплект: off (дефицит OSM {deficit:.0f}%)")

        all_blds = osm_blds + cv_blds
        eps = ctx.P('hh_eps_m') / mpp
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

        households = []
        yard_map = {}
        for yard in yards:
            bl = [all_blds[j] for j in yard]
            main = max(bl, key=lambda b: b['w'] * b['h'] * (1.6 if b['src'] == 'osm' else 1.0))
            if main['w'] * main['h'] * mpp * mpp < ctx.P('hh_main_area_m2'):
                continue
            cx = sum(b['cx'] for b in bl) / len(bl)
            cy = sum(b['cy'] for b in bl) / len(bl)
            if not near_road(cx, cy, ctx.P('hh_road_max_m')):
                continue
            la, lo = px_to_geo(main['cx'], main['cy'], v['lat'], west, north, mpp)
            households.append(dict(id=len(households) + 1, cx=main['cx'], cy=main['cy'],
                                   lat=round(la, 6), lon=round(lo, 6), n_bld=len(bl),
                                   main_w=main['w'], main_h=main['h'], main_src=main['src']))
            yard_map[households[-1]['id']] = (bl, main)
        dev = 100 * (len(households) - v.get('hh', len(households))) / max(1, v.get('hh', 1))
        print(f"  OSM {len(osm_blds)} + CV {len(cv_blds)} -> {len(households)} ДХ"
              f" (заказ {v.get('hh', '?')}, {dev:+.1f}%)")

        if ctx.P('hh_refine', True):
            n_sp, n_ap, pend = refine_households(ctx, v, households, yard_map,
                                                 all_blds, mos, mpp, west, north)
            dev = 100 * (len(households) - v.get('hh', len(households))) / max(1, v.get('hh', 1))
            print(f"  уточнение v2: сплиты сблокированных {n_sp}, квартиры "
                  f"многоэтажек {n_ap} (кв. в ожидании VLM: {pend}) -> {len(households)} ДХ"
                  f" ({dev:+.1f}%)")

        save_json(os.path.join(ctx.vdir(key), 'households.json'), households)

        img = Image.fromarray(mos)
        img.thumbnail((2200, 2200))
        k = img.width / W
        dr = ImageDraw.Draw(img)
        for h_ in households:
            x, y = h_['cx'] * k, h_['cy'] * k
            dr.rectangle([x - 3, y - 3, x + 3, y + 3], fill=(255, 70, 70))
        img.save(os.path.join(ctx.vdir(key), 'households_preview.jpg'), quality=88)
        del mos, img
        gc.collect()


# ============================================================================
# СТАДИЯ 3: anchor — здание-якорь (ЦУ/ОРШ)
# ============================================================================
def anchor_candidates(v, ctx):
    key = v['key']
    geo = load_json(os.path.join(ctx.vdir(key), 'geo.json'))
    d = load_json(os.path.join(ctx.vdir(key), 'osm.json'))
    hhs = load_json(os.path.join(ctx.vdir(key), 'households.json'))
    mpp, west, north = geo['mpp'], geo['west'], geo['north']
    clat = sum(h['lat'] for h in hhs) / max(1, len(hhs))
    clon = sum(h['lon'] for h in hhs) / max(1, len(hhs))

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

    bbox = d['bbox']
    cands = []
    for b in d['buildings']:
        la, lo = b['center']
        if not in_zone(la, lo, v, bbox):
            continue
        tags = b.get('tags', {})
        bt = tags.get('building', 'yes')
        if bt in BAD_BUILDINGS:
            continue
        x, y = geo_to_px(la, lo, west, north, mpp)
        pts = [geo_to_px(pla, plo, west, north, mpp) for pla, plo in b['poly']]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        asp = max(bw, bh) / max(1e-6, min(bw, bh))
        compact = 1.0 if asp < 2.2 else (2.2 / asp)
        dcent_m = math.hypot((la - clat) * M_PER_DEG_LAT,
                             (lo - clon) * M_PER_DEG_LAT * math.cos(math.radians(la)))
        centr = max(0.0, 1.0 - dcent_m / 1200.0)
        area = b['area']
        sz = 1.0 if 150 <= area <= 500 else (0.75 if 90 <= area < 150
                                             else (0.5 if 500 < area <= 900 else 0.25))
        rd = road_dist(x, y)
        road_s = 1.0 if rd < 25 else (0.6 if rd < 50 else (0.3 if rd < 90 else 0.1))
        tag_bonus = 1.4 if (tags.get('amenity') or
                            bt in ('public', 'civic', 'commercial', 'retail', 'office')) else 1.0
        cands.append(dict(id=b['id'], lat=la, lon=lo, x=x, y=y, area=area, asp=round(asp, 1),
                          rd=round(rd, 1), dcent=round(dcent_m), bw=bw, bh=bh,
                          score=round(sz * centr * road_s * compact * tag_bonus, 4), tags=tags))
    cands.sort(key=lambda c: -c['score'])
    return cands


def stage_anchor(ctx):
    from PIL import Image, ImageDraw, ImageFont
    FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    for v in ctx.villages:
        print(f"=== anchor: {v['name']} ===")
        key = v['key']
        cands = anchor_candidates(v, ctx)
        if not cands:
            raise RuntimeError(f'{key}: нет кандидатов ЦУ — проверьте OSM/зону')
        forced = v.get('force_anchor')
        if forced:
            cands.sort(key=lambda c: (c['id'] != forced, -c['score']))
            print(f"  принудительный ОРШ: id={cands[0]['id']} (score {cands[0]['score']})")
        save_json(os.path.join(ctx.vdir(key), 'anchor_candidates.json'),
                  [dict(id=c['id'], lat=c['lat'], lon=c['lon'], x=c['x'], y=c['y'],
                        area=c['area'], score=c['score'], tags=c['tags']) for c in cands[:5]])
        print('  топ-5 кандидатов ЦУ:')
        for c in cands[:5]:
            print(f"   id={c['id']} {c['area']:.0f} м² asp={c['asp']} дорога={c['rd']}м "
                  f"центр={c['dcent']}м score={c['score']} "
                  f"тег={c['tags'].get('building', '?')}/{c['tags'].get('name', '')}")
        img = Image.open(os.path.join(ctx.vdir(key), 'mosaic.jpg')).convert('RGB')
        W, H = img.size
        cx, cy = int(cands[0]['x']), int(cands[0]['y'])
        x0, y0 = max(0, cx - 500), max(0, cy - 500)
        crop = img.crop((x0, y0, min(W, x0 + 1000), min(H, y0 + 1000))).copy()
        dr = ImageDraw.Draw(crop)
        f = ImageFont.truetype(FB, 26)
        for i, c in enumerate(cands[:3]):
            dr.ellipse([c['x'] - x0 - 16, c['y'] - y0 - 16, c['x'] - x0 + 16, c['y'] - y0 + 16],
                       outline=(255, 230, 0) if i == 0 else (0, 255, 255), width=4)
            dr.text((c['x'] - x0 + 20, c['y'] - y0 - 30), str(i + 1), font=f,
                    fill=(255, 230, 0) if i == 0 else (0, 255, 255))
        crop.save(os.path.join(ctx.vdir(key), 'anchor_preview.png'))
        print(f"  превью: work/{key}/anchor_preview.png — ПРОВЕРЬТЕ кандидата №1"
              f" (или задайте force_anchor в config)")
        del img, crop
        gc.collect()


# ============================================================================
# СТАДИЯ 4: network — древовидная сеть (MST по дорогам -> SPT -> муфты -> дропы)
# ============================================================================
class RoadGraph:
    def __init__(self):
        self.pts = []
        self.idx = {}
        self.edges = []

    def add_node(self, x, y):
        k = (round(x, 1), round(y, 1))
        i = self.idx.get(k)
        if i is None:
            i = len(self.pts)
            self.pts.append((x, y))
            self.idx[k] = i
        return i

    def add_polyline(self, pts_px, mpp):
        prev = None
        for p in pts_px:
            cur = self.add_node(p[0], p[1])
            if prev is not None and cur != prev:
                d = math.hypot(self.pts[cur][0] - self.pts[prev][0],
                               self.pts[cur][1] - self.pts[prev][1]) * mpp
                if d > 0.05:
                    self.edges.append((prev, cur, d))
            prev = cur


def build_road_graph(osm, geo, mpp, P, bounds=None):
    """Полный дорожный граф OSM (те же узлы/рёбра, что строит build_network).

    Нужен для прокладки ФИДЕРНЫХ трасс схемы D по кратчайшим путям (Дейкстра):
    путь «точка-точка» (ЦУ -> зонный ОРШ) внутри дерева распределения
    (приближение дерева Штейнера, минимум суммарной длины) может быть
    вдвое длиннее кратчайшего маршрута по улицам (шаг 43 проекта ВКО).
    Возвращает dict: P (узлы), kdt, C (CSR расстояний), allowed (маска bounds).
    """
    from scipy.spatial import cKDTree
    from scipy.sparse import csr_matrix

    west, north = geo['west'], geo['north']
    W, H = geo['W'], geo['H']
    G = RoadGraph()
    mstep = P('net_densify_m')
    for r in osm['roads']:
        pts = [geo_to_px(la, lo, west, north, mpp) for la, lo in r['pts']]
        if all(p[0] < -200 or p[0] > W + 200 or p[1] < -200 or p[1] > H + 200 for p in pts):
            continue
        dens = [pts[0]]
        for p in pts[1:]:
            q = dens[-1]
            seg = math.hypot(p[0] - q[0], p[1] - q[1]) * mpp
            n_sub = int(seg / mstep)
            for k in range(1, n_sub + 1):
                dens.append((q[0] + (p[0] - q[0]) * k / max(n_sub, 1),
                             q[1] + (p[1] - q[1]) * k / max(n_sub, 1)))
            if seg < mstep:
                dens.append(p)
        G.add_polyline(dens, mpp)
    Pt = np.array(G.pts)
    n = len(Pt)
    allowed = np.ones(n, bool)
    if bounds is not None:
        bx0, by0, bx1, by1 = bounds
        allowed = ((Pt[:, 0] >= bx0) & (Pt[:, 0] <= bx1) &
                   (Pt[:, 1] >= by0) & (Pt[:, 1] <= by1))
    rows, cols, vals = [], [], []
    for (u, w, l) in G.edges:
        if not (allowed[u] and allowed[w]):
            continue
        rows += [u, w]; cols += [w, u]; vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(n, n))
    return dict(P=Pt, kdt=cKDTree(Pt), C=C, allowed=allowed)


def yard_polyline(hh, road_pt, mpp):
    """Дворовая прокладка: от дороги вдоль участка/забора к стене дома (ломаная)."""
    hx, hy = hh['cx'], hh['cy']
    sx, sy = road_pt
    dx, dy = hx - sx, hy - sy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return [[sx, sy], [hx, hy]]
    hsh = int(hashlib.md5(str(hh['id']).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    f_along = 0.30 + 0.35 * hsh
    side = 1 if hsh > 0.5 else -1
    ux, uy = dx / dist, dy / dist
    px_, py_ = -uy, ux
    if dist * mpp < 10:
        m1 = [sx + dx * 0.55 + px_ * 2.5 * side, sy + dy * 0.55 + py_ * 2.5 * side]
        return [[sx, sy], m1, [hx, hy]]
    a1 = [sx + px_ * dist * f_along * 0.55 + ux * dist * 0.22,
          sy + py_ * dist * f_along * 0.55 + uy * dist * 0.22]
    a2 = [a1[0] + ux * dist * 0.5 + px_ * dist * 0.12 * side,
          a1[1] + uy * dist * 0.5 + py_ * dist * 0.12 * side]
    return [[sx, sy], a1, a2, [hx, hy]]


def build_network(key, osm, hhs, anchor, geo, mpp, P, bounds=None, verbose=True):
    """Ядро проектирования сети.

    bounds: (x0,y0,x1,y1) в px мозаики — клип по пользовательскому кадру (None = всё).
    Возвращает network.json-совместимый dict (координаты px мозаики).
    """
    from scipy.spatial import cKDTree
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    west, north = geo['west'], geo['north']
    W, H = geo['W'], geo['H']
    MERGE_M, DEDUP_M = P('net_merge_m'), P('net_dedup_m')
    MAX_DROP_M = P('net_max_drop_m')
    INTERM = P('net_intermediate_m')

    ax, ay = anchor['x'], anchor['y']

    _rg = build_road_graph(osm, geo, mpp, P, bounds)
    Pt, tree, C, allowed = _rg['P'], _rg['kdt'], _rg['C'], _rg['allowed']
    n = len(Pt)
    if verbose:
        print(f'  граф: {n} узлов, {C.nnz // 2} рёбер')

    root_id = int(tree.query([ax, ay])[1])
    hh_nodes, snap_d = [], []
    for h in hhs:
        d, i = tree.query([h['cx'], h['cy']])
        if d * mpp > P('net_snap_max_m') or not allowed[i]:
            hh_nodes.append(None)
        else:
            hh_nodes.append(int(i))
        snap_d.append(float(d * mpp))
    if verbose:
        sd = sorted(snap_d)
        print(f'  привязка ДХ к дорогам: медиана {sd[len(sd)//2]:.0f} м, '
              f'p90 {sd[9*len(sd)//10]:.0f} м, макс {sd[-1]:.0f} м;'
              f' вне допуска: {sum(x is None for x in hh_nodes)}')

    ok = [i for i in range(len(hhs)) if hh_nodes[i] is not None]
    terminals = list(dict.fromkeys([root_id] + [hh_nodes[i] for i in ok]))
    tpos = {t: i for i, t in enumerate(terminals)}

    Dm, pred_m = dijkstra(C, indices=terminals, return_predecessors=True)

    K = len(terminals)
    Dt = np.array([[Dm[i][t] for t in terminals] for i in range(K)])
    in_tree = [False] * K
    best_w = [np.inf] * K
    parent = [-1] * K
    best_w[0] = 0.0
    mst_pairs = []
    for _ in range(K):
        b, bw = -1, np.inf
        for i in range(K):
            if not in_tree[i] and best_w[i] < bw:
                b, bw = i, best_w[i]
        if b < 0:
            break
        in_tree[b] = True
        if parent[b] >= 0:
            mst_pairs.append((terminals[parent[b]], terminals[b]))
        for j in range(K):
            if not in_tree[j] and Dt[b][j] < best_w[j]:
                best_w[j] = Dt[b][j]
                parent[j] = b

    union = set()
    for (u, w) in mst_pairs:
        iu = tpos[u]
        cur = w
        while cur != u and cur >= 0:
            p = int(pred_m[iu][cur])
            if p < 0:
                break
            union.add((min(p, cur), max(p, cur)))
            cur = p
    ur, uc, uv = [], [], []
    elen = {}
    for (u, w) in union:
        l = math.hypot(Pt[u][0] - Pt[w][0], Pt[u][1] - Pt[w][1]) * mpp
        elen[(u, w)] = l
        ur += [u, w]; uc += [w, u]; uv += [l, l]
    U = csr_matrix((uv, (ur, uc)), shape=(n, n))
    DU, predU = dijkstra(U, indices=root_id, return_predecessors=True)
    predU = predU.astype(np.int64)

    def path_to_root(node):
        pth = [node]
        cur = node
        guard = 0
        while cur != root_id:
            p = int(predU[cur])
            if p < 0:
                return None
            pth.append(p)
            cur = p
            guard += 1
            if guard > n:
                return None
        return pth

    hh_paths = {i: path_to_root(hh_nodes[i]) for i in ok}

    couplers = {}

    def add_coup(node, hi):
        couplers.setdefault(node, []).append(hi)

    order = sorted([i for i in ok if hh_paths[i] is not None],
                   key=lambda i: DU[hh_nodes[i]])
    for hi in order:
        pth = hh_paths[hi]
        acc = 0.0
        serve = None
        for i in range(len(pth) - 1):
            if pth[i] in couplers:
                serve = pth[i]
                break
            acc += elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
            if acc > MERGE_M:
                break
        add_coup(serve if serve is not None else pth[0], hi)

    tree_edges = set()
    for hi in order:
        pth = hh_paths[hi]
        for i in range(len(pth) - 1):
            tree_edges.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
    deg = {}
    for (u, w) in tree_edges:
        deg[u] = deg.get(u, 0) + 1
        deg[w] = deg.get(w, 0) + 1
    for node, dg in deg.items():
        if dg >= 3:
            couplers.setdefault(node, [])

    def path_dist_nodes(a, b):
        if a == b:
            return 0.0
        pa = path_to_root(a)
        if pa is None or b not in pa:
            return 1e9
        ib = pa.index(b)
        return sum(elen.get((min(pa[i], pa[i + 1]), max(pa[i], pa[i + 1])), 0)
                   for i in range(ib))

    changed = True
    while changed:
        changed = False
        nodes_c = sorted(couplers.keys(), key=lambda c: DU[c])
        for i in range(len(nodes_c)):
            if nodes_c[i] not in couplers:
                continue
            for j in range(i + 1, len(nodes_c)):
                a, b = nodes_c[i], nodes_c[j]
                if a not in couplers or b not in couplers:
                    continue
                if path_dist_nodes(b, a) < DEDUP_M:
                    couplers[a].extend(couplers.pop(b))
                    changed = True
                    break
            if changed:
                break

    def serving(hi):
        pth = hh_paths[hi]
        for i in range(len(pth)):
            if pth[i] in couplers:
                return pth[i]
        return root_id

    def drop_len(hi, sc):
        pth = hh_paths[hi]
        si = pth.index(sc)
        return sum(elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
                   for i in range(si))

    for hi in order:
        pth = hh_paths[hi]
        hh = hhs[hi]
        a_h = pth[0]
        yard = math.hypot(hh['cx'] - Pt[a_h][0], hh['cy'] - Pt[a_h][1]) * mpp
        sc = serving(hi)
        dl = drop_len(hi, sc) + yard
        while dl > MAX_DROP_M:
            acc = 0.0
            placed = None
            for i in range(len(pth) - 1):
                acc += elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
                if acc >= INTERM:
                    placed = pth[i + 1]
                    break
            if placed is None or placed in couplers or placed == sc:
                break
            couplers.setdefault(placed, [])
            sc = serving(hi)
            dl2 = drop_len(hi, sc)
            if dl2 >= dl:
                break
            dl = dl2 + yard

    drops = []
    for hi in range(len(hhs)):
        if hh_nodes[hi] is None or hh_paths.get(hi) is None:
            continue
        pth = hh_paths[hi]
        sc = serving(hi)
        si = pth.index(sc)
        poly = [list(Pt[pth[i]]) for i in range(si, -1, -1)]
        a_h = pth[0]
        entry = yard_polyline(hhs[hi], Pt[a_h], mpp)
        poly += entry
        dl = (sum(elen.get((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])), 0)
                  for i in range(si))
              + sum(math.hypot(entry[k + 1][0] - entry[k][0],
                               entry[k + 1][1] - entry[k][1]) for k in range(len(entry) - 1)) * mpp)
        drops.append(dict(hh=hi, coupler=sc, poly=poly, length_m=round(dl, 1)))

    feeder_edges = set()
    for c in couplers:
        pth = path_to_root(c)
        if pth is None:
            continue
        for i in range(len(pth) - 1):
            feeder_edges.add((min(pth[i], pth[i + 1]), max(pth[i], pth[i + 1])))
    feeder_m = sum(elen.get(e, math.hypot(Pt[e[0]][0] - Pt[e[1]][0],
                                          Pt[e[0]][1] - Pt[e[1]][1]) * mpp)
                   for e in feeder_edges)
    drop_m = sum(dd['length_m'] for dd in drops)
    coup_list = sorted([c for c in couplers if c != root_id])
    stats = dict(households=len(hhs), served=len(drops),
                 couplers=len(coup_list),
                 feeder_km=round(feeder_m / 1000, 2), drop_km=round(drop_m / 1000, 2),
                 avg_drop_m=round(drop_m / max(1, len(drops)), 1),
                 max_drop_m=round(max((dd['length_m'] for dd in drops), default=0), 1))
    if verbose:
        print(f"  ОРШ id={anchor.get('id')} ({anchor.get('area', 0):.0f} м²);"
              f" обслужено {stats['served']}/{len(hhs)} ДХ")
        print(f"  муфт {stats['couplers']}, магистраль {stats['feeder_km']} км,"
              f" дропы {stats['drop_km']} км, ср. {stats['avg_drop_m']} м,"
              f" макс {stats['max_drop_m']} м")
    return dict(anchor=dict(x=ax, y=ay, lat=anchor['lat'], lon=anchor['lon'],
                            bld_id=anchor.get('id'), area=anchor.get('area')),
                root_node=root_id,
                couplers=[dict(node=int(c), x=float(Pt[c][0]), y=float(Pt[c][1]),
                               label=f'М{i+1}') for i, c in enumerate(coup_list)],
                feeder_edges=[[[float(Pt[e[0]][0]), float(Pt[e[0]][1])],
                               [float(Pt[e[1]][0]), float(Pt[e[1]][1])]] for e in sorted(feeder_edges)],
                drops=drops, stats=stats)


def stage_network(ctx):
    for v in ctx.villages:
        print(f"=== network: {v['name']} ===")
        key = v['key']
        geo = load_json(os.path.join(ctx.vdir(key), 'geo.json'))
        osm = load_json(os.path.join(ctx.vdir(key), 'osm.json'))
        hhs = load_json(os.path.join(ctx.vdir(key), 'households.json'))
        anchors = load_json(os.path.join(ctx.vdir(key), 'anchor_candidates.json'))
        net = build_network(key, osm, hhs, anchors[0], geo, geo['mpp'], ctx.P)
        save_json(os.path.join(ctx.vdir(key), 'network.json'), net)


# ============================================================================
# СТАДИЯ 5 (опция): crop — пользовательский кадр
# ============================================================================
def match_frame(key, frame_path, ctx):
    """SIFT+FLANN+RANSAC: кадр пользователя против мозаики. -> crop_transform dict."""
    import cv2
    old = cv2.imread(os.path.join(ctx.vdir(key), 'mosaic.jpg'))
    new = cv2.imread(frame_path)
    assert old is not None and new is not None, 'imread fail'
    Ho, Wo = old.shape[:2]
    Hn, Wn = new.shape[:2]
    DS = 4
    s = 1.0 / DS
    old_s = cv2.resize(old, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    new_s = cv2.resize(new, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(old_s, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(new_s, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1, g2 = clahe.apply(g1), clahe.apply(g2)
    sift = cv2.SIFT_create(nfeatures=60000, contrastThreshold=0.02)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=64))
    matches = flann.knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=20000,
                                         confidence=0.999)
    assert M is not None, 'RANSAC fail'
    ninl = int(inl.sum())
    err = np.sqrt(((cv2.transform(src, M) - dst) ** 2).sum(axis=2)[inl.ravel() == 1]).mean()
    M3 = np.vstack([M, [0, 0, 1]])
    S = np.diag([DS, DS, 1.0]).astype(np.float64)
    Si = np.diag([1.0 / DS, 1.0 / DS, 1.0])
    M_full = S @ M3 @ Si
    scale = math.hypot(M_full[0, 0], M_full[1, 0])
    rot = math.degrees(math.atan2(M_full[1, 0], M_full[0, 0]))
    corners = np.float32([[0, 0], [Wn, 0], [Wn, Hn], [0, Hn]]).reshape(-1, 1, 2)
    quad = cv2.transform(corners, M_full[:2, :]).reshape(-1, 2)
    Minv = np.linalg.inv(M_full)
    warped = cv2.warpAffine(old, Minv[:2, :], (Wn, Hn), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
    gw, gn = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
    step = 4
    a = gw[::step, ::step].astype(np.float32)
    b = gn[::step, ::step].astype(np.float32)
    a = a - a.mean(); b = b - b.mean()
    ncc = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))
    print(f'  match: inliers {ninl} ({100*ninl/max(1,len(good)):.1f}%), rms {err*DS:.2f} px,'
          f' scale {scale:.4f}, rot {rot:+.3f}°, NCC {ncc:.3f}')
    out = dict(new_image=frame_path, new_W=Wn, new_H=Hn, mosaic_W=Wo, mosaic_H=Ho,
               M_full=[[float(c) for c in row] for row in M_full],
               M_inv=[[float(c) for c in row] for row in Minv[:2, :]],
               scale=float(scale), rot_deg=float(rot),
               quad_old=[[float(x), float(y)] for x, y in quad],
               inliers=ninl, rms_px=float(err * DS), ncc=ncc)
    save_json(os.path.join(ctx.vdir(key), 'crop_transform.json'), out)
    del warped, old, new
    gc.collect()
    return out


def stage_crop(ctx):
    """Привязка пользовательского кадра + перестроение сети в его границах."""
    for v in ctx.villages:
        frame = v.get('crop_image')
        if not frame:
            continue
        print(f"=== crop: {v['name']} ===")
        key = v['key']
        if not os.path.isabs(frame):
            frame = os.path.join(ctx.root, frame)
        t = match_frame(key, frame, ctx)
        assert abs(t['rot_deg']) < 0.5, 'кадр повёрнут — требуется ручная обработка'
        q = t['quad_old']
        rect = (min(p[0] for p in q), min(p[1] for p in q),
                max(p[0] for p in q), max(p[1] for p in q))
        geo = load_json(os.path.join(ctx.vdir(key), 'geo.json'))
        osm = load_json(os.path.join(ctx.vdir(key), 'osm.json'))
        hhs = load_json(os.path.join(ctx.vdir(key), 'households.json'))
        hhs_in = [h for h in hhs if rect[0] <= h['cx'] <= rect[2] and rect[1] <= h['cy'] <= rect[3]]
        print(f'  ДХ в кадре: {len(hhs_in)}/{len(hhs)}')
        anchors = load_json(os.path.join(ctx.vdir(key), 'anchor_candidates.json'))
        anchor = anchors[0]
        if not (rect[0] + 15 <= anchor['x'] <= rect[2] - 15 and rect[1] + 15 <= anchor['y'] <= rect[3] - 15):
            cands = [c for c in anchors if rect[0] + 15 <= c['x'] <= rect[2] - 15
                     and rect[1] + 15 <= c['y'] <= rect[3] - 15]
            if not cands:
                cands = anchor_candidates(v, ctx)
                cands = [c for c in cands if rect[0] + 15 <= c['x'] <= rect[2] - 15
                         and rect[1] + 15 <= c['y'] <= rect[3] - 15]
            anchor = cands[0] if cands else anchor
            print(f"  перевыбор ОРШ в кадре: id={anchor.get('id')}")
        net = build_network(key, osm, hhs_in, anchor, geo, geo['mpp'], ctx.P, bounds=rect)
        save_json(os.path.join(ctx.vdir(key), 'network_v2.json'), net)


# ============================================================================
# СТАДИЯ 6: boq — схемы A (централизованная) и D (зонные ОРШ)
# ============================================================================
class Tree:
    """Дерево магистрали села (BFS-ориентация от ЦУ).

    v2 (фидерные трассы): если передан дорожный граф road (build_road_graph),
    фидеры ЦУ -> зонные ОРШ прокладываются по КРАТЧАЙШИМ путям дорожного
    графа (Дейкстра); фидерные волокна на общих с деревом участках едут
    в одном кабеле, вне дерева — отдельный кабель >= min_fibers.
    Без road — прежняя логика (фидеры по дереву сети), для совместимости.
    """

    def __init__(self, key, net_path, mpp, P, road=None):
        self.key = key
        self.mpp = mpp
        self.P = P
        net = load_json(net_path)
        self.net = net
        adj = defaultdict(set)
        self.edge_len = {}
        for e in net['feeder_edges']:
            k1, k2 = nkey(e[0]), nkey(e[1])
            if k1 == k2:
                continue
            L = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * mpp
            adj[k1].add(k2)
            adj[k2].add(k1)
            self.edge_len[(min(k1, k2), max(k1, k2))] = L
        ax, ay = net['anchor']['x'], net['anchor']['y']
        self.root = min(adj.keys(), key=lambda k: (k[0] - ax) ** 2 + (k[1] - ay) ** 2)

        self.parent = {self.root: None}
        self.children = defaultdict(list)
        order = deque([self.root])
        self.bfs = [self.root]
        while order:
            u = order.popleft()
            for w in adj[u]:
                if w not in self.parent:
                    self.parent[w] = u
                    self.children[u].append(w)
                    self.bfs.append(w)
                    order.append(w)

        self.edges = []
        for (k1, k2), L in self.edge_len.items():
            if self.parent.get(k1) == k2:
                self.edges.append((k2, k1, L))
            elif self.parent.get(k2) == k1:
                self.edges.append((k1, k2, L))

        ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
        self.coupler_nodes = {k for c in net['couplers'] if (k := nkey([c['x'], c['y']])) in adj}
        self.homes = defaultdict(int)
        for d in net['drops']:
            k = ck.get(d['coupler'])
            if k is None or k not in adj:
                k = self.root
            self.homes[k] += 1
        self.dh_total = len(net['drops'])
        self.drop_km = sum(d['length_m'] for d in net['drops']) / 1000.0
        self.n_couplers = len(net['couplers'])

        self.dist = {self.root: 0.0}
        for u in self.bfs[1:]:
            p = self.parent[u]
            self.dist[u] = self.dist[p] + self.edge_len[(min(u, p), max(u, p))]

        # --- v2: дорожный граф для кратчайших фидерных трасс ---
        self.road = road
        self.idx = None
        self._pcache = {}
        if road is not None:
            from scipy.sparse.csgraph import dijkstra as _dijkstra
            nodes = {self.root}
            for (p, ch, L) in self.edges:
                nodes.add(p); nodes.add(ch)
            nodes = list(nodes)
            d, i = road['kdt'].query(np.array(nodes))
            bad = [n for n, dd in zip(nodes, d) if dd * mpp > 0.05]
            assert not bad, f'{key}: узлы дерева вне дорожного графа: {bad[:3]}'
            self.idx = {n: int(ii) for n, ii in zip(nodes, i)}
            self.root_i = self.idx[self.root]
            self.Dg, self.predg = _dijkstra(road['C'], indices=self.root_i,
                                            return_predecessors=True)
            # ребро дерева (idx-ключ) -> (ребёнок-носитель потока, длина)
            self.child_of = {}
            for (p, ch, L) in self.edges:
                a, b = self.idx[p], self.idx[ch]
                k = (a, b) if a < b else (b, a)
                assert k not in self.child_of, f'{key}: коллизия рёбер дерева {k}'
                self.child_of[k] = (ch, L)

    def feeder_path_edges(self, z):
        """Список (ключ_ребра, L_м) кратчайшей фидерной трассы ЦУ -> z."""
        assert self.road is not None, 'feeder_path_edges: нет дорожного графа'
        if z in self._pcache:
            return self._pcache[z]
        out = []
        cur = self.idx[z]
        while cur != self.root_i and self.predg[cur] >= 0:
            p = int(self.predg[cur])
            a, b = (cur, p) if cur < p else (p, cur)
            L = math.hypot(self.road['P'][a][0] - self.road['P'][b][0],
                           self.road['P'][a][1] - self.road['P'][b][1]) * self.mpp
            out.append(((a, b), L))
            cur = p
        self._pcache[z] = out
        return out

    def feeder_path_nodes(self, z):
        """Координаты узлов (px мозаики) фидерной трассы ЦУ -> z — для отрисовки.

        v2 (road): кратчайший путь; иначе — путь в дереве (совместимость).
        """
        if self.road is None:
            chain = [z]
            u = z
            while self.parent[u] is not None:
                u = self.parent[u]
                chain.append(u)
            chain.reverse()
            return list(chain)
        path = [self.idx[z]]
        cur = self.idx[z]
        while cur != self.root_i and self.predg[cur] >= 0:
            cur = int(self.predg[cur])
            path.append(cur)
        path.reverse()
        return [(float(self.road['P'][i][0]), float(self.road['P'][i][1])) for i in path]

    def _edge_accounting(self, cuts, flows=None):
        """Генератор (L_м, F_волокон, несёт_фидер) по всем рёбрам сети.

        v2 (road): дерево + кратчайшие фидерные трассы (на общих участках
        волокна суммируются в одном кабеле, вне дерева — max(min_fibers, ff)).
        Без road: прежняя логика (фидерные волокна по дереву).
        """
        P = self.P
        if flows is None:
            flows = self.flows(cuts)
        zr, zone_dh, spl, df, ffw_tree = flows
        if self.road is None:
            for _, child, L in self.edges:
                F = max(P('min_fibers'),
                        ceilr(P('fiber_reserve') * df[child]) + ffw_tree[child])
                yield L, F, ffw_tree[child] > 0
            return
        ffw = defaultdict(int)
        for z in cuts:
            ff = ceilr(P('fiber_reserve') * spl[z])
            for k, L in self.feeder_path_edges(z):
                ffw[k] += ff
        for k, (ch, L) in self.child_of.items():
            F = max(P('min_fibers'),
                    ceilr(P('fiber_reserve') * df.get(ch, 0)) + ffw.get(k, 0))
            yield L, F, k in ffw
        for k, ff in ffw.items():
            if k not in self.child_of:
                a, b = k
                L = math.hypot(self.road['P'][a][0] - self.road['P'][b][0],
                               self.road['P'][a][1] - self.road['P'][b][1]) * self.mpp
                yield L, max(P('min_fibers'), ff), True

    def flows(self, cuts):
        P = self.P
        cutset = set(cuts)
        zr = {self.root: self.root}
        for u in self.bfs:
            if u == self.root:
                continue
            zr[u] = u if u in cutset else zr[self.parent[u]]
        zone_dh = Counter()
        cnt = Counter()
        for node, dh in self.homes.items():
            z = zr[node]
            zone_dh[z] += dh
            cnt[node] += dh
            cnt[z] -= dh
        spl = {z: ceilr(dh / P('split_ratio')) for z, dh in zone_dh.items()}
        ffnode = Counter()
        for z in cutset:
            ffnode[z] += ceilr(P('fiber_reserve') * spl[z])
        df, ffw = {}, {}
        for u in reversed(self.bfs):
            acc_d = cnt.get(u, 0)
            acc_f = ffnode.get(u, 0)
            for ch in self.children[u]:
                acc_d += df[ch]
                acc_f += ffw[ch]
            df[u] = acc_d
            ffw[u] = acc_f
        return zr, zone_dh, spl, df, ffw

    def raw_fkm(self, cuts):
        fl = self.flows(cuts)
        fkm = sum(F * L for L, F, _ in self._edge_accounting(cuts, fl))
        return fkm, fl[3]

    def partition_greedy(self, s_min_km):
        """Жадные врезы по максимальной маржинальной экономии волокно-км."""
        cuts = []
        cur_fkm, df = self.raw_fkm(cuts)
        log = []
        while True:
            best_u, best_sav = None, 0.0
            cands = [u for u in self.coupler_nodes
                     if u != self.root and u not in cuts and df.get(u, 0) >= self.P('min_zone_dh')]
            for u in cands:
                fkm_new, _ = self.raw_fkm(cuts + [u])
                sav = (cur_fkm - fkm_new) / 1000.0
                if sav > best_sav:
                    best_u, best_sav = u, sav
            if best_u is None or best_sav < s_min_km:
                break
            cuts.append(best_u)
            log.append(dict(node=str(best_u), sav_km=round(best_sav, 1)))
            cur_fkm, df = self.raw_fkm(cuts)
        return cuts, log

    def layout(self, cuts):
        P = self.P
        fl = self.flows(cuts)
        zr, zone_dh, spl, df, ffw = fl
        std = P('std_fibers')
        km_by_size = defaultdict(float)
        fiber_km = cable_km = 0.0
        top_fibers = max_parallel = 0
        feeder_route_km = 0.0
        for L, F, has_ff in self._edge_accounting(cuts, fl):
            top_fibers = max(top_fibers, F)
            cables = decompose(F, std)
            max_parallel = max(max_parallel, len(cables))
            for s in cables:
                km_by_size[s] += L / 1000.0
                cable_km += L / 1000.0
                fiber_km += L / 1000.0 * s
            if has_ff:
                feeder_route_km += L / 1000.0

        routes = []
        for node, dh in self.homes.items():
            r = max(0.0, self.dist[node] - self.dist[zr[node]])
            routes.extend([r] * dh)
        routes.sort()

        zinfo = [dict(root_dist_m=0.0, houses=zone_dh.get(self.root, 0),
                      splitters=spl.get(self.root, 0), feeder_fibers=0,
                      orsh_ports=next(p2 for p2 in P('orsh_ports_row')
                                      if p2 >= zone_dh.get(self.root, 0) * 1.1))]
        for z in cuts:
            rd = float(self.Dg[self.idx[z]]) if self.road is not None else self.dist[z]
            zinfo.append(dict(root_dist_m=round(rd, 1), houses=zone_dh[z],
                              splitters=spl[z],
                              feeder_fibers=ceilr(P('fiber_reserve') * spl[z]),
                              orsh_ports=next(p2 for p2 in P('orsh_ports_row_zone')
                                              if p2 >= zone_dh[z] * 1.1)))
        mufty = self.n_couplers - sum(1 for z in cuts if z in self.coupler_nodes)
        dh = self.dh_total
        spl_total = sum(spl.values())

        def pct(sv, q):
            if not sv:
                return 0.0
            i = min(len(sv) - 1, max(0, int(math.ceil(q / 100.0 * len(sv))) - 1))
            return sv[i]

        return dict(cuts=[str(c) for c in cuts], zones=zinfo, n_zones=len(cuts),
                    orsh=1 + len(cuts), fiber_km=round(fiber_km, 1),
                    cable_km_raw=round(cable_km, 3),
                    km_by_size={str(s): round(km_by_size.get(s, 0.0), 3) for s in std
                                if km_by_size.get(s, 0.0) > 0},
                    top_fibers=top_fibers, max_parallel=max_parallel,
                    feeder_route_km=round(feeder_route_km, 2),
                    splitters=spl_total, olt_ports=spl_total,
                    orsh_ports=sum(z['orsh_ports'] for z in zinfo),
                    mufty=mufty, splices=ceilr((2 * dh + 2 * spl_total) * P('consum_stock')),
                    pigtails=dh + 2 * spl_total,
                    suspend_kits=math.ceil(cable_km * P('suspend_per_km')),
                    routes=dict(avg_m=round(sum(routes) / max(1, len(routes)), 1),
                                med_m=round(pct(routes, 50), 1),
                                p90_m=round(pct(routes, 90), 1),
                                max_m=round(routes[-1], 1) if routes else 0))


def boq_centralized(key, net_path, mpp, P):
    """Схема A: сплиттеры 1:64 в ОРШ, выделенное волокно каждому ДХ."""
    net = load_json(net_path)
    std = P('std_fibers')
    adj = defaultdict(set)
    edge_len = {}
    for e in net['feeder_edges']:
        k1, k2 = nkey(e[0]), nkey(e[1])
        if k1 == k2:
            continue
        L = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * mpp
        adj[k1].add(k2)
        adj[k2].add(k1)
        edge_len[(min(k1, k2), max(k1, k2))] = L
    ax, ay = net['anchor']['x'], net['anchor']['y']
    root = min(adj.keys(), key=lambda k: (k[0] - ax) ** 2 + (k[1] - ay) ** 2)

    ck = {c['node']: nkey([c['x'], c['y']]) for c in net['couplers']}
    homes_direct = Counter()
    unmapped = 0
    for d in net['drops']:
        k = ck.get(d['coupler'])
        if k is None or k not in adj:
            k = root
            unmapped += 1
        homes_direct[k] += 1

    parent = {root: None}
    bfs = [root]
    order = deque([root])
    while order:
        u = order.popleft()
        for w in adj[u]:
            if w not in parent:
                parent[w] = u
                bfs.append(w)
                order.append(w)

    sub = dict(homes_direct)
    for u in reversed(bfs):
        p2 = parent[u]
        if p2 is not None:
            sub[p2] = sub.get(p2, 0) + sub.get(u, 0)

    km_by_size = defaultdict(float)
    fiber_km = total_cable_km = 0.0
    top_fibers = max_parallel = 0
    feeder_m = 0.0
    for (k1, k2), L in edge_len.items():
        feeder_m += L
        if parent.get(k1) == k2:
            child = k1
        elif parent.get(k2) == k1:
            child = k2
        else:
            continue
        F = max(P('min_fibers'), ceilr(P('fiber_reserve') * sub.get(child, 0)))
        top_fibers = max(top_fibers, F)
        cables = decompose(F, std)
        max_parallel = max(max_parallel, len(cables))
        for s in cables:
            km_by_size[s] += L / 1000.0
            total_cable_km += L / 1000.0
            fiber_km += L / 1000.0 * s

    drops = net['drops']
    dh = len(drops)
    drop_km = sum(d['length_m'] for d in drops) / 1000.0
    cable_km = {str(s): round(roundup01(km_by_size.get(s, 0.0) * P('cable_stock')), 1)
                for s in std if km_by_size.get(s, 0.0) > 0}
    m = dict(
        orsh=1,
        splitters=ceilr(dh / P('split_ratio')), olt_ports=ceilr(dh / P('split_ratio')),
        pigtails=dh, mufty=len(net['couplers']),
        drop_cable_km=roundup01(drop_km * P('drop_stock')),
        abonent_boxes=dh, fast_conn=ceilr(dh * P('consum_stock')),
        splices=ceilr(2 * dh * P('consum_stock')), kdzs=ceilr(2 * dh * P('consum_stock')),
        suspend_kits=math.ceil(total_cable_km * P('suspend_per_km')),
        drop_anchors=P('drop_anchors_per_dh') * dh,
        drop_fix=P('drop_fix_per_dh') * dh,
        orsh_ports=next(p2 for p2 in P('orsh_ports_row') if p2 >= dh * 1.1),
    )
    m.update({f'cable_{s}': cable_km.get(str(s), 0.0) for s in std})
    return dict(
        dhx_served=dh, couplers=len(net['couplers']), mufty=len(net['couplers']),
        feeder_km=round(feeder_m / 1000, 2), drop_km=round(drop_km, 2),
        avg_drop_m=round(sum(d['length_m'] for d in drops) / max(1, dh), 1),
        max_drop_m=round(max((d['length_m'] for d in drops), default=0), 1),
        top_fibers=top_fibers, max_parallel=max_parallel,
        total_cable_km=round(total_cable_km, 3), fiber_km=round(fiber_km, 1),
        cable_km=cable_km,
        cable_km_raw=round(total_cable_km * P('cable_stock'), 2),
        drop_cable_km=m['drop_cable_km'],
        orsh_ports=m['orsh_ports'], splitters64=m['splitters'],
        materials=m, checks=dict(unmapped_drop_couplers=unmapped),
    )


def net_path_for(v, ctx):
    """Путь к финальной сети: network_v2.json (кадр) либо network.json."""
    key = v['key']
    for cand in (v.get('net'), 'network_v2.json', 'network.json'):
        if cand:
            p = os.path.join(ctx.vdir(key), cand)
            if os.path.exists(p):
                return p
    raise FileNotFoundError(f'{key}: нет network.json — запустите стадию network')


def geo_for(key, ctx):
    """Геопривязка села: <key>/geo.json, иначе legacy work/mosaic_geo.json."""
    p = os.path.join(ctx.vdir(key), 'geo.json')
    if os.path.exists(p):
        return load_json(p)
    legacy = os.path.join(ctx.work, 'mosaic_geo.json')
    if os.path.exists(legacy):
        g = load_json(legacy)
        if key in g:
            return g[key]
    raise FileNotFoundError(f'{key}: нет geo.json')


# ============================================================================
# Оптический бюджет (v2.4) — энергетический расчёт худшей линии каждой зоны
# ============================================================================
def optical_budget(t, cuts, zones_layout, max_drop_m, P):
    """Энергетический бюджет (затухание) худшей абонентской линии каждой зоны.

    Линия (восходящий поток 1310 нм — максимум потерь):
      OLT(ЦУ) -> ODF -> фидер ЦУ->зонный ОРШ -> кросс ОРШ -> сплиттер PLC 1:64
      -> распределение ОРШ->муфта -> муфта -> дроп муфта->ДХ -> ONT.

    Худший абонент зоны: фидер(ОРШ) + max путь дерева ОРШ->муфта зоны
    + макс. дроп села (верхняя граница — консервативно).
    Сварки: 2 (концы фидера) + транзитные (муфты ветвления на пути) +
    2 (оба конца дропа). Разъёмы: 3 x SC/APC.

    Гейты: A + margin_min <= budget (ok) — полная годность;
           A <= budget (ok-hard) — годно, но эксплуатационный запас < нормы:
           для этих зон указывается оптика Class C+ (budget_db_c) или
           сплиттер 1:32 (требование ALGORITHM_FTTH.md v1.1, разд. VII);
           A > budget (EXCEEDED) — редизайн зоны (сдвиг ОРШ/1:32).
    """
    zr, zone_dh, spl, df, ffw = t.flows(cuts)
    zworst = {}
    for node in t.homes:
        z = zr[node]
        r = t.dist[node] - t.dist[z]
        if z not in zworst or r > zworst[z][0]:
            zworst[z] = (r, node)
    B, MC = P('ob_budget_db'), P('ob_margin_min_db')
    zones = []
    for zi, z in enumerate([t.root] + list(cuts)):
        dist_m, wnode = zworst.get(z, (0.0, z))
        n_tr = 0
        u = wnode
        while u != z:
            p = t.parent[u]
            if p != z and p in t.coupler_nodes:
                n_tr += 1
            u = p
        feeder_m = zones_layout[zi]['root_dist_m']
        L_km = (feeder_m + dist_m + max_drop_m) / 1000.0
        A = (P('ob_alpha_db_km') * L_km + P('ob_splitter_il_db')
             + 3 * P('ob_connector_db')
             + (2 + n_tr + 2) * P('ob_splice_db') + P('ob_penalty_db'))
        status = ('ok' if A + MC <= B else
                  'ok-hard' if A <= B else 'EXCEEDED')
        rec = ('' if status == 'ok' else
               'оптика Class C+ или сплиттер 1:32 для дальних PON-портов зоны'
               if status == 'ok-hard' else 'РЕДИЗАЙН: сдвинуть ОРШ к центру зоны / 1:32')
        zones.append(dict(kind=zones_layout[zi].get('zone', ''),
                          houses=zones_layout[zi]['houses'],
                          feeder_m=round(feeder_m, 1), distrib_m=round(dist_m, 1),
                          drop_max_m=max_drop_m, L_km=round(L_km, 3),
                          transit_splices=n_tr, attenuation_db=round(A, 2),
                          margin_db=round(B - A, 2), status=status, recommendation=rec))
    return dict(model=dict(alpha_db_km=P('ob_alpha_db_km'),
                           splitter_il_db=P('ob_splitter_il_db'),
                           splice_db=P('ob_splice_db'),
                           connector_db=P('ob_connector_db'),
                           penalty_db=P('ob_penalty_db'),
                           budget_class_b=B, budget_class_c=P('ob_budget_db_c'),
                           margin_min_db=MC),
                worst_attenuation_db=max(z['attenuation_db'] for z in zones),
                worst_margin_db=min(z['margin_db'] for z in zones),
                all_ok=all(z['status'] != 'EXCEEDED' for z in zones),
                all_ok_with_margin=all(z['status'] == 'ok' for z in zones),
                zones=zones)


def stage_boq(ctx):
    """Схемы A и D по каждому селу + сводный work/boq_total.json."""
    P = ctx.P
    villages_out = []
    for v in ctx.villages:
        print(f"=== boq: {v['name']} ===")
        key = v['key']
        netp = net_path_for(v, ctx)
        geo = geo_for(key, ctx)
        mpp = geo['mpp']
        osm_p = os.path.join(ctx.vdir(key), 'osm.json')
        road = build_road_graph(load_json(osm_p), geo, mpp, P) if os.path.exists(osm_p) else None
        if road is None:
            print('  ! нет osm.json — фидеры по дереву сети (legacy-режим)')
        a = boq_centralized(key, netp, mpp, P)
        t = Tree(key, netp, mpp, P, road=road)
        r0 = t.layout([])
        if abs(r0['fiber_km'] - a['fiber_km']) > 0.15 or r0['splitters'] != a['splitters64']:
            print(f'  ! контроль A/D: fiber {r0["fiber_km"]} vs {a["fiber_km"]},'
                  f' сплиттеры {r0["splitters"]} vs {a["splitters64"]}')
        cuts, log = t.partition_greedy(P('s_min_km'))
        r = t.layout(cuts)

        net = t.net
        ax, ay = net['anchor']['x'], net['anchor']['y']
        alat, alon = net['anchor']['lat'], net['anchor']['lon']
        mlat = -mpp / 110574.0
        mlon = mpp / (M_PER_DEG_LAT * math.cos(math.radians(alat)))
        cpos = {nkey([c['x'], c['y']]): (c['x'], c['y']) for c in net['couplers']}
        zones_geo = []
        zlist = [(t.root, None)] + [(c, cpos.get(c)) for c in cuts]
        for z, zxy in zlist:
            zdata = r['zones'][len(zones_geo)]
            if zxy is not None:
                zx, zy = zxy
                zgeo = dict(px=[round(zx, 1), round(zy, 1)],
                            lat=round(alat + (zy - ay) * mlat, 6),
                            lon=round(alon + (zx - ax) * mlon, 6))
            else:
                zgeo = dict(px=None, lat=None, lon=None)
            zones_geo.append(dict(**zdata,
                                  zone='ЦУ (корневая)' if z == t.root else 'зонный ОРШ',
                                  **zgeo))

        cable_km = {str(s): roundup01(r['km_by_size'].get(str(s), 0.0) * P('cable_stock'))
                    for s in P('std_fibers') if r['km_by_size'].get(str(s), 0.0) > 0}
        dh = t.dh_total
        drops_sorted = sorted(d['length_m'] for d in net['drops'])
        m = dict(
            orsh=r['orsh'], orsh_cu=1, orsh_zone=r['n_zones'],
            splitters=r['splitters'], olt_ports=r['splitters'],
            pigtails=r['pigtails'], mufty=r['mufty'],
            drop_cable_km=roundup01(t.drop_km * P('drop_stock')),
            abonent_boxes=dh, fast_conn=ceilr(dh * P('consum_stock')),
            splices=r['splices'], kdzs=r['splices'],
            suspend_kits=r['suspend_kits'],
            drop_anchors=P('drop_anchors_per_dh') * dh,
            drop_fix=P('drop_fix_per_dh') * dh,
            orsh_ports=r['orsh_ports'],
        )
        m.update({f'cable_{s}': cable_km.get(str(s), 0.0) for s in P('std_fibers')})
        vv = dict(num=v.get('num', ''), key=key, name=v['name'],
                  raion=v.get('raion', ''), so=v.get('so', '—'),
                  dhx_excel=v.get('hh'), net=os.path.basename(netp),
                  dhx_served=dh, couplers=t.n_couplers, mufty=r['mufty'],
                  feeder_km=round(sum(L for _, _, L in t.edges) / 1000.0, 2),
                  drop_km=round(t.drop_km, 2),
                  avg_drop_m=round(sum(drops_sorted) / max(1, dh), 1),
                  max_drop_m=round(drops_sorted[-1], 1) if drops_sorted else 0,
                  n_zones=r['n_zones'], orsh=r['orsh'], zones=zones_geo,
                  fiber_km=r['fiber_km'], total_cable_km=r['cable_km_raw'],
                  cable_km=cable_km,
                  cable_km_raw=round(r['cable_km_raw'] * P('cable_stock'), 2),
                  drop_cable_km=m['drop_cable_km'],
                  orsh_ports=r['orsh_ports'], splitters64=r['splitters'],
                  top_fibers=r['top_fibers'], max_parallel=r['max_parallel'],
                  feeder_route_km=r['feeder_route_km'], routes=r['routes'],
                  cut_log=log, materials=m,
                  scheme_a=dict(fiber_km=a['fiber_km'],
                                cable_km_raw=a['cable_km_raw'],
                                drop_cable_km=a['drop_cable_km'],
                                mufty=a['mufty'], splitters64=a['splitters64'],
                                splices=a['materials']['splices'],
                                orsh_ports=a['orsh_ports'],
                                total_length_km=round(a['cable_km_raw'] + a['drop_cable_km'], 1)))
        vv['total_length_km'] = round(vv['cable_km_raw'] + vv['drop_cable_km'], 1)
        # v2.4: энергетический бюджет худших линий зон (ALGORITHM_FTTH.md v1.1 §VII)
        vv['optical_budget'] = optical_budget(t, cuts, r['zones'], vv['max_drop_m'], P)
        assert dh == a['dhx_served'], f'{key}: ДХ A/D не совпали'
        assert abs(vv['drop_km'] - a['drop_km']) < 0.02, f'{key}: дропы A/D'
        assert abs(vv['feeder_km'] - a['feeder_km']) < 0.02, f'{key}: трасса A/D'
        assert sum(z['houses'] for z in zones_geo) == dh, f'{key}: сумма зон != ДХ'
        print(f"  A: вол-км {a['fiber_km']}, кабель {a['cable_km_raw']} км;"
              f"  D: зон {r['n_zones']} + ЦУ, вол-км {r['fiber_km']},"
              f" кабель {vv['cable_km_raw']} км, сварки {r['splices']}")
        ob = vv['optical_budget']
        n_hard = sum(1 for z in ob['zones'] if z['status'] == 'ok-hard')
        n_exc = sum(1 for z in ob['zones'] if z['status'] == 'EXCEEDED')
        print(f"  Бюджет B+: худшая линия {ob['worst_attenuation_db']:.2f} дБ"
              f" (маржа {ob['worst_margin_db']:.2f} дБ);"
              f" зон ok={len(ob['zones']) - n_hard - n_exc},"
              f" с усечённым запасом={n_hard}, превышений={n_exc}"
              + (' — КЛАСС C+/1:32 для дальних зон' if n_hard and not n_exc else ''
                 if not n_exc else ' — РЕДИЗАЙН ЗОН'))
        save_json(os.path.join(ctx.vdir(key), 'boq.json'), vv)
        villages_out.append(vv)

    tot = dict(
        dhx_served=sum(x['dhx_served'] for x in villages_out),
        dhx_excel=sum(x['dhx_excel'] or 0 for x in villages_out),
        mufty=sum(x['mufty'] for x in villages_out),
        couplers=sum(x['couplers'] for x in villages_out),
        n_zones=sum(x['n_zones'] for x in villages_out),
        orsh=sum(x['orsh'] for x in villages_out),
        feeder_km=round(sum(x['feeder_km'] for x in villages_out), 2),
        fiber_km=round(sum(x['fiber_km'] for x in villages_out), 1),
        cable_km_raw=round(sum(x['cable_km_raw'] for x in villages_out), 2),
        drop_km=round(sum(x['drop_km'] for x in villages_out), 2),
        drop_cable_km=round(sum(x['drop_cable_km'] for x in villages_out), 1),
        splitters64=sum(x['splitters64'] for x in villages_out),
        orsh_ports=sum(x['orsh_ports'] for x in villages_out),
        splices=sum(x['materials']['splices'] for x in villages_out),
        total_length_km=round(sum(x['total_length_km'] for x in villages_out), 1),
        fiber_km_a=round(sum(x['scheme_a']['fiber_km'] for x in villages_out), 1),
        cable_km_raw_a=round(sum(x['scheme_a']['cable_km_raw'] for x in villages_out), 2),
        total_length_km_a=round(sum(x['scheme_a']['total_length_km'] for x in villages_out), 1),
    )
    mat_tot = defaultdict(float)
    for x in villages_out:
        for k, val in x['materials'].items():
            mat_tot[k] = round(mat_tot.get(k, 0) + val, 1)
    out = dict(model=dict(
        scheme='D — децентрализованная: зонные ОРШ 1:64, единый узел OLT',
        s_min_km=P('s_min_km'), min_zone=P('min_zone_dh'),
        fiber_reserve=P('fiber_reserve'), min_fibers=P('min_fibers'),
        std_fibers=P('std_fibers'), cable_stock=P('cable_stock'),
        drop_stock=P('drop_stock'), suspend_per_km=P('suspend_per_km'),
        drop_anchors_per_dh=P('drop_anchors_per_dh'), drop_fix_per_dh=P('drop_fix_per_dh'),
        consum_stock=P('consum_stock'), split_ratio=P('split_ratio'),
        orsh_ports_row=P('orsh_ports_row'), orsh_ports_row_zone=P('orsh_ports_row_zone'),
        note='Фидер ЦУ -> зонный ОРШ: кратчайший путь дорожного графа (Дейкстра); '
             'на общих участках с деревом — в одном кабеле, вне дерева — отдельный '
             'кабель >= min_fibers. Межселённый транспорт до ЦУ — за рамками расчёта'),
        villages=villages_out, totals=tot, materials_total=dict(mat_tot))
    save_json(os.path.join(ctx.work, 'boq_total.json'), out)
    print(f"\nИТОГО по {len(villages_out)} СНП: {tot['dhx_served']} ДХ,"
          f" зон {tot['n_zones']} + {len(villages_out)} ЦУ,"
          f" волокно-км {tot['fiber_km']} (A: {tot['fiber_km_a']}),"
          f" ВСЕГО кабель {tot['total_length_km']} км (A: {tot['total_length_km_a']})")
    return out


# ============================================================================
# СТАДИЯ qa — контрольные проверки
# ============================================================================
def stage_qa(ctx):
    print('=== QA артефактов ===')
    ok = True
    for v in ctx.villages:
        key = v['key']
        vd = ctx.vdir(key)
        checks = []
        if not os.path.exists(os.path.join(vd, 'osm.json')):
            checks.append(('osm.json', False, 'нет файла'))
        geo = geo_for(key, ctx)
        mos_ok = os.path.exists(os.path.join(vd, 'mosaic.jpg'))
        checks.append(('mosaic.jpg', mos_ok, 'мозаика есть' if mos_ok else 'НЕТ мозаики'))
        hh_path = os.path.join(vd, 'households.json')
        if os.path.exists(hh_path):
            hhs = load_json(hh_path)
            dev = 100 * (len(hhs) - (v.get('hh') or len(hhs))) / max(1, v.get('hh') or 1)
            checks.append(('households', abs(dev) <= 60,
                           f'{len(hhs)} ДХ, отклонение от заказа {dev:+.1f}%'
                           + ('' if abs(dev) <= 25 else ' — СВЕРИТЬ вручную/VLM')))
        netp = net_path_for(v, ctx)
        net = load_json(netp)
        st = net['stats']
        # legacy-совместимость: network_v2 проекта ВКО писал households_in_crop
        hh_total = st.get('households', st.get('households_in_crop', st['served']))
        served_ratio = st['served'] / max(1, hh_total)
        checks.append(('network', served_ratio > 0.9,
                       f"обслужено {st['served']}/{hh_total}"
                       f" ({100*served_ratio:.1f}%), муфт {st['couplers']},"
                       f" дропы {st['drop_km']} км"))
        boq_path = os.path.join(vd, 'boq.json')
        if os.path.exists(boq_path):
            b = load_json(boq_path)
            zsum = sum(z['houses'] for z in b['zones'])
            checks.append(('boq', zsum == b['dhx_served'],
                           f"зоны={zsum} == ДХ={b['dhx_served']};"
                           f" вол-км D {b['fiber_km']} / A {b['scheme_a']['fiber_km']}"))
            ob = b.get('optical_budget')
            if ob:
                n_hard = sum(1 for z in ob['zones'] if z['status'] == 'ok-hard')
                n_exc = sum(1 for z in ob['zones'] if z['status'] == 'EXCEEDED')
                checks.append(('budget', n_exc == 0,
                               f"худшая линия {ob['worst_attenuation_db']:.2f} дБ /"
                               f" Class B+ {ob['model']['budget_class_b']:.0f} дБ"
                               + ('' if not n_hard else
                                  f"; {n_hard} зон(ы) запас < {ob['model']['margin_min_db']:.0f} дБ"
                                  " — C+/1:32")
                               + ('' if n_exc == 0 else f"; ПРЕВЫШЕНИЕ в {n_exc} зон(ах)!")))
        map_path = os.path.join(ctx.dl, f"{v.get('num','')}_{v['name']}_зоны_ОРШ.jpg")
        if os.path.exists(map_path):
            sz = os.path.getsize(map_path) / 1e6
            checks.append(('map', sz > 0.5, f'{sz:.1f} МБ'))
        for name, passed, msg in checks:
            print(f"  [{'OK ' if passed else '!! '}] {key:<18} {name:<12} {msg}")
            ok &= passed
    print('QA:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ — см. выше')
    return ok


# ============================================================================
# CLI
# ============================================================================
def main():
    ap = argparse.ArgumentParser(description='FTTH-конвейер: село -> сеть -> карта + BoQ')
    ap.add_argument('--config', required=True, help='config.json со списком сёл')
    ap.add_argument('--stage', required=True,
                    choices=['fetch', 'households', 'anchor', 'network', 'crop', 'boq',
                             'map', 'xlsx', 'all', 'qa'],
                    help='стадия конвейера')
    ap.add_argument('--village', default=None, help='key одного села (иначе все)')
    ap.add_argument('--vlm', action='store_true', help='VLM-проверки превью (если доступен z-ai)')
    args = ap.parse_args()

    ctx = Ctx(args.config, only=args.village)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    stages = ([args.stage] if args.stage != 'all'
              else ['fetch', 'households', 'anchor', 'network', 'boq', 'map', 'xlsx'])
    for st in stages:
        if st == 'fetch':
            stage_fetch(ctx)
        elif st == 'households':
            stage_households(ctx)
        elif st == 'anchor':
            stage_anchor(ctx)
        elif st == 'network':
            stage_network(ctx)
        elif st == 'crop':
            stage_crop(ctx)
        elif st == 'boq':
            stage_boq(ctx)
        elif st in ('map', 'xlsx'):
            import ftth_outputs
            if st == 'map':
                ftth_outputs.stage_map(ctx, vlm=args.vlm)
            else:
                ftth_outputs.stage_xlsx(ctx)
        elif st == 'qa':
            stage_qa(ctx)


if __name__ == '__main__':
    main()
