# -*- coding: utf-8 -*-
"""
Шаг 43a. Диагноз логики прокладки трасс: маршрут пользователя vs проектная трасса.

Гипотеза: дерево сети (шаг 06: MST терминалов -> объединение путей -> SPT от
корня, приближение дерева Штейнера) минимизирует СУММАРНУЮ длину сети, но
путь корень -> зонный узел внутри него может быть вдвое длиннее кратчайшего
пути по улицам. Фидер ЦУ -> ОРШ (точка-точка) должен идти по кратчайшему
маршруту дорожного графа, а не по пути внутри дерева распределения.

Проверка:
  1) маршрут пользователя (upload/ЦУ - ОРШ-2.kmz) -> px мозаики, длина;
  2) полный дорожный граф OSM (как в 06_network) -> лежит ли маршрут на улицах;
  3) Дейкстра по ПОЛНОМУ графу: кратчайший путь узел ЦУ -> узел ОРШ-2;
  4) сравнение: пользователь / кратчайший / путь в дереве (1313,6 м);
  5) точка расхождения маршрутов.
"""
import json
import math
import sys
import zipfile
import importlib.util
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from pyproj import Geod

BASE = '/home/z/my-project'
Z = 18
KEY = 'prigorodnoe'
SEL_PX = (3907.11, 3325.35)
S_MIN = 15.0

sys.path.insert(0, f'{BASE}/scripts')
from common import lon2tx, lat2ty  # noqa: E402

GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]
GEOD = Geod(ellps='WGS84')


def geo_to_px(lat, lon):
    """WGS84 -> px мозаики, точный обратный Web Mercator z18."""
    tx = (lon + 180.0) / 360.0 * (1 << Z)
    ty = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat)))
          / math.pi) / 2.0 * (1 << Z)
    tx0f, ty0f = lon2tx(GEO['west'], Z), lat2ty(GEO['north'], Z)
    return (tx - tx0f) * 256.0, (ty - ty0f) * 256.0


def geod_len(pts):
    return sum(GEOD.inv(lo1, la1, lo2, la2)[2]
               for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]))


# ============================================ 1) маршрут пользователя ====
kmz = zipfile.ZipFile(f'{BASE}/upload/ЦУ - ОРШ-2.kmz')
kml = kmz.read('doc.kml').decode('utf-8')
root_xml = ET.fromstring(kml)
coords_el = root_xml.find('.//{http://www.opengis.net/kml/2.2}LineString/'
                          '{http://www.opengis.net/kml/2.2}coordinates')
user_geo = [tuple(float(v) for v in c.split(',')[:2][::-1])
            for c in coords_el.text.strip().split()]
L_user = geod_len(user_geo)
user_px = [geo_to_px(la, lo) for la, lo in user_geo]
print(f'маршрут пользователя: {len(user_geo)} точек, длина {L_user:.1f} м')
print(f'  старт px ({user_px[0][0]:.1f}, {user_px[0][1]:.1f})  '
      f'финиш px ({user_px[-1][0]:.1f}, {user_px[-1][1]:.1f})')

# ============================================ 2) полный дорожный граф ====
def geo_to_px_aff(lat, lon, west, north, mpp):
    return ((lon - west) * (111320 * math.cos(math.radians(lat))) / mpp,
            (north - lat) * 111320 / mpp)


osm = json.load(open(f'{BASE}/work/{KEY}/osm.json'))
mpp = GEO['mpp']
pts_all, idx_all, edges_all = [], {}, []


def add_node(x, y):
    k = (round(x, 1), round(y, 1))
    i = idx_all.get(k)
    if i is None:
        i = len(pts_all)
        pts_all.append((x, y))
        idx_all[k] = i
    return i


mstep = 4.0
for r in osm['roads']:
    pl = [geo_to_px_aff(la, lo, GEO['west'], GEO['north'], mpp) for la, lo in r['pts']]
    if all(p[0] < -200 or p[0] > GEO['W'] + 200 or p[1] < -200 or p[1] > GEO['H'] + 200
           for p in pl):
        continue
    dens = [pl[0]]
    for p in pl[1:]:
        q = dens[-1]
        seg = math.hypot(p[0] - q[0], p[1] - q[1]) * mpp
        n_sub = int(seg / mstep)
        for k in range(1, n_sub + 1):
            dens.append((q[0] + (p[0] - q[0]) * k / max(n_sub, 1),
                         q[1] + (p[1] - q[1]) * k / max(n_sub, 1)))
        if seg < mstep:
            dens.append(p)
    prev = None
    for p in dens:
        cur = add_node(p[0], p[1])
        if prev is not None and cur != prev:
            d = math.hypot(pts_all[cur][0] - pts_all[prev][0],
                           pts_all[cur][1] - pts_all[prev][1]) * mpp
            if d > 0.05:
                edges_all.append((prev, cur, d))
        prev = cur

P = np.array(pts_all)
n = len(P)
print(f'\nполный дорожный граф: {n} узлов, {len(edges_all)} рёбер')

rows, cols, vals = [], [], []
for (u, w, l) in edges_all:
    rows += [u, w]; cols += [w, u]; vals += [l, l]
C = csr_matrix((vals, (rows, cols)), shape=(n, n))

kdt = cKDTree(P)

# точки пользователя на графе? (query возвращает (dist_px, idx))
snap_d_px, snap_i = kdt.query(np.array(user_px))
print('привязка точек пользователя к улицам (м):')
print('  ' + '  '.join(f'{d * mpp:.1f}' for d in snap_d_px))

# ============================================ 3) Дейкстра по полному графу
net = json.load(open(f'{BASE}/work/{KEY}/network_v2.json'))
ax, ay = net['anchor']['x'], net['anchor']['y']
d_root, root_id = kdt.query([ax, ay])
root_id = int(root_id)
d_tgt, tgt_id = kdt.query([SEL_PX[0], SEL_PX[1]])
tgt_id = int(tgt_id)
print(f'\nкорень (ЦУ): узел {root_id}, от якоря {d_root * mpp:.1f} м')
print(f'цель (ОРШ-2): узел {tgt_id}, от узла сети {d_tgt * mpp:.1f} м')

D, pred = dijkstra(C, indices=root_id, return_predecessors=True)
L_short = float(D[tgt_id])
sp = [tgt_id]
cur = tgt_id
while pred[cur] >= 0 and cur != root_id:
    cur = int(pred[cur])
    sp.append(cur)
sp.reverse()
sp_px = [tuple(P[i]) for i in sp]
sp_geo = []
for (x, y) in sp_px:
    tx0f, ty0f = lon2tx(GEO['west'], Z), lat2ty(GEO['north'], Z)
    gx, gy = tx0f * 256.0 + x, ty0f * 256.0 + y
    lon = gx / 256.0 / (1 << Z) * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * gy / 256.0 / (1 << Z)))))
    sp_geo.append((lat, lon))
print(f'кратчайший путь по ПОЛНОМУ дорожному графу: {len(sp)} узлов, {L_short:.1f} м')

# маршрут пользователя по графу: сумма кратчайших между последовательными точками
L_user_graph = 0.0
for a, b in zip(snap_i, snap_i[1:]):
    D2 = dijkstra(C, indices=int(a))
    L_user_graph += float(D2[int(b)])
print(f'маршрут пользователя по графу (через его точки): {L_user_graph:.1f} м')

# ============================================ 4) путь в дереве (шаг 42) ==
spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)
v = next(v for v in de28.VILLAGES if v['key'] == KEY)
t = de28.Tree(v)
cuts, _ = t.partition_greedy(S_MIN)
sel = min(cuts, key=lambda k: (k[0] - SEL_PX[0]) ** 2 + (k[1] - SEL_PX[1]) ** 2)
chain = [sel]
u = sel
while t.parent[u] is not None:
    u = t.parent[u]
    chain.append(u)
chain.reverse()
L_tree = t.dist[sel]
print(f'путь в ДЕРЕВЕ сети (текущая логика): {len(chain)} узлов, {L_tree:.1f} м')

# ============================================ 5) точка расхождения =======
sp_arr = np.array(sp_px)
kdt_sp = cKDTree(sp_arr)
div = None
for j in range(1, len(chain)):
    d = float(kdt_sp.query([chain[j][0], chain[j][1]])[0]) * mpp
    if d > 15.0:
        div = j
        print(f'\nрасхождение маршрутов: узел дерева #{j} {chain[j]} '
              f'в {d:.0f} м от кратчайшего пути; пройдено от ЦУ {t.dist[chain[j - 1]]:.0f} м')
        break
if div is None:
    print('\nмаршруты существенно не расходятся')

print(f'''
================= ИТОГ =================
путь в дереве (проект, BoQ)          : {L_tree:7.1f} м
кратчайший по улицам (Дейкстра)      : {L_short:7.1f} м
маршрут пользователя (геодезически)  : {L_user:7.1f} м
маршрут пользователя по графу        : {L_user_graph:7.1f} м
экономия vs дерево                   : {L_tree - L_short:.0f} м ({100 * (L_tree - L_short) / L_tree:.0f}%)
''')

json.dump(dict(user_geo=user_geo, user_px=user_px, L_user=L_user,
               sp_px=[list(p) for p in sp_px], sp_geo=sp_geo, L_short=L_short,
               L_user_graph=L_user_graph,
               chain=[list(c) for c in chain], L_tree=L_tree),
          open(f'{BASE}/work/route_diag_prigorodnoe.json', 'w'), ensure_ascii=False)
print('сохранено: work/route_diag_prigorodnoe.json')
