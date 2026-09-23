# -*- coding: utf-8 -*-
"""
Шаг 50. KMZ фидера ЦУ -> ОРШ-2 (с. Пригородное) — топология v3.

Тот же участок, что проверялся пользователем (зона 80 ДХ, врез у хлебозавода),
но по оптимизированной топологии v3:
  - зонный ОРШ стоит в ЦЕНТРЕ СЕКТОРА (медиана дерева зоны, сдвиг ~193 м
    от узла вреза к домам) — пунктирный «хвост» от вреза к шкафу не рисуется:
    распределительная сеть зоны физически не меняется, меняется точка стояния;
  - фидер прокладывается к шкафу-медиане по кратчайшему пути дорожного графа,
    ОБРЕЗАННОГО границей НП.

Линии:
  1) зелёная — проектная трасса v3: ЦУ -> медиана ОРШ-2 (кратчайший путь
     в границе НП); оранжевые сегменты — отдельный кабель 8F вне дерева;
  2) серый пунктир — v2-трасса к узлу вреза (683,9 м) — для сравнения;
  3) белая — маршрут пользователя (681,3 м) — эталон кратчайшего к врезу.

Выход: download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v3.kmz
"""
import json
import math
import sys
import zipfile
import importlib.util
import xml.etree.ElementTree as ET

from pyproj import Geod

BASE = '/home/z/my-project'
Z = 18
KEY = 'prigorodnoe'
SEL_PX = (3907.11, 3325.35)
OUT_KMZ = f'{BASE}/download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v3.kmz'

sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty, tx2lon, ty2lat  # noqa: E402


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de44 = load_mod('de44', f'{BASE}/scripts/44_feeder_shortest.py')
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
    lat = ty2lat(gy / 256.0, Z)
    return lat, lon


def geod_len(pts):
    return sum(GEOD.inv(lo1, la1, lo2, la2)[2]
               for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]))


# ============================================================ модель v3 ===
v = next(v for v in de28.VILLAGES if v['key'] == KEY)
V3 = de46.VillageV3(v)
t = V3.t
boq3 = json.load(open(f'{BASE}/work/boq_decentral_data_v3.json'))
bv3 = next(x for x in boq3['villages'] if x['key'] == KEY)
cuts = [tuple(l['node']) for l in bv3['cut_log']]
sel = min(cuts, key=lambda k: (k[0] - SEL_PX[0]) ** 2 + (k[1] - SEL_PX[1]) ** 2)
assert math.hypot(sel[0] - SEL_PX[0], sel[1] - SEL_PX[1]) < 0.05

med = V3.medians_of(cuts)[sel]
bz = next(z for z in bv3['zones'] if z.get('cut_px') == [round(sel[0], 1), round(sel[1], 1)])
assert tuple(bz['orsh_px']) == tuple(round(x, 1) for x in med)

A = V3.account_v3(cuts, V3.medians_of(cuts))
ff = de28.ceilr(1.25 * A['spl'][sel])

# маршрут v3: ЦУ -> медиана (кратчайший путь в границе НП)
path_i = []
cur = V3.idx[med]
while cur != V3.root_i and V3.pred[cur] >= 0:
    path_i.append(cur)
    cur = int(V3.pred[cur])
path_i.append(V3.root_i)
path_i.reverse()

edges = []
for a, b in zip(path_i, path_i[1:]):
    k = V3.ekey(a, b)
    edges.append(dict(a=a, b=b, shared=k in V3.child_of,
                      L=V3.L_of(a, b), ffw=A['ffw'].get(k, 0)))
L_v3 = sum(e['L'] for e in edges)
L_shared = sum(e['L'] for e in edges if e['shared'])
L_corr = sum(e['L'] for e in edges if not e['shared'])

pts = [px_to_geo(V3.P[i][0], V3.P[i][1]) for i in path_i]
L_geod = geod_len(pts)
assert abs(bz['root_dist_m'] - L_v3) < 0.1, (bz['root_dist_m'], L_v3)

# сравнение: v2 (к врезу) и маршрут пользователя
V2 = de44.VillageV2(v)
p2 = []
cur = V2.idx[sel]
while cur != V2.root_i and V2.pred[cur] >= 0:
    p2.append(cur)
    cur = int(V2.pred[cur])
p2.append(V2.root_i)
p2.reverse()
v2_geo = [px_to_geo(V2.P[i][0], V2.P[i][1]) for i in p2]
L_v2 = sum(V2.L_of(a, b) for a, b in zip(p2, p2[1:]))
assert abs(L_v2 - Q['L_short']) < 0.5
user_geo = [tuple(p) for p in Q['user_geo']]
L_user = Q['L_user']
shift = math.hypot(med[0] - sel[0], med[1] - sel[1]) * V3.mpp

print(f'v3: медиана зоны {med}, сдвиг от вреза {shift:.0f} м')
print(f'трасса v3: {len(path_i)} узлов, {L_v3:.1f} м '
      f'(общие {L_shared:.0f} / отдельный 8F {L_corr:.0f} м); геодезически {L_geod:.1f} м')
print(f'сравнение: v2 к врезу {L_v2:.1f} м; пользователь {L_user:.1f} м')


def fmt(x, nd=1):
    return f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')


coords = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in pts)
coords_v2 = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in v2_geo)
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

med_geo = px_to_geo(med[0], med[1])
cut_geo = px_to_geo(sel[0], sel[1])
cu_geo = px_to_geo(V3.P[V3.root_i][0], V3.P[V3.root_i][1])

desc = f"""\
Магистральный участок кабеля: фидер ЦУ → зонный ОРШ-2 (схема D, топология v3 — оптимизированная)

Село Пригородное (г.а. Риддер, ВКО) · зона: {bz['houses']} ДХ · сплиттеры {bz['splitters']}×1:64 · фидер {bz['feeder_fibers']} волокна

ЧТО ИЗМЕНИЛОСЬ В v3:
  1) ОРШ стоит в ЦЕНТРЕ СЕКТОРА — медиане дерева зоны (зелёный квадрат), на {fmt(shift, 0)} м ближе к домам, чем узел вреза (оранжевая точка). Состав зоны и распределительная сеть не меняются — переносится только точка стояния шкафа.
  2) Фидер прокладывается К ШКАФУ по кратчайшему пути дорожного графа, обрезанного границей населённого пункта (морфология застройки).

ТРАССА v3 (зелёная): {fmt(L_v3)} м — кратчайший путь ЦУ → медиана ОРШ-2 в границе НП
   из них {fmt(L_shared)} м — участки, общие с распределительной сетью (в одном кабеле),
   {fmt(L_corr)} м — отдельный кабель 8 волокон (оранжевые сегменты)
   длина геодезическая WGS84: {fmt(L_geod)} м · по книге v3 (root_dist_m): {fmt(bz['root_dist_m'])} м

СРАВНЕНИЕ (серый пунктир): v2-трасса к узлу вреза — {fmt(L_v2)} м; маршрут пользователя (белая) — {fmt(L_user)} м.
   v3 короче на {fmt(L_v2 - L_v3)} м: фидеру больше не нужно доходить до края сектора.
   Экономия волокна по зоне (распределительные + фидер): ~3,3 волокно-км (шаг 46a).

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
    <name>Фидер ЦУ → ОРШ-2, с. Пригородное (схема D, v3 — ОРШ в центре сектора)</name>
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
      <name>Фидер ЦУ → ОРШ-2 (v3): {fmt(L_v3)} м к медиане зоны</name>
      <description><![CDATA[{desc}]]></description>
      <styleUrl>#feeder</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords}</coordinates></LineString>
    </Placemark>
{corr_placemarks}    <Placemark>
      <name>v2-трасса к узлу вреза: {fmt(L_v2)} м (для сравнения)</name>
      <styleUrl>#old</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_v2}</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Маршрут пользователя: {fmt(L_user)} м</name>
      <styleUrl>#user</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_user}</coordinates></LineString>
    </Placemark>
{pin('pinCu', 'ЦУ — точка входа фидера (здание-якорь)', cu_geo[0], cu_geo[1], 'Единый узел OLT, корневая зона')}
{pin('pinCut', f'Узел вреза зоны (граница сектора)', cut_geo[0], cut_geo[1], f'Точка отделения зоны от дерева сети; {bz["houses"]} ДХ ниже по дереву')}
{pin('pinOrsh', f'ОРШ-2 — шкаф в центре сектора ({bz["houses"]} ДХ)', med_geo[0], med_geo[1], f'Медиана дерева зоны; сдвиг от вреза {fmt(shift, 0)} м; фидер {bz["feeder_fibers"]} волокна')}
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

ns = '{http://www.opengis.net/kml/2.2}'
pls = root.findall(f'{ns}Document/{ns}Placemark')
lines = [p for p in pls if p.find(f'{ns}LineString') is not None]
pins_n = [p for p in pls if p.find(f'{ns}Point') is not None]
main = next(p for p in lines if 'v3' in p.find(f'{ns}name').text)
gpts = [tuple(map(float, c.split(',')[:2]))
        for c in main.find(f'{ns}LineString/{ns}coordinates').text.split()]
L_file = geod_len([(la, lo) for lo, la in gpts])
assert len(gpts) == len(pts), (len(gpts), len(pts))
assert abs(L_file - L_geod) < 0.05, (L_file, L_geod)
print(f'KMZ: {OUT_KMZ}')
print(f'  записи: {names}; линий {len(lines)} (из них 8F-сегментов {len(corr_segs)}), меток {len(pins_n)}')
print(f'  обратный парсинг: {len(gpts)} точек, геодезическая длина из файла {L_file:.2f} м '
      f'(допуск 0,05 м на округление координат)')
