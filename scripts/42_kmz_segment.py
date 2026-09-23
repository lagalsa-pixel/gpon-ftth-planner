# -*- coding: utf-8 -*-
"""
Шаг 42. KMZ-файл для проверки длины участка кабеля (схема D).

Участок: магистральный фидер ЦУ -> зонный ОРШ-2, с. Пригородное (80 ДХ,
root_dist_m = 1313,6 м — цифра из BoQ схемы D и легенды карты шага 37).

Геометрия — ТО ЖЕ дерево магистрали, что строилось для финальных карт
(28_decentral_explore.Tree + partition_greedy(15.0)); маршрут = цепочка
узлов от корня до зонного вреза (пунктир зелёного цвета на карте
«05_Пригородное_зоны_ОРШ_схема_D.jpg»).

Координаты — точный обратный Web Mercator от привязки мозаики
(mosaic_geo.json; валидация 42a: якорь OSM воспроизводится с точностью 0,2 м).

Выход: download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D.kmz
Запуск: python3 scripts/42_kmz_segment.py
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
SEL_PX = (3907.11, 3325.35)     # узел зонного ОРШ (из cut_log BoQ схемы D)
S_MIN = 15.0                     # порог окупаемости зонного ОРШ (как в шаге 37)
OUT_KMZ = f'{BASE}/download/Фидер_ЦУ-ОРШ2_Пригородное_схема_D.kmz'

sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty, tx2lon, ty2lat  # noqa: E402

GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
GEOD = Geod(ellps='WGS84')

# цвет зоны ОРШ-2 на карте шага 37: PALETTE[1] = (47, 158, 68) -> KML aabbggrr
KML_GREEN = 'ff449e2f'
KML_RED = 'ff2b1dff'      # красный (ЦУ)
KML_ORANGE = 'ff009be0'   # оранжевый (узел подключения)


def px_to_geo(x, y):
    """Пиксель мозаики -> (lat, lon) WGS84, точный обратный Web Mercator z18."""
    tx0f = lon2tx(GEO['west'], Z)
    ty0f = lat2ty(GEO['north'], Z)
    gx, gy = tx0f * 256.0 + x, ty0f * 256.0 + y
    lon = gx / 256.0 / (1 << Z) * 360.0 - 180.0
    lat = ty2lat(gy / 256.0, Z)
    return lat, lon


def fmt(x, nd=1):
    return f'{x:,.{nd}f}'.replace(',', ' ').replace('.', ',')


def geod_len(pts):
    """Сумма геодезических расстояний WGS84 по ломаной [(lat, lon), ...]."""
    s = 0.0
    for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
        s += GEOD.inv(lo1, la1, lo2, la2)[2]
    return s


# =========================================================== дерево сети ===
spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)

v = next(v for v in de28.VILLAGES if v['key'] == KEY)
t = de28.Tree(v)
cuts, _ = t.partition_greedy(S_MIN)

boq = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
bv = next(x for x in boq['villages'] if x['key'] == KEY)

# --- контроль воспроизводимости: врезы должны совпасть с BoQ ---
cut_nodes = [tuple(c) for c in cuts]
log_nodes = [tuple(l['node']) for l in bv['cut_log']]
assert cut_nodes == log_nodes, f'врезы не совпали:\n  {cut_nodes}\n  {log_nodes}'
print('контроль врезов: совпадают с cut_log BoQ ->', cut_nodes)

# --- выбор зоны ОРШ-2 ---
sel = min(cuts, key=lambda k: (k[0] - SEL_PX[0]) ** 2 + (k[1] - SEL_PX[1]) ** 2)
assert math.hypot(sel[0] - SEL_PX[0], sel[1] - SEL_PX[1]) < 0.05, sel

cutset = set(cuts)
zr = {t.root: t.root}
for u in t.bfs[1:]:
    zr[u] = u if u in cutset else zr[t.parent[u]]
zone_dh = {}
for node, dh in t.homes.items():
    zone_dh[zr[node]] = zone_dh.get(zr[node], 0) + dh
order = sorted(cuts, key=lambda c: -zone_dh[c])
zname = f'ОРШ-{order.index(sel) + 1}'
assert zname == 'ОРШ-2' and zone_dh[sel] == 80, (zname, zone_dh[sel])

bz = next(z for z in bv['zones'] if abs(z['px'][0] - sel[0]) < 0.05 and abs(z['px'][1] - sel[1]) < 0.05)
print(f'зона: {zname}, {zone_dh[sel]} ДХ, root_dist BoQ = {bz["root_dist_m"]} м')

# --- маршрут фидера: цепочка узлов от корня до вреза (как в шаге 37) ---
chain = [sel]
u = sel
while t.parent[u] is not None:
    u = t.parent[u]
    chain.append(u)
chain.reverse()
print(f'маршрут: {len(chain)} узлов, от {chain[0]} до {chain[-1]}')

# --- длины ---
L_proj = t.dist[sel]                      # по модели проекта (px * mpp)
L_edges = 0.0
for a, b in zip(chain, chain[1:]):
    key_ab = (min(a, b), max(a, b))
    assert key_ab in t.edge_len, key_ab   # каждое звено — реальное ребро сети
    L_edges += t.edge_len[key_ab]
assert abs(L_edges - L_proj) < 1e-6
assert abs(L_proj - bz['root_dist_m']) < 0.05, (L_proj, bz['root_dist_m'])

pts = [px_to_geo(x, y) for (x, y) in chain]
L_geod = geod_len(pts)
L_direct = GEOD.inv(pts[0][1], pts[0][0], pts[-1][1], pts[-1][0])[2]
d_diff = L_geod - L_proj
d_pct = 100.0 * d_diff / L_proj

anchor = json.load(open(f"{BASE}/work/{KEY}/{v['net']}"))['anchor']
cu_lat, cu_lon = anchor['lat'], anchor['lon']

print(f'длина по проекту (px*mpp) : {L_proj:.1f} м  (= root_dist_m BoQ)')
print(f'длина геодезическая WGS84 : {L_geod:.1f} м')
print(f'расхождение               : {d_diff:+.1f} м ({d_pct:+.2f} %)')
print(f'прямая ЦУ-ОРШ             : {L_direct:.1f} м  (коэф. маршрута {L_proj / L_direct:.2f})')

# ================================================================= KML ===
coords = ' '.join(f'{lo:.7f},{la:.7f},0' for la, lo in pts)

desc = f"""\
Магистральный участок кабеля: фидер ЦУ → зонный ОРШ-2 (схема D)

Село Пригородное (г.а. Риддер, ВКО) · зона ОРШ-2: 80 ДХ · сплиттеры 2×1:64 · фидер 3 волокна

Длина по проекту: {fmt(L_proj)} м — root_dist_m из BoQ схемы D (на карте: «{fmt(L_proj / 1000, 2)} км от ЦУ»)
   методика: пиксельная геометрия маршрута по улицам × {fmt(GEO['mpp'], 4)} м/px (Google z18, Web Mercator)

Длина геодезическая WGS84 (по точкам этой линии): {fmt(L_geod)} м
Расхождение с проектом: {('+' if d_diff >= 0 else '−') + fmt(abs(d_diff), 1)} м ({('+' if d_pct >= 0 else '−') + fmt(abs(d_pct), 2)} %)
Прямая (воздушная) между концами: {fmt(L_direct)} м · коэффициент удлинения маршрута: {fmt(L_proj / L_direct, 2)}

Маршрут: {len(chain)} точек по улицам села — та же геометрия, что пунктиром зелёного цвета на карте «05_Пригородное_зоны_ОРШ_схема_D.jpg» (зоны ОРШ, схема D).

Примечание: длина отсчитывается от узла подключения дерева у ЦУ (оранжевая точка) — как в расчёте BoQ; здание-якорь ЦУ (красная точка) находится в ~{GEOD.inv(cu_lon, cu_lat, pts[0][1], pts[0][0])[2]:.0f} м от узла подключения.

Проверка в Google Earth Pro: ПКМ по линии → «Сведения об объекте» → вкладка «Измерение».
Либо «Инструменты» → «Линейка» → проложить путь по тем же улицам и сравнить."""


def pin(style_id, color, scale, name, lat, lon, desc=''):
    return f"""    <Placemark>
      <name>{name}</name>
      <description>{desc}</description>
      <styleUrl>#{style_id}</styleUrl>
      <Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>
    </Placemark>"""


kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Фидер ЦУ → ОРШ-2, с. Пригородное (схема D) — проверка длины</name>
    <open>1</open>
    <Style id="feeder">
      <LineStyle><color>{KML_GREEN}</color><width>5</width></LineStyle>
    </Style>
    <Style id="pinCu">
      <IconStyle><color>{KML_RED}</color><scale>1.5</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="pinNode">
      <IconStyle><color>{KML_ORANGE}</color><scale>0.9</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="pinOrsh">
      <IconStyle><color>{KML_GREEN}</color><scale>1.4</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_square.png</href></Icon>
      </IconStyle>
    </Style>
    <Placemark>
      <name>Фидер ЦУ → ОРШ-2: {fmt(L_proj)} м (по проекту) / {fmt(L_geod)} м (геодезически)</name>
      <description><![CDATA[{desc}]]></description>
      <styleUrl>#feeder</styleUrl>
      <LineString>
        <tessellate>1</tessellate>
        <altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords}</coordinates>
      </LineString>
    </Placemark>
{pin('pinCu', KML_RED, 1.5, 'ЦУ — здание-якорь (ОРШ села, точка входа фидера)', cu_lat, cu_lon)}
{pin('pinNode', KML_ORANGE, 0.9, 'Узел подключения фидера (начало отсчёта длины)', *pts[0])}
{pin('pinOrsh', KML_GREEN, 1.4, f'ОРШ-2 — зонный шкаф (80 ДХ, {fmt(L_proj)} м от ЦУ)', *pts[-1])}
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
coord_els = root.findall('.//k:LineString/k:coordinates', ns)
assert len(coord_els) == 1
pts2 = [(float(c.split(',')[1]), float(c.split(',')[0]))
        for c in coord_els[0].text.strip().split()]
assert len(pts2) == len(pts), (len(pts2), len(pts))
for (a, b) in zip(pts, pts2):
    assert abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6  # 7 знаков после запятой
L_check = geod_len(pts2)
assert abs(L_check - L_geod) < 0.05, (L_check, L_geod)   # округление координат до 1e-7 град

pins = root.findall('.//k:Placemark', ns)
import os
print(f'\nПРОВЕРКА KMZ:OK  записей doc.kml=1, точек {len(pts2)}, '
      f'геодезическая длина из файла {L_check:.1f} м, меток {len(pins)}')
print(f'файл: {OUT_KMZ} ({os.path.getsize(OUT_KMZ)} байт)')
