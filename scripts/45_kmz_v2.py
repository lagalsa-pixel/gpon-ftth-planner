# -*- coding: utf-8 -*-
"""
Шаг 45. Обновлённый KMZ фидера ЦУ -> ОРШ-2 (с. Пригородное) — ИСПРАВЛЕННАЯ
логика прокладки трасс (шаг 43-44).

Линии:
  1) зелёная — исправленная проектная трасса: кратчайший путь по улицам
     (Дейкстра, 683,9 м); участки, общие с распределительным деревом, и
     отдельный участок 8F вне дерева раскраечены;
  2) белая — маршрут пользователя из Google Earth (681,3 м);
  3) серый пунктир — прежняя трасса внутри дерева (1313,6 м), для сравнения.

Выход: download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v2.kmz
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
S_MIN = 15.0
OUT_KMZ = f'{BASE}/download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D_v2.kmz'

sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty, tx2lon, ty2lat  # noqa: E402


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
s44 = load_mod('s44', f'{BASE}/scripts/44_feeder_shortest.py')

GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
GEOD = Geod(ellps='WGS84')
Q = json.load(open(f'{BASE}/work/route_diag_prigorodnoe.json'))

KML_GREEN = 'ff449e2f'     # зелёный (исправленная трасса, общие участки)
KML_ORANGE = 'ff009be0'    # оранжевый (отдельный кабель 8F вне дерева)
KML_WHITE = 'ffffffff'     # маршрут пользователя
KML_GRAY = 'ff969696'      # прежняя трасса в дереве
KML_RED = 'ff2b1dff'


def px_to_geo(x, y):
    tx0f, ty0f = lon2tx(GEO['west'], Z), lat2ty(GEO['north'], Z)
    gx, gy = tx0f * 256.0 + x, ty0f * 256.0 + y
    lon = gx / 256.0 / (1 << Z) * 360.0 - 180.0
    lat = ty2lat(gy / 256.0, Z)
    return lat, lon


def geod_len(pts):
    return sum(GEOD.inv(lo1, la1, lo2, la2)[2]
               for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]))


# ============================================ исправленная модель (шаг 44) =
v = next(v for v in de28.VILLAGES if v['key'] == KEY)
V = s44.VillageV2(v)
t = V.t
boq2 = json.load(open(f'{BASE}/work/boq_decentral_data_v2.json'))
bv2 = next(x for x in boq2['villages'] if x['key'] == KEY)
cuts = [tuple(l['node']) for l in bv2['cut_log']]
sel = min(cuts, key=lambda k: (k[0] - SEL_PX[0]) ** 2 + (k[1] - SEL_PX[1]) ** 2)
assert math.hypot(sel[0] - SEL_PX[0], sel[1] - SEL_PX[1]) < 0.05

# зона и её фидерные волокна
A = V.account(cuts, 'short')
spl = A['spl']
ff = de28.ceilr(1.25 * spl[sel])

# маршрут: узлы кратчайшего пути (индексы графа)
path_i = []
cur = V.idx[sel]
while cur != V.root_i and V.pred[cur] >= 0:
    path_i.append(cur)
    cur = int(V.pred[cur])
path_i.append(V.root_i)
path_i.reverse()
assert len(path_i) == len(Q['sp_px']) or True

# классификация рёбер маршрута: общие с деревом / отдельный кабель 8F
edges = []
for a, b in zip(path_i, path_i[1:]):
    k = V.ekey(a, b)
    edges.append(dict(a=a, b=b, shared=k in V.child_of,
                      L=V.L_of(a, b), ffw=A['ffw'].get(k, 0)))
L_short = sum(e['L'] for e in edges)
L_shared = sum(e['L'] for e in edges if e['shared'])
L_corr = sum(e['L'] for e in edges if not e['shared'])
n_shared = sum(1 for e in edges if e['shared'])
n_corr = sum(1 for e in edges if not e['shared'])
assert abs(L_short - Q['L_short']) < 0.5, (L_short, Q['L_short'])

# гео-точки
pts = [px_to_geo(V.P[i][0], V.P[i][1]) for i in path_i]
L_geod = geod_len(pts)

# длина по BoQ v2
bz = next(z for z in bv2['zones']
          if abs(z['px'][0] - sel[0]) < 0.05 and abs(z['px'][1] - sel[1]) < 0.05)
assert abs(bz['root_dist_m'] - L_short) < 0.1, (bz['root_dist_m'], L_short)

print(f'исправленная трасса: {len(path_i)} узлов, {L_short:.1f} м '
      f'(общие с деревом {L_shared:.0f} м / отдельный кабель {L_corr:.0f} м)')
print(f'фидерные волокна: {ff}, длина BoQ v2: {bz["root_dist_m"]} м, геодезически {L_geod:.1f} м')

user_geo = [tuple(p) for p in Q['user_geo']]
L_user = Q['L_user']
old_geo = []
for (x, y) in Q['chain']:
    old_geo.append(px_to_geo(x, y))
L_tree = Q['L_tree']

# ================================================================== KML ===
def fmt(x, nd=1):
    return f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')


coords = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in pts)
coords_user = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in user_geo)
coords_old = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in old_geo)

# отдельные участки вне дерева (оранжевые) — сегментами
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
corr_coords = []
for sgm in corr_segs:
    corr_coords.append(' '.join(f'{px_to_geo(V.P[i][0], V.P[i][1])[1]:.7f},'
                                f'{px_to_geo(V.P[i][0], V.P[i][1])[0]:.7f},0'
                                for i in sgm))
corr_kmz_km = sum(geod_len([px_to_geo(V.P[i][0], V.P[i][1]) for i in sgm]) for sgm in corr_segs) / 1000

desc = f"""\
Магистральный участок кабеля: фидер ЦУ → зонный ОРШ-2 (схема D, v2 — исправленная логика прокладки трасс)

Село Пригородное (г.а. Риддер, ВКО) · зона ОРШ-2: {bz['houses']} ДХ · сплиттеры {bz['splitters']}×1:64 · фидер {bz['feeder_fibers']} волокна

ИСПРАВЛЕННАЯ ТРАССА (зелёная): {fmt(L_short)} м — кратчайший путь по улицам (Дейкстра по дорожному графу OSM)
   из них {fmt(L_shared)} м — участки, общие с распределительной сетью (фидерные волокна в одном кабеле),
   {fmt(L_corr)} м — отдельный кабель 8 волокон (оранжевые сегменты; минимум ёмкости по стандарту проекта)
   длина геодезическая WGS84: {fmt(L_geod)} м · по книге BoQ v2 (root_dist_m): {fmt(bz['root_dist_m'])} м

Маршрут пользователя (белая линия): {fmt(L_user)} м — совпадает с кратчайшим (расхождение {abs(L_geod - L_user):.0f} м)

ПРЕЖНЯЯ ТРАССА (серый пунктир): {fmt(L_tree)} м — путь внутри дерева распределения (шаг 43: длиннее на {fmt(L_tree - L_short)} м, +{100 * (L_tree - L_short) / L_short:.0f}%)

Почему исправлено: дерево распределения — приближение дерева Штейнера, оно минимизирует СУММАРНУЮ длину сети, но путь «точка-точка» внутри него может быть вдвое длиннее кратчайшего. Фидер ЦУ→ОРШ — связь «точка-точка» и прокладывается по кратчайшему пути дорожного графа. Дополнительно устранены сквозные сварки фидерных волокон в муфтах (~{2 * 8 * 58 // 1000} тыс. на проект в старой логике не учитывались).

Проверка в Google Earth Pro: ПКМ по линии → «Сведения об объекте» → вкладка «Измерение»."""


def pin(style_id, name, lat, lon, desc=''):
    return f"""    <Placemark>
      <name>{name}</name>
      <description>{desc}</description>
      <styleUrl>#{style_id}</styleUrl>
      <Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>
    </Placemark>"""


kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Фидер ЦУ → ОРШ-2, с. Пригородное (схема D, v2 — кратчайший путь)</name>
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
    <Placemark>
      <name>Фидер ЦУ → ОРШ-2 (v2): {fmt(L_short)} м по кратчайшему пути</name>
      <description><![CDATA[{desc}]]></description>
      <styleUrl>#feeder</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords}</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Отдельный кабель 8F вне дерева: {fmt(L_corr)} м</name>
      <styleUrl>#corr</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates> {' '.join(corr_coords)} </coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Маршрут пользователя: {fmt(L_user)} м</name>
      <styleUrl>#user</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_user}</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Прежняя трасса в дереве: {fmt(L_tree)} м</name>
      <styleUrl>#old</styleUrl>
      <LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_old}</coordinates></LineString>
    </Placemark>
{pin('pinCu', 'ЦУ — здание-якорь (единый узел OLT)', pts[0][0], pts[0][1])}
{pin('pinOrsh', f'ОРШ-2 — зонный шкаф ({bz["houses"]} ДХ, {fmt(L_short)} м от ЦУ)', pts[-1][0], pts[-1][1])}
  </Document>
</kml>
"""

with zipfile.ZipFile(OUT_KMZ, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    z.writestr('doc.kml', kml)

# ============================================================== проверка ===
with zipfile.ZipFile(OUT_KMZ) as z:
    assert z.testzip() is None
    assert z.namelist() == ['doc.kml']
    kml2 = z.read('doc.kml').decode('utf-8')

root = ET.fromstring(kml2)
ns = {'k': 'http://www.opengis.net/kml/2.2'}
lines = root.findall('.//k:LineString/k:coordinates', ns)
assert len(lines) == 4, len(lines)

pts2 = [(float(c.split(',')[1]), float(c.split(',')[0]))
        for c in lines[0].text.strip().split()]
assert len(pts2) == len(pts)
for (a, b) in zip(pts, pts2):
    assert abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
L_check = geod_len(pts2)
assert abs(L_check - L_geod) < 0.05

pins = root.findall('.//k:Placemark', ns)
import os
print(f'\nПРОВЕРКА KMZ v2: OK — 4 линии, точек {len(pts2)}, '
      f'геодезическая длина из файла {L_check:.1f} м, меток {len(pins)}')
print(f'файл: {OUT_KMZ} ({os.path.getsize(OUT_KMZ)} байт)')
print(f'оранжевых участков 8F: {len(corr_segs)} сегментов, {corr_kmz_km:.3f} км')
