#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Шаг 52e. KMZ фидера ЦУ -> ОРШ-2 (с. Пригородное) — топология v4
(Task 52: кратчайшие трассы прокладки кабелей вдоль дорог).

Пересборка KMZ 50_kmz_v3 под новую книгу boq_decentral_data_v4
(network_hh3: детур-гард ствола + дропы кратчайшими уличными путями):
  - состав зон Пригородного изменился (93-ДХ зона южной части села
    сохранила размер, медиана сместилась, фидер 498 -> 262 м);
  - зелёная линия — НОВАЯ трасса v4: ЦУ -> медиана ОРШ-2 (кратчайший
    путь в границе НП по дереву hh3);
  - серый пунктир — прежняя трасса v3 (из KMZ v3, для сравнения);
  - белая — маршрут пользователя (эталон, шаг 42-43) — сохранён.

Запуск: FTTH_NET_OVERRIDE=network_hh3.json python3 52e_kmz_v4.py
Выход: download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v4.kmz
"""
import json
import math
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

import importlib.util
from pyproj import Geod

BASE = '/home/z/my-project'
Z = 18
KEY = 'prigorodnoe'
OUT_KMZ = f'{BASE}/download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v4.kmz'
OLD_KMZ = f'{BASE}/download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v3.kmz'

sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty  # noqa: E402


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


assert os.environ.get('FTTH_NET_OVERRIDE') == 'network_hh3.json', \
    'запускать с FTTH_NET_OVERRIDE=network_hh3.json'
de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de46 = load_mod('de46', f'{BASE}/scripts/46_topology_v3.py')

GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
GEOD = Geod(ellps='WGS84')
Q = json.load(open(f'{BASE}/work/route_diag_prigorodnoe.json'))

KML_GREEN = 'ff449e2f'
KML_ORANGE = 'ff009be0'
KML_WHITE = 'ffffffff'
KML_GRAY = 'ff969696'
KML_RED = 'ff2b1ffd'


def px_to_geo(x, y):
    tx0f, ty0f = lon2tx(GEO['west'], Z), lat2ty(GEO['north'], Z)
    gx, gy = tx0f * 256.0 + x, ty0f * 256.0 + y
    lon = gx / 256.0 / (1 << Z) * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * gy / 256.0 / (1 << Z)))))
    return lat, lon


def geod_len(pts):
    return sum(GEOD.inv(lo1, la1, lo2, la2)[2]
               for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]))


def fmt(x, nd=1):
    return f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')


# ============================================================ модель v4 ===
v = next(v for v in de28.VILLAGES if v['key'] == KEY)
DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
bv = next(x for x in DBOOK['villages'] if x['key'] == KEY)
# ОРШ-2 = зона 2 книги (93 ДХ, южная часть села — преемник валидированной
# пользователем зоны «врез у хлебозавода»)
bz = bv['zones'][2]
assert bz['houses'] >= 80, bz['houses']
cuts = [tuple(l['node']) for l in bv['cut_log']]

V3 = de46.VillageV3(v)
med_model = V3.medians_of(cuts)
med = tuple(float(x) for x in bz['orsh_px'])
mm = tuple(round(x, 1) for x in med_model[cuts[1]])
if mm != tuple(round(x, 1) for x in med):
    print(f'ВНИМ: медиана модели {mm} != книги {med} — беру книгу')

# узел V3 для медианы (точный или ближайший)
key = tuple(round(x, 1) for x in med)
if key in V3.idx:
    m_i = V3.idx[key]
else:
    m_i = min(V3.idx.items(),
              key=lambda kv: (kv[0][0] - med[0]) ** 2 + (kv[0][1] - med[1]) ** 2)[1]

# маршрут v4: ЦУ -> медиана (кратчайший путь в границе НП)
path_i = [m_i]
cur = m_i
while cur != V3.root_i and V3.pred[cur] >= 0:
    cur = int(V3.pred[cur])
    path_i.append(cur)
path_i.reverse()
L_v4 = sum(V3.L_of(a, b) for a, b in zip(path_i, path_i[1:]))
assert abs(bz['root_dist_m'] - L_v4) < 0.1, (bz['root_dist_m'], L_v4)

pts = [px_to_geo(V3.P[i][0], V3.P[i][1]) for i in path_i]
L_geod = geod_len(pts)

# фидерные волокна: общие/отдельные участки (как в 50_kmz_v3)
A = V3.account_v3(cuts, V3.medians_of(cuts))
sel = cuts[1]
edges = []
for a, b in zip(path_i, path_i[1:]):
    k = V3.ekey(a, b)
    edges.append(dict(a=a, b=b, shared=k in V3.child_of,
                      L=V3.L_of(a, b), ffw=A['ffw'].get(k, 0)))
L_shared = sum(e['L'] for e in edges if e['shared'])
L_corr = sum(e['L'] for e in edges if not e['shared'])

# прежняя зелёная трасса v3 из KMZ v3 (для сравнения, серым)
old_green = None
with zipfile.ZipFile(OLD_KMZ) as zf:
    root_old = ET.fromstring(zf.read('doc.kml'))
ns = '{http://www.opengis.net/kml/2.2}'
for p in root_old.findall(f'{ns}Document/{ns}Placemark'):
    if 'v3' in (p.find(f'{ns}name').text or ''):
        old_green = p.find(f'{ns}LineString/{ns}coordinates').text.strip()
assert old_green, 'в KMZ v3 не найдена зелёная трасса'
L_v3_old = 497.6
user_geo = [tuple(p) for p in Q['user_geo']]
L_user = Q['L_user']

med_geo = px_to_geo(med[0], med[1])
cut_geo = px_to_geo(bz['cut_px'][0], bz['cut_px'][1])
cu_geo = px_to_geo(V3.P[V3.root_i][0], V3.P[V3.root_i][1])

print(f'v4: медиана зоны {tuple(round(x, 1) for x in med)}; '
      f'трасса {len(path_i)} узлов, {L_v4:.1f} м (общие {L_shared:.0f} / '
      f'отдельный 8F {L_corr:.0f} м); геодезически {L_geod:.1f} м')
print(f'сравнение: прежняя v3 {L_v3_old:.1f} м; пользователь {L_user:.1f} м')

coords = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in pts)
coords_user = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in user_geo)

corr_segs = []
seg = None
for e in edges:
    if not e['shared']:
        if seg is None:
            seg = [e['a'], e['b']]
        elif seg[-1] == e['a']:
            seg.append(e['b'])
        else:
            corr_segs.append(seg)
            seg = [e['a'], e['b']]
    else:
        if seg is not None:
            corr_segs.append(seg)
            seg = None
if seg is not None:
    corr_segs.append(seg)
corr_coords = [' '.join(f'{px_to_geo(V3.P[i][0], V3.P[i][1])[1]:.7f},'
                        f'{px_to_geo(V3.P[i][0], V3.P[i][1])[0]:.7f},0' for i in sgm)
               for sgm in corr_segs]

desc = f"""\
Магистральный участок кабеля: фидер ЦУ → зонный ОРШ-2 (схема D, топология v4 — кратчайшие трассы)

Село Пригородное (г.а. Риддер, ВКО) · зона: {bz['houses']} ДХ · сплиттеры {bz['splitters']}×1:64 · фидер {bz['feeder_fibers']} волокна

ЧТО ИЗМЕНИЛОСЬ В v4 (Task 52 «кратчайшие трассы вдоль дорог»):
  1) Дерево распределения перестроено: маршруты с обходами (>30% длиннее
     кратчайшего пути по улицам) заменены кратчайшими; дропы прокладываются
     кратчайшими уличными путями от ближайшей по дорогам муфты.
  2) Состав зон пересчитан по новому дереву (правило S_MIN = 15 волокно-км
     не изменилось): прежняя зона «врез у хлебозавода» (93 ДХ) перешла в
     новую зону ОРШ-2 того же размера, медиана сместилась к домам.

ТРАССА v4 (зелёная): {fmt(L_v4)} м — кратчайший путь ЦУ → медиана ОРШ-2 в границе НП
   из них {fmt(L_shared)} м — участки, общие с распределительной сетью (в одном кабеле),
   {fmt(L_corr)} м — отдельный кабель 8 волокон (оранжевые сегменты)
   длина геодезическая WGS84: {fmt(L_geod)} м · по книге v4 (root_dist_m): {fmt(bz['root_dist_m'])} м

СРАВНЕНИЕ (серый пунктир): прежняя трасса v3 — {fmt(L_v3_old)} м к старой медиане.
   v4 короче на {fmt(L_v3_old - L_v4)} м: ствол больше не обходит кварталы.
   Маршрут пользователя (белая) — {fmt(L_user)} м, эталон шага 42-43.

Проверка в Google Earth Pro: ПКМ по линии → «Сведения об объекте» → вкладка «Измерение»."""


def pin(style_id, name, lat, lon, pdesc=''):
    return f"""    <Placemark>
      <name>{name}</name>
      <description>{pdesc}</description>
      <styleUrl>#{style_id}</styleUrl>
      <Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>
    </Placemark>"""


corr_placemarks = ''.join(
    f"""    <Placemark>
      <name>Отдельный кабель 8F (вне дерева)</name>
      <styleUrl>#corr</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{cc}</coordinates></LineString>
    </Placemark>\n""" for cc in corr_coords)

kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Фидер ЦУ → ОРШ-2, с. Пригородное (схема D, v4 — кратчайшие трассы)</name>
    <open>1</open>
    <Style id="feeder"><LineStyle><color>{KML_GREEN}</color><width>6</width></LineStyle></Style>
    <Style id="corr"><LineStyle><color>{KML_ORANGE}</color><width>6</width></LineStyle></Style>
    <Style id="user"><LineStyle><color>{KML_WHITE}</color><width>2</width></LineStyle></Style>
    <Style id="old"><LineStyle><color>{KML_GRAY}</color><width>2</width></LineStyle></Style>
    <Style id="pinCu"><IconStyle><color>{KML_RED}</color><scale>1.5</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>
    </IconStyle></Style>
    <Style id="pinOrsh"><IconStyle><color>{KML_GREEN}</color><scale>1.4</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_square.png</href></Icon>
    </IconStyle></Style>
    <Style id="pinCut"><IconStyle><color>{KML_ORANGE}</color><scale>1.1</scale>
      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>
    </IconStyle></Style>
    <Placemark>
      <name>Фидер ЦУ → ОРШ-2 (v4): {fmt(L_v4)} м к медиане зоны</name>
      <description><![CDATA[{desc}]]></description>
      <styleUrl>#feeder</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords}</coordinates></LineString>
    </Placemark>
{corr_placemarks}    <Placemark>
      <name>Прежняя трасса v3: {fmt(L_v3_old)} м (для сравнения)</name>
      <styleUrl>#old</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{old_green}</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Маршрут пользователя: {fmt(L_user)} м</name>
      <styleUrl>#user</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_user}</coordinates></LineString>
    </Placemark>
{pin('pinCu', 'ЦУ — точка входа фидера (здание-якорь)', cu_geo[0], cu_geo[1], 'Единый узел OLT, корневая зона')}
{pin('pinCut', f'Узел вреза зоны (граница сектора)', cut_geo[0], cut_geo[1], f'Точка отделения зоны от дерева сети; {bz["houses"]} ДХ ниже по дереву')}
{pin('pinOrsh', f'ОРШ-2 — шкаф в центре сектора ({bz["houses"]} ДХ)', med_geo[0], med_geo[1], f'Медиана дерева зоны; фидер {bz["feeder_fibers"]} волокна')}
  </Document>
</kml>
"""

with zipfile.ZipFile(OUT_KMZ, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('doc.kml', kml)

# ============================================================== контроль ==
with zipfile.ZipFile(OUT_KMZ) as zf:
    assert zf.testzip() is None
    names = zf.namelist()
    assert names == ['doc.kml'], names
    root = ET.fromstring(zf.read('doc.kml'))
pls = root.findall(f'{ns}Document/{ns}Placemark')
lines = [p for p in pls if p.find(f'{ns}LineString') is not None]
pins_n = [p for p in pls if p.find(f'{ns}Point') is not None]
main = next(p for p in lines if 'v4' in p.find(f'{ns}name').text)
gpts = [tuple(map(float, c.split(',')[:2]))
        for c in main.find(f'{ns}LineString/{ns}coordinates').text.split()]
L_file = geod_len([(la, lo) for lo, la in gpts])
assert len(gpts) == len(pts), (len(gpts), len(pts))
assert abs(L_file - L_geod) < 0.05, (L_file, L_geod)
print(f'KMZ: {OUT_KMZ}')
print(f'  записи: {names}; линий {len(lines)} (8F-сегментов {len(corr_segs)}), меток {len(pins_n)}')
print(f'  обратный парсинг: {len(gpts)} точек, длина из файла {L_file:.2f} м')
