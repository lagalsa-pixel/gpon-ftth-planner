# -*- coding: utf-8 -*-
"""
Шаг 54. Топология v4 = v3 на сетях с уточнённой детекцией ДХ (Task 45,
network_hh2.json: сплиты сблокированных домов по крышам/заборам + квартиры
многоэтажек). Дерево сетей не меняется — только потоки ДХ на узлах, поэтому
врезы зон книги v3 остаются валидными границами зон; медианы ОРШ и все
объёмы пересчитываются. Запуск: FTTH_NET_OVERRIDE=network_hh2.json.

Исходник: 46_topology_v3.py (автоматическая копия с заменами).

Указания пользователя (после подтверждения точности KMZ, шаг 42-43):
  1) «может быть ОРШ располагать ближе к центру секторов?» — да: точка стояния
     зонного ОРШ выбирается из узлов зоны как точный минимизатор стоимости
         cost(v) = g(v) + ff_z * D(v),
     где g(v) — распределительные волокна зоны при корне в v (та же формула
     модели F = max(8, ceil(1.25 x поток)); точный DP переноса корня: при
     смещении корня на одно ребро меняется только поток этого ребра),
     ff_z — фидерные волокна зоны, D(v) — кратчайший путь ЦУ->v. Состав зоны
     (врез) не меняется — перемещается только шкаф.
  2) «определять по возможности границу НП и ограничивать ею проектируемую
     сеть» — граница НП строится по морфологии застройки (шаг 46a: диски 175 м
     вокруг каждого ДХ + замыкание 250 м, внешний контур). Дорожный граф
     маршрутизации ОБРЕЗАЕТСЯ границей: фидерные трассы физически не могут
     покинуть населённый пункт.
  3) фидеры — кратчайшие пути Дейкстра (v2, шаг 44) — теперь в границе НП.

Расчёты:
  A) фиксированные врезы выпущенной книги + медианы (основной вариант);
  B) повторная жадная оптимизация врезов с экономикой медиан (чувствительность).
  Выбирается вариант с меньшим индексом стоимости (кабель + дропы + обор. +
  шкафы доп. ОРШ; коэффициенты шага 25/28).

Контроль:
  1) медиана не дороже вреза: cost(v*) <= cost(u) для каждой зоны;
  2) все узлы фидерных путей — внутри границы НП;
  3) v3 с медианами = врезам воспроизводит v2 (Σ F x L, допуск 1e-3 вол-м):
     обрезка графа границей не меняет кратчайшие пути (шаг 46a: 0 км вне);
  4) достижимость: все узлы дерева достижимы от ЦУ в обрезанном графе.

Выход: work/boq_decentral_data_v4.json (формат зеркалит v2 для шагов 30/34/37-40)
       work/topology_v4_summary.json (A/B, сдвиги ОРШ, граница)
"""
import json
import math
import importlib.util
from collections import defaultdict

import numpy as np
from scipy.sparse import csr_matrix
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

BASE = '/home/z/my-project'


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de29 = load_mod('de29', f'{BASE}/scripts/29_boq_decentral_calc.py')
de44 = load_mod('de44', f'{BASE}/scripts/44_feeder_shortest.py')

Tree = de28.Tree
ceilr, decompose, roundup01 = de28.ceilr, de28.decompose, de28.roundup01
STD_FIBERS = de28.STD_FIBERS
MIN_ZONE, FIBER_RESERVE, MIN_FIBERS = de28.MIN_ZONE, de28.FIBER_RESERVE, de28.MIN_FIBERS
ORSH_PORTS_ROW, ORSH_PORTS_ROW_ZONE = de28.ORSH_PORTS_ROW, de28.ORSH_PORTS_ROW_ZONE
S_MIN_REC = 15.0

OLD = json.load(open(f'{BASE}/work/boq_decentral_data_v3.json'))
OLD_BY = {v['key']: v for v in OLD['villages']}
ANA = {v['key']: v for v in json.load(open(f'{BASE}/work/v3_analysis.json'))['villages']}

# ================================================================= гео ==
def lon2tx(lon, z):
    return (lon + 180.0) / 360.0 * (1 << z)


def lat2ty(lat, z):
    la = math.radians(lat)
    return (1.0 - math.log(math.tan(la) + 1.0 / math.cos(la)) / math.pi) / 2.0 * (1 << z)


def tx2lon(x, z):
    return x / (1 << z) * 360.0 - 180.0


def ty2lat(y, z):
    y = y / (1 << z)
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))


GEO = json.load(open(f'{BASE}/work/mosaic_geo.json'))


def px_to_geo(key, x, y):
    """px мозаики -> WGS84, точный обратный Web Mercator z18 (валидация 42a: 0,2 м)."""
    g = GEO[key]
    gx = lon2tx(g['west'], 18) * 256.0 + x
    gy = lat2ty(g['north'], 18) * 256.0 + y
    return ty2lat(gy / 256.0, 18), tx2lon(gx / 256.0, 18)


def F_of(fl):
    return max(MIN_FIBERS, ceilr(FIBER_RESERVE * fl))


# ============================================================= деревня ===
class VillageV3:
    def __init__(self, v):
        self.v = v
        self.key = v['key']
        self.t = Tree(v)
        self.P, self.C, self.kdt, self.mpp = de44.build_graph(self.key)
        t = self.t

        # --- граница НП (морфология застройки, шаг 46a) ---
        ring = ANA[self.key]['boundary_poly_px']
        poly = Polygon(ring).buffer(0)
        assert poly.is_valid and poly.area > 0, f'{self.key}: некорректная граница НП'
        self.poly = poly
        ppoly = prep(poly)
        allowed = np.array([ppoly.covers(Point(p)) for p in self.P], bool)
        # допуск 2 px (0,8 м) — только для узлов, точно лежащих на контуре
        for i in np.nonzero(~allowed)[0]:
            if poly.distance(Point(self.P[i])) <= 2.0:
                allowed[i] = True
        self.allowed = allowed

        # --- обрезанный дорожный граф ---
        coo = self.C.tocoo()
        rows, cols, vals = [], [], []
        for r, c, val in zip(coo.row, coo.col, coo.data):
            if r < c and allowed[r] and allowed[c]:
                rows += [r, c]
                cols += [c, r]
                vals += [val, val]
        self.C_cl = csr_matrix((vals, (rows, cols)), shape=self.C.shape)

        # --- сопоставление узлов дерева с графом (как в v2) ---
        nodes = {t.root}
        for (p, ch, L) in t.edges:
            nodes.add(p)
            nodes.add(ch)
        nodes = list(nodes)
        d, i = self.kdt.query(np.array(nodes))
        bad = [(n, round(dd * self.mpp, 3)) for n, dd in zip(nodes, d) if dd * self.mpp > 0.05]
        assert not bad, f'{self.key}: узлы дерева вне графа: {bad[:3]}'
        self.idx = {n: int(ii) for n, ii in zip(nodes, i)}
        self.root_i = self.idx[t.root]

        # --- КОНТРОЛЬ 4: достижимость узлов дерева в обрезанном графе ---
        from scipy.sparse.csgraph import dijkstra, connected_components
        ncomp, labels = connected_components(self.C_cl, directed=False)
        root_lbl = labels[self.root_i]
        tree_lbls = set(labels[self.idx[n]] for n in nodes)
        assert tree_lbls == {root_lbl}, \
            f'{self.key}: {len(tree_lbls)} компонент обрезанного графа на дереве'

        # Дейкстра от ЦУ по обрезанному графу
        self.D, self.pred = dijkstra(self.C_cl, indices=self.root_i,
                                     return_predecessors=True)

        # статичные карты рёбер дерева (idx-пары)
        self.child_of = {}
        for (p, ch, L) in t.edges:
            k = self.ekey(self.idx[p], self.idx[ch])
            assert k not in self.child_of, f'{self.key}: коллизия рёбер {k}'
            self.child_of[k] = ch
        self._path_cache = {}

    def ekey(self, a, b):
        return (min(a, b), max(a, b))

    def L_of(self, a, b):
        return math.hypot(self.P[a][0] - self.P[b][0], self.P[a][1] - self.P[b][1]) * self.mpp

    def path_edges(self, z):
        """Рёбра кратчайшего пути ЦУ->z по обрезанному графу (граница НП)."""
        if z in self._path_cache:
            return self._path_cache[z]
        out = []
        cur = self.idx[z]
        guard = 0
        while cur != self.root_i and self.pred[cur] >= 0:
            p = int(self.pred[cur])
            out.append(self.ekey(cur, p))
            cur = p
            guard += 1
            assert guard < 10 ** 6, 'path_edges: цикл'
        assert cur == self.root_i, f'{self.key}: ЦУ недостижим из {z}'
        self._path_cache[z] = out
        return out

    # ------------------------------------------------------------ зоны ---
    def zone_sets(self, cuts):
        """Принадлежность узлов зонам: z -> set(узлов)."""
        zr, zone_dh, spl, df, _ = self.t.flows(cuts)
        by = defaultdict(set)
        for u in self.t.bfs:
            by[zr[u]].add(u)
        return zr, zone_dh, spl, df, by

    def zone_median(self, z, sub, dh_z, ff):
        """v* = argmin [ g(v) + ff x D(v) ] — точный DP переноса корня зоны."""
        t = self.t
        below = {}
        for u in reversed(t.bfs):
            if u not in sub:
                continue
            s = t.homes.get(u, 0)
            for c in t.children[u]:
                if c in sub:
                    s += below[c]
            below[u] = s
        g = {z: 0.0}
        for u in t.bfs:
            if u not in sub or u == z:
                continue
            p = t.parent[u]
            L = t.edge_len[(min(u, p), max(u, p))]
            g[u] = g[p] - F_of(below[u]) * L + F_of(dh_z - below[u]) * L
        best_v, best_c = z, None
        for v, gv in g.items():
            c = gv + ff * float(self.D[self.idx[v]])
            if best_c is None or c < best_c - 1e-9:
                best_v, best_c = v, c
        return best_v, best_c

    def medians_of(self, cuts, zr=None, zone_dh=None, spl=None, by=None):
        if zr is None:
            zr, zone_dh, spl, _, by = self.zone_sets(cuts)
        return {z: self.zone_median(z, by[z], zone_dh[z],
                                    ceilr(FIBER_RESERVE * spl[z]))[0]
                for z in cuts}

    # ------------------------------------------------------- раскладка ---
    def account_v3(self, cuts, medians=None):
        """Полная раскладка: ОРШ зон в медианах, фидеры Дейкстрой в границе."""
        t = self.t
        zr, zone_dh, spl, df, by = self.zone_sets(cuts)
        if medians is None:
            medians = self.medians_of(cuts, zr, zone_dh, spl, by)
        assert set(medians) == set(cuts)

        # распределительные потоки (по зонам, корень = медиана) + маршруты ДХ
        dist_flow = {}
        routes = []
        for zone in [t.root] + list(cuts):
            v_z = t.root if zone == t.root else medians[zone]
            sub = by[zone]
            par_v = {v_z: None}
            order_v = [v_z]
            qi = 0
            while qi < len(order_v):
                x = order_v[qi]
                qi += 1
                nbs = [c for c in t.children[x] if c in sub]
                px_ = t.parent[x]
                if px_ is not None and px_ in sub:
                    nbs.append(px_)
                for nb in nbs:
                    if nb not in par_v:
                        par_v[nb] = x
                        order_v.append(nb)
            below_v = {}
            dist_v = {v_z: 0.0}
            for x in reversed(order_v):
                s = t.homes.get(x, 0)
                for nb in [c for c in t.children[x] if c in sub] + \
                          ([t.parent[x]] if (t.parent[x] is not None and t.parent[x] in sub) else []):
                    if par_v.get(nb) == x:
                        s += below_v[nb]
                below_v[x] = s
            for x in order_v[1:]:
                p = par_v[x]
                e = self.ekey(self.idx[x], self.idx[p])
                dist_flow[e] = below_v[x]
                dist_v[x] = dist_v[p] + t.edge_len[(min(x, p), max(x, p))]
            for node, dh in t.homes.items():
                if node in sub:
                    routes.extend([dist_v[node]] * dh)

        # фидерные волокна на кратчайших путях (обрезанный граф)
        ffw = defaultdict(int)
        for z in cuts:
            ff = ceilr(FIBER_RESERVE * spl[z])
            for e in self.path_edges(medians[z]):
                ffw[e] += ff

        # КОНТРОЛЬ: внутренние рёбра зон покрыты потоками ровно один раз;
        # рёбра-«мостики» (родитель -> врез) не несут распределения (как в v1/v2:
        # потоки ДХ ниже вреза обнуляются на врезе) — им присваиваем поток 0
        cutset = set(cuts)
        cross = {e for e, ch in self.child_of.items() if ch in cutset}
        internal = set(dist_flow)
        assert internal.isdisjoint(cross), f'{self.key}: мостик попал во внутренние рёбра'
        assert internal | cross == set(self.child_of), \
            f'{self.key}: внутренние {len(internal)} + мостики {len(cross)} != дерево {len(self.child_of)}'
        for e in cross:
            dist_flow[e] = 0

        km_by_size = defaultdict(float)
        fiber_m = 0.0        # сырые волокна: Σ F x L (жадная оптимизация, контроль v2)
        fiber_cap_m = 0.0    # ёмкостные: Σ L x s по кабелям стандартных ёмкостей (метрика книги)
        cable_m = feeder_route_m = 0.0
        top_fibers = 0
        max_parallel = 0
        for e in set(self.child_of) | set(ffw):
            L = self.L_of(*e)
            if e in self.child_of:
                F = max(MIN_FIBERS, ceilr(FIBER_RESERVE * dist_flow.get(e, 0))
                        + ffw.get(e, 0))
            else:
                F = max(MIN_FIBERS, ffw[e])
            top_fibers = max(top_fibers, F)
            cables = decompose(F)
            max_parallel = max(max_parallel, len(cables))
            fiber_m += L * F
            for s in cables:
                km_by_size[s] += L / 1000.0
                cable_m += L
                fiber_cap_m += L * s
            if e in ffw:
                feeder_route_m += L
        # NB: fiber_m — сырые волокно-метры (совместимо с raw_fkm_v2);
        #     fiber_cap_m — волокно в кабелях стандартных ёмкостей (как в книге)

        routes.sort()
        return dict(zr=zr, zone_dh=zone_dh, spl=spl, df=df, by=by,
                    medians=medians, dist_flow=dist_flow, ffw=ffw,
                    km_by_size=km_by_size, fiber_m=fiber_m, fiber_cap_m=fiber_cap_m,
                    cable_km=cable_m / 1000.0,
                    feeder_route_km=feeder_route_m / 1000.0,
                    top_fibers=top_fibers, max_parallel=max_parallel,
                    routes=routes)

    # ------------------------------------------------------- жадный v3 ---
    def greedy_v3(self, s_min_km):
        cuts = []
        log = []
        while True:
            zr, zone_dh, spl, df, by = self.zone_sets(cuts)
            cur_med = self.medians_of(cuts, zr, zone_dh, spl, by)
            cur = self.account_v3(cuts, cur_med)['fiber_m']
            best_u, best_sav = None, 0.0
            cands = [u for u in self.t.coupler_nodes
                     if u != self.t.root and u not in cuts and df.get(u, 0) >= MIN_ZONE]
            for u in cands:
                zp = zr[u]
                # точные наборы зон для cuts+[u] (зона u = subtree(u) минус
                # вложенные врезы; зона zp сжимается на subtree(u))
                zr2, zone_dh2, spl2, df2, by2 = self.zone_sets(cuts + [u])
                med = dict(cur_med)
                if zp in med:
                    med.pop(zp)
                    med[zp] = self.zone_median(
                        zp, by2[zp], zone_dh2[zp],
                        ceilr(FIBER_RESERVE * ceilr(zone_dh2[zp] / de28.SPLIT_RATIO)))[0]
                med[u] = self.zone_median(
                    u, by2[u], zone_dh2[u],
                    ceilr(FIBER_RESERVE * ceilr(zone_dh2[u] / de28.SPLIT_RATIO)))[0]
                a = self.account_v3(cuts + [u], med)
                sav = (cur - a['fiber_m']) / 1000.0
                if sav > best_sav:
                    best_u, best_sav = u, sav
            if best_u is None or best_sav < s_min_km:
                break
            cuts.append(best_u)
            log.append(dict(node=best_u, sav_km=round(best_sav, 1)))
        return cuts, log


# ==================================================================== main =
def cost_index(mt, orsh_ports_total, orsh_total, k=de28.COST_COEFFS['cable_k']):
    """Индекс стоимости (как в шагах 25/28), у.е. = 1 км кабеля 8F."""
    C = de28.COST_COEFFS
    cable = sum(mt[f'cable_{s}'] * (s / 8.0) ** k for s in STD_FIBERS if mt.get(f'cable_{s}'))
    drop = mt['drop_cable_km'] * (2 / 8.0) ** k
    hw = dict(
        mufty=mt['mufty'] * C['mufta'],
        splitters=mt['splitters'] * C['spl64'],
        splices=mt['splices'] * C['splice'],
        conns=mt['fast_conn'] * C['conn'],
        orsh_ports=orsh_ports_total * C['orsh_port'],
        olt=mt['olt_ports'] * C['olt_port'],
        suspend=mt['suspend_kits'] * C['suspend'],
        pigtails=mt['pigtails'] * C['pigtail'],
    )
    boxes = (orsh_total - 6) * C['orsh_box']
    return dict(cable=cable, drop=drop, hw=hw, boxes=boxes,
                total=cable + drop + sum(hw.values()) + boxes)


def village_record(V, cuts, medians, A, log, chosen_tag):
    """Запись села в формате книги v2 (+ доп. поля v3)."""
    t = V.t
    key = V.key
    old = OLD_BY[key]
    zone_dh, spl = A['zone_dh'], A['spl']

    zinfo = [dict(
        root_dist_m=0.0, houses=zone_dh.get(t.root, 0),
        splitters=spl.get(t.root, 0), feeder_fibers=0,
        orsh_ports=next(p for p in ORSH_PORTS_ROW if p >= zone_dh.get(t.root, 0) * 1.1),
    )]
    zone_extra = []
    for z in cuts:
        v_z = medians[z]
        shift = math.hypot(v_z[0] - z[0], v_z[1] - z[1]) * V.mpp
        zinfo.append(dict(
            root_dist_m=round(float(V.D[V.idx[v_z]]), 1), houses=zone_dh[z],
            splitters=spl[z], feeder_fibers=ceilr(FIBER_RESERVE * spl[z]),
            orsh_ports=next(p for p in ORSH_PORTS_ROW_ZONE if p >= zone_dh[z] * 1.1),
        ))
        la, lo = px_to_geo(key, v_z[0], v_z[1])
        cu_la, cu_lo = px_to_geo(key, z[0], z[1])
        zone_extra.append(dict(
            zone='зонный ОРШ', orsh_px=[round(v_z[0], 1), round(v_z[1], 1)],
            orsh_lat=round(la, 6), orsh_lon=round(lo, 6),
            cut_px=[round(z[0], 1), round(z[1], 1)], cut_lat=round(cu_la, 6),
            cut_lon=round(cu_lo, 6), median_shift_m=round(shift, 0),
            orsh_kind='врез (=центр зоны)' if shift < 1.0 else 'медиана зоны (центр сектора)',
        ))
    # координаты корня (ЦУ)
    la, lo = px_to_geo(key, t.root[0], t.root[1])
    zones_geo = [dict(zinfo[0], zone='ЦУ (корневая)',
                      px=[round(t.root[0], 1), round(t.root[1], 1)],
                      lat=round(la, 6), lon=round(lo, 6),
                      orsh_kind='ЦУ — здание-якорь')]
    for zd, xe in zip(zinfo[1:], zone_extra):
        zones_geo.append(dict(zd, **xe, px=xe['orsh_px'], lat=xe['orsh_lat'],
                              lon=xe['orsh_lon']))

    km = A['km_by_size']
    cable_km = {str(s): roundup01(km.get(s, 0.0) * 1.1) for s in STD_FIBERS
                if km.get(s, 0.0) > 0}
    dh = t.dh_total
    routes = A['routes']
    r_old = t.layout(cuts)  # муфты/сварки — как в дереве (не зависят от медиан)
    m = dict(
        orsh=1 + len(cuts),
        splitters=r_old['splitters'], olt_ports=r_old['splitters'],
        pigtails=dh + 2 * r_old['splitters'],
        mufty=r_old['mufty'],
        drop_cable_km=roundup01(t.drop_km * 1.05),
        abonent_boxes=dh,
        fast_conn=ceilr(dh * 1.1),
        splices=r_old['splices'], kdzs=r_old['splices'],
        suspend_kits=math.ceil(A['cable_km'] * 30),
        drop_anchors=2 * dh, drop_fix=6 * dh,
        orsh_ports=sum(z['orsh_ports'] for z in zinfo),
    )
    m.update({f'cable_{s}': cable_km.get(str(s), 0.0) for s in STD_FIBERS})

    vv = dict(de29.VILLAGES_META[key])
    vv.update(dict(
        key=key, net=V.v['net'],
        dhx_served=dh, couplers=t.n_couplers, mufty=r_old['mufty'],
        feeder_km=round(sum(L for _, _, L in t.edges) / 1000.0, 2),
        drop_km=round(t.drop_km, 2),
        avg_drop_m=old['avg_drop_m'], max_drop_m=old['max_drop_m'],
        n_zones=len(cuts), orsh=1 + len(cuts),
        zones=zones_geo,
        fiber_km=round(A['fiber_cap_m'] / 1000.0, 1), total_cable_km=round(A['cable_km'], 3),
        cable_km=cable_km, cable_km_raw=round(A['cable_km'] * 1.1, 2),
        drop_cable_km=m['drop_cable_km'],
        orsh_ports=m['orsh_ports'], splitters64=r_old['splitters'],
        top_fibers=A['top_fibers'], max_parallel=A['max_parallel'],
        feeder_route_km=round(A['feeder_route_km'], 2),
        routes=dict(avg_m=round(sum(routes) / max(1, len(routes)), 1),
                    med_m=round(de28.pct(routes, 50), 1),
                    p90_m=round(de28.pct(routes, 90), 1),
                    max_m=round(routes[-1], 1) if routes else 0),
        cut_log=log,
        materials=m,
        feeder_model='v3: ОРШ в центре сектора (медиана дерева); фидер — кратчайший '
                     'путь Дейкстра по дорожному графу, обрезанному границей НП',
    ))
    return vv, m


def main():
    out_villages = []
    summary = []
    V2BOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v2.json'))
    V2_BY = {v['key']: v for v in V2BOOK['villages']}
    print(f"{'Село':<18}{'зон':>4}{'вол-км кн.':>11}{'v2':>8}{'v3':>8}"
          f"{'каб.км v3':>10}{'фид.трассы':>11}{'ср.маршр':>9}{'ОРШ сдв.':>9}")

    for v in de28.VILLAGES:
        key = v['key']
        V = VillageV3(v)
        t = V.t
        old = OLD_BY[key]
        cuts_book = [tuple(l['node']) for l in old['cut_log']]

        # --- КОНТРОЛЬ 3: медианы=врезам => v3 == v2 ---
        V2 = de44.VillageV2(v)
        fkm_v2 = V2.raw_fkm_v2(cuts_book, 'short')[0]
        a_ctrl = V.account_v3(cuts_book, {z: z for z in cuts_book})
        d_ctrl = abs(a_ctrl['fiber_m'] - fkm_v2)
        assert d_ctrl < 1e-3, f'{key}: v3(врезы) {a_ctrl["fiber_m"]} != v2 {fkm_v2}'

        # --- A: врезы книги + медианы ---
        medA = V.medians_of(cuts_book)
        A = V.account_v3(cuts_book, medA)

        # КОНТРОЛЬ 1: медиана не дороже вреза (точная стоимость вреза = g(z) + ff*D(z))
        for z in cuts_book:
            sub = A['by'][z]
            dh_z = A['zone_dh'][z]
            ff = ceilr(FIBER_RESERVE * A['spl'][z])
            below = {}
            for u in reversed(t.bfs):
                if u not in sub:
                    continue
                s = t.homes.get(u, 0)
                for c in t.children[u]:
                    if c in sub:
                        s += below[c]
                below[u] = s
            g_z = sum(F_of(below[u]) * t.edge_len[(min(u, t.parent[u]), max(u, t.parent[u]))]
                      for u in sub if u != z)
            c_cut = g_z + ff * float(V.D[V.idx[z]])
            _, c_med = V.zone_median(z, sub, dh_z, ff)
            assert c_med <= c_cut + 1e-6, \
                f'{key}: медиана дороже вреза ({c_med:.1f} > {c_cut:.1f})'

        # КОНТРОЛЬ 2: фидерные пути в границе НП
        for z in cuts_book:
            for e in V.path_edges(medA[z]):
                assert V.allowed[e[0]] and V.allowed[e[1]], f'{key}: фидер вне границы'

        # --- B: повторная жадная оптимизация с медианами ---
        cutsB, logB = V.greedy_v3(S_MIN_REC)
        if cutsB == cuts_book:
            B = A
            logB = old['cut_log']
        else:
            medB = V.medians_of(cutsB)
            B = V.account_v3(cutsB, medB)

        # --- выбор варианта по индексу стоимости ---
        recA, mtA = village_record(V, cuts_book, medA, A, old['cut_log'], 'A')
        recB, mtB = village_record(V, cutsB,
                                   B['medians'], B, logB, 'B')
        ciA = cost_index(mtA, recA['orsh_ports'], recA['orsh'])
        ciB = cost_index(mtB, recB['orsh_ports'], recB['orsh'])
        if ciB['total'] < ciA['total'] - 1e-9:
            chosen, ci, tag = recB, ciB, 'B (перекомпоновка зон)'
        else:
            chosen, ci, tag = recA, ciA, 'A (зоны книги)'

        out_villages.append(chosen)

        shifts = [z['median_shift_m'] for z in chosen['zones'][1:]]
        summary.append(dict(
            key=key, name=t.name, variant=tag,
            zones_book=list(map(list, cuts_book)), zones_B=[list(c) for c in cutsB],
            same=cutsB == cuts_book,
            fiber_km_book=old['fiber_km'], fiber_km_A=recA['fiber_km'],
            fiber_km_B=recB['fiber_km'],
            cable_A=recA['cable_km_raw'], cable_B=recB['cable_km_raw'],
            cost_A=round(ciA['total'], 1), cost_B=round(ciB['total'], 1),
            cost=dict(cable=round(ci['cable'], 1), drop=round(ci['drop'], 1),
                      hw=round(sum(ci['hw'].values()), 1), boxes=round(ci['boxes'], 1),
                      total=round(ci['total'], 1)),
            feeder_route_km=chosen['feeder_route_km'],
            routes=chosen['routes'],
            median_shift=dict(avg=round(sum(shifts) / max(1, len(shifts)), 0),
                              max=round(max(shifts), 0) if shifts else 0),
            zones=[dict(cut=z['cut_px'], orsh=z['orsh_px'], shift_m=z['median_shift_m'],
                        root_dist_m=zd['root_dist_m'], houses=zd['houses'])
                   for z, zd in zip(chosen['zones'][1:], chosen['zones'][1:])],
            ctrl_v3_eq_v2=round(d_ctrl, 6),
        ))

        d = 100 * (chosen['fiber_km'] - old['fiber_km']) / old['fiber_km'] if old['fiber_km'] else 0
        print(f"{t.name:<18}{chosen['n_zones']:>4}{old['fiber_km']:>11.1f}"
              f"{V2_BY[key]['fiber_km']:>8.1f}"
              f"{chosen['fiber_km']:>8.1f}{chosen['cable_km_raw']:>10.1f}"
              f"{chosen['feeder_route_km']:>8.1f} км{chosen['routes']['avg_m']:>9.0f}"
              f"{summary[-1]['median_shift']['avg']:>6.0f} м")

    # --- итоги ---
    tot = dict(
        dhx_served=sum(v['dhx_served'] for v in out_villages),
        dhx_excel=sum(v['dhx_excel'] for v in out_villages),
        couplers=sum(v['couplers'] for v in out_villages),
        mufty=sum(v['mufty'] for v in out_villages),
        n_zones=sum(v['n_zones'] for v in out_villages),
        orsh=sum(v['orsh'] for v in out_villages),
        feeder_km=round(sum(v['feeder_km'] for v in out_villages), 2),
        fiber_km=round(sum(v['fiber_km'] for v in out_villages), 1),
        cable_km_raw=round(sum(v['cable_km_raw'] for v in out_villages), 2),
        drop_km=round(sum(v['drop_km'] for v in out_villages), 2),
        drop_cable_km=round(sum(v['drop_cable_km'] for v in out_villages), 1),
        splitters64=sum(v['splitters64'] for v in out_villages),
        orsh_ports=sum(v['orsh_ports'] for v in out_villages),
        splices=sum(v['materials']['splices'] for v in out_villages),
        total_length_km=round(sum(v['cable_km_raw'] for v in out_villages)
                              + sum(v['drop_cable_km'] for v in out_villages), 1),
    )
    mat_tot = defaultdict(float)
    for v in out_villages:
        for k, val in v['materials'].items():
            mat_tot[k] = round(mat_tot.get(k, 0) + val, 1)

    data = dict(
        model=dict(
            scheme='D — децентрализованная: зонные ОРШ 1:64, единый узел OLT '
                   '(v3: граница НП + ОРШ в центре сектора + фидеры Дейкстрой)',
            s_min_km=S_MIN_REC, min_zone=MIN_ZONE,
            fiber_reserve=1.25, min_fibers=8, std_fibers=STD_FIBERS,
            cable_stock=1.10, drop_stock=1.05, suspend_per_km=30,
            drop_anchors_per_dh=2, drop_fix_per_dh=6, consum_stock=1.10,
            split_ratio=64,
            orsh_ports_row=[144, 288, 576, 864, 1152],
            orsh_ports_row_zone=ORSH_PORTS_ROW_ZONE,
            feeder_fibers='ceil(1.25 x сплиттеры зоны)',
            feeder_routing='v3: кратчайший путь ЦУ->ОРШ (Дейкстра) по дорожному графу, '
                           'ОБРЕЗАННОМУ границей НП (морфология застройки: диски 175 м '
                           'вокруг ДХ + замыкание 250 м); ОРШ стоит в центре сектора — '
                           'медиане дерева зоны (минимум g(v) + фидер x D(v)); на общих '
                           'с деревом участках волокна в одном кабеле, вне дерева — '
                           'отдельный кабель >= 8 волокон',
            note='Топология распределительной сети, муфты, дропы и состав зон — как в '
                 'выпущенной книге; ОРШ зон перенесены в центры секторов (медианы), '
                 'фидерные трассы — кратчайшие пути в границе НП. Межселённый '
                 'транспорт — за рамками расчёта.',
        ),
        villages=out_villages, totals=tot, materials_total=dict(mat_tot),
    )
    json.dump(data, open(f'{BASE}/work/boq_decentral_data_v4.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    v2t = V2BOOK['totals']
    js = dict(
        old_totals=OLD['totals'], v2_totals=v2t, v3_totals=tot,
        villages=summary,
    )
    json.dump(js, open(f'{BASE}/work/topology_v4_summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('\nИТОГО (v3):')
    for k in ('dhx_served', 'n_zones', 'orsh', 'feeder_km', 'fiber_km', 'cable_km_raw',
              'drop_km', 'drop_cable_km', 'total_length_km', 'mufty', 'splitters64',
              'orsh_ports', 'splices'):
        print(f"  {k:>16}: {tot[k]}  (книга {OLD['totals'][k]}, v2 {v2t[k]})")
    print('\nСохранено: work/boq_decentral_data_v4.json, work/topology_v4_summary.json')


if __name__ == '__main__':
    main()
