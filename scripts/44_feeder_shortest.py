# -*- coding: utf-8 -*-
"""
Шаг 44. Исправленная логика прокладки фидерных трасс (схема D).

Проблема (шаг 43, с. Пригородное, ОРШ-2): путь ЦУ -> зонный ОРШ внутри
дерева распределения (приближение дерева Штейнера — минимум СУММАРНОЙ длины
сети) оказался 1313,6 м при кратчайшем пути по улицам 683,9 м (вдвое дольше;
маршрут пользователя в Google Earth совпал с кратчайшим).

Исправление: фидер ЦУ -> зонный ОРШ — связь «точка-точка» — прокладывается
по КРАТЧАЙШЕМУ пути ПОЛНОГО дорожного графа (Дейкстра; тот же граф, по
которому строилось дерево в шаге 06). Фидерные волокна
ceil(1,25 x сплиттеры зоны) учитываются на рёбрах кратчайшего пути:
  - общие с деревом участки: едут в одном кабеле,
    F = max(8, ceil(1,25 x ДХ-поток) + фидерные волокна);
  - участки вне дерева: отдельный кабель F = max(8, фидерные волокна).
Распределительное дерево, муфты, дропы и СОСТАВ ЗОН (врезы) — без изменений.

Два расчёта:
  A) фиксированные врезы (= выпущенным карте/BoQ) — основная поправка;
  B) повторная жадная оптимизация врезов с новой экономикой — чувствительность.

Контроль:
  1) воспроизведение старой модели: fkm_v2 с фидерами ПО ДЕРЕВУ == Tree.raw_fkm;
  2) инвариант: кратчайший путь <= пути в дереве для каждого вреза;
  3) воспроизведение врезов: partition_greedy(15) == cut_log выпущенной книги.

Выход: work/boq_decentral_data_v2.json (A; схема зеркалит boq_decentral_data.json)
       work/feeder_v2_summary.json (сравнение A/B со старой моделью)
"""
import json
import math
import importlib.util
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

BASE = '/home/z/my-project'


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de29 = load_mod('de29', f'{BASE}/scripts/29_boq_decentral_calc.py')

Tree = de28.Tree
ceilr, decompose, roundup01 = de28.ceilr, de28.decompose, de28.roundup01
STD_FIBERS = de28.STD_FIBERS
MIN_ZONE, FIBER_RESERVE, MIN_FIBERS = de28.MIN_ZONE, de28.FIBER_RESERVE, de28.MIN_FIBERS
ORSH_PORTS_ROW, ORSH_PORTS_ROW_ZONE = de28.ORSH_PORTS_ROW, de28.ORSH_PORTS_ROW_ZONE
S_MIN_REC = 15.0

OLD = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
OLD_BY = {v['key']: v for v in OLD['villages']}


# ================================================== дорожный граф (шаг 06) ==
def build_graph(key):
    """Полный дорожный граф OSM — детерминированное воспроизведение шага 06
    (та же плотизация 4 м, те же ключи узлов round(x,1), сырые координаты)."""
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
    osm = json.load(open(f'{BASE}/work/{key}/osm.json'))
    mpp, west, north = geo['mpp'], geo['west'], geo['north']

    def g2p(la, lo):
        return ((lo - west) * (111320 * math.cos(math.radians(la))) / mpp,
                (north - la) * 111320 / mpp)

    pts, idx, edges = [], {}, []

    def add_node(x, y):
        k = (round(x, 1), round(y, 1))
        i = idx.get(k)
        if i is None:
            i = len(pts)
            pts.append((x, y))
            idx[k] = i
        return i

    mstep = 4.0
    W, H = geo['W'], geo['H']
    for r in osm['roads']:
        pl = [g2p(la, lo) for la, lo in r['pts']]
        if all(p[0] < -200 or p[0] > W + 200 or p[1] < -200 or p[1] > H + 200 for p in pl):
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
                d = math.hypot(pts[cur][0] - pts[prev][0],
                               pts[cur][1] - pts[prev][1]) * mpp
                if d > 0.05:
                    edges.append((prev, cur, d))
            prev = cur

    P = np.array(pts)
    rows, cols, vals = [], [], []
    for (u, w, l) in edges:
        rows += [u, w]; cols += [w, u]; vals += [l, l]
    C = csr_matrix((vals, (rows, cols)), shape=(len(P), len(P)))
    return P, C, cKDTree(P), mpp


# ============================================================ деревня v2 ===
class VillageV2:
    def __init__(self, v):
        self.v = v
        self.key = v['key']
        self.t = Tree(v)
        self.P, self.C, self.kdt, self.mpp = build_graph(self.key)

        # сопоставление узлов дерева (nkey, round 2) -> индексы графа
        nodes = {self.t.root}
        for (p, ch, L) in self.t.edges:
            nodes.add(p); nodes.add(ch)
        nodes = list(nodes)
        d, i = self.kdt.query(np.array(nodes))
        bad = [(n, round(dd * self.mpp, 3)) for n, dd in zip(nodes, d) if dd * self.mpp > 0.05]
        assert not bad, f'{self.key}: узлы дерева вне графа: {bad[:3]}'
        self.idx = {n: int(ii) for n, ii in zip(nodes, i)}
        self.root_i = self.idx[self.t.root]

        # Дейкстра от ЦУ по ПОЛНОМУ графу
        self.D, self.pred = dijkstra(self.C, indices=self.root_i, return_predecessors=True)

        # статичная карта: ребро дерева (idx-key) -> ребёнок (nkey, носитель ДХ-потока)
        self.child_of = {}
        for (p, ch, L) in self.t.edges:
            k = self.ekey(self.idx[p], self.idx[ch])
            assert k not in self.child_of, f'{self.key}: коллизия рёбер дерева {k}'
            self.child_of[k] = ch

        self._path_cache = {}

    def ekey(self, a, b):
        return (min(a, b), max(a, b))

    def L_of(self, a, b):
        return math.hypot(self.P[a][0] - self.P[b][0], self.P[a][1] - self.P[b][1]) * self.mpp

    def path_edges(self, z, mode='short'):
        """Рёбра маршрута ЦУ->z: 'short' — кратчайший путь (Дейкстра),
        'tree' — путь внутри дерева распределения (старая логика)."""
        ck = (z, mode)
        if ck in self._path_cache:
            return self._path_cache[ck]
        out = []
        if mode == 'short':
            cur = self.idx[z]
            while cur != self.root_i and self.pred[cur] >= 0:
                p = int(self.pred[cur])
                out.append(self.ekey(cur, p))
                cur = p
        else:
            u = z
            while self.t.parent[u] is not None:
                p = self.t.parent[u]
                out.append(self.ekey(self.idx[u], self.idx[p]))
                u = p
        self._path_cache[ck] = out
        return out

    # ------------------------------------------------------------ расчёт --
    def _flows_and_ffw(self, cuts, mode):
        """ДХ-потоки дерева + фидерные волокна на рёбрах маршрутов."""
        zr, zone_dh, spl, df, _ = self.t.flows(cuts)
        ffw = defaultdict(int)
        for z in cuts:
            ff = ceilr(FIBER_RESERVE * spl[z])
            for e in self.path_edges(z, mode):
                ffw[e] += ff
        return zr, zone_dh, spl, df, ffw

    def _edge_iter(self, cuts, mode):
        """Генератор (ребро, длина_м, F_волокон) по дереву + фидерным маршрутам."""
        _, _, spl, df, ffw = self._flows_and_ffw(cuts, mode)
        for e in set(self.child_of) | set(ffw):
            L = self.L_of(*e)
            if e in self.child_of:
                F = max(MIN_FIBERS, ceilr(FIBER_RESERVE * df.get(self.child_of[e], 0))
                        + ffw.get(e, 0))
            else:
                F = max(MIN_FIBERS, ffw[e])
            yield e, L, F

    def raw_fkm_v2(self, cuts, mode='short'):
        """Σ F x L (волокно-м) — для жадной оптимизации; + df для кандидатов."""
        _, _, _, df, _ = self._flows_and_ffw(cuts, mode)
        fkm = sum(F * L for _, L, F in self._edge_iter(cuts, mode))
        return fkm, df

    def account(self, cuts, mode='short'):
        """Полная раскладка: волокно-км, кабель-км по ёмкостям, фидерные трассы."""
        zr, zone_dh, spl, df, ffw = self._flows_and_ffw(cuts, mode)
        km_by_size = defaultdict(float)
        fiber_km = cable_km = feeder_route_km = 0.0
        top_fibers = 0
        max_parallel = 0
        for e, L, F in self._edge_iter(cuts, mode):
            top_fibers = max(top_fibers, F)
            cables = decompose(F)
            max_parallel = max(max_parallel, len(cables))
            for s in cables:
                km_by_size[s] += L / 1000.0
                cable_km += L / 1000.0
                fiber_km += L / 1000.0 * s
            if e in ffw:
                feeder_route_km += L / 1000.0
        return dict(zr=zr, zone_dh=zone_dh, spl=spl, df=df, ffw=ffw,
                    km_by_size=km_by_size, fiber_km=fiber_km, cable_km=cable_km,
                    feeder_route_km=feeder_route_km, top_fibers=top_fibers,
                    max_parallel=max_parallel)

    def greedy_v2(self, s_min_km, mode='short'):
        """Жадные врезы по маржинальной экономии волокно-км (новая экономика)."""
        cuts = []
        cur, df = self.raw_fkm_v2(cuts, mode)
        log = []
        while True:
            best_u, best_sav = None, 0.0
            cands = [u for u in self.t.coupler_nodes
                     if u != self.t.root and u not in cuts and df.get(u, 0) >= MIN_ZONE]
            for u in cands:
                fkm_new, df_new = self.raw_fkm_v2(cuts + [u], mode)
                sav = (cur - fkm_new) / 1000.0
                if sav > best_sav:
                    best_u, best_sav = u, sav
            if best_u is None or best_sav < s_min_km:
                break
            cuts.append(best_u)
            log.append(dict(node=best_u, sav_km=round(best_sav, 1)))
            cur, df = self.raw_fkm_v2(cuts, mode)
        return cuts, log


# ==================================================================== main =
def main():
    out_villages = []
    summary = []
    print(f"{'Село':<18}{'зон':>4}{'вол-км стар':>12}{'нов':>8}{'Δ%':>6}"
          f"{'кабель стар':>12}{'нов':>8}{'Δ%':>6}{'фидерные трассы':>20}")

    for v in de28.VILLAGES:
        key = v['key']
        V = VillageV2(v)
        t = V.t
        old = OLD_BY[key]

        # врезы выпущенной книги
        cuts = [tuple(l['node']) for l in old['cut_log']]

        # --- КОНТРОЛЬ 1: старая модель воспроизводится (фидеры по дереву) ---
        fkm_tree_mode, _ = V.raw_fkm_v2(cuts, mode='tree')
        fkm_old_model, _ = t.raw_fkm(cuts)
        assert abs(fkm_tree_mode - fkm_old_model) < 1e-3, \
            f'{key}: fkm дерево {fkm_tree_mode} != старая модель {fkm_old_model}'

        # --- КОНТРОЛЬ 2: кратчайший <= пути в дереве ---
        for z in cuts:
            ds, dt_ = V.D[V.idx[z]], t.dist[z]
            assert ds <= dt_ + 0.01, f'{key}: кратчайший {ds} > дерево {dt_}'

        # --- КОНТРОЛЬ 3: состав зон воспроизводится ---
        cuts_g, _ = t.partition_greedy(S_MIN_REC)
        assert cuts_g == cuts, f'{key}: greedy != cut_log'

        # --- A: фиксированные врезы, фидеры по кратчайшим путям ---
        A = V.account(cuts, 'short')
        zone_dh, spl = A['zone_dh'], A['spl']

        zinfo = [dict(
            root_dist_m=0.0, houses=zone_dh.get(t.root, 0),
            splitters=spl.get(t.root, 0), feeder_fibers=0,
            orsh_ports=next(p for p in ORSH_PORTS_ROW if p >= zone_dh.get(t.root, 0) * 1.1),
        )]
        for z in cuts:
            zinfo.append(dict(
                root_dist_m=round(float(V.D[V.idx[z]]), 1), houses=zone_dh[z],
                splitters=spl[z], feeder_fibers=ceilr(FIBER_RESERVE * spl[z]),
                orsh_ports=next(p for p in ORSH_PORTS_ROW_ZONE if p >= zone_dh[z] * 1.1),
            ))

        # маршруты ДХ->свой ОРШ и пр. — из layout() дерева (не зависят от фидеров)
        r_old = t.layout(cuts)

        # геокоординаты зон (аффинная привязка по якорю — как в шаге 29)
        net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
        ax, ay = net['anchor']['x'], net['anchor']['y']
        alat, alon = net['anchor']['lat'], net['anchor']['lon']
        mlat = -t.mpp / 110574.0
        mlon = t.mpp / (111320.0 * math.cos(math.radians(alat)))
        zones_geo = []
        for z, zdata in zip([t.root] + list(cuts), zinfo):
            zx, zy = z
            zones_geo.append(dict(
                **zdata,
                zone='ЦУ (корневая)' if z == t.root else 'зонный ОРШ',
                px=[round(zx, 1), round(zy, 1)],
                lat=round(alat + (zy - ay) * mlat, 6),
                lon=round(alon + (zx - ax) * mlon, 6),
            ))

        km = A['km_by_size']
        cable_km = {str(s): roundup01(km.get(s, 0.0) * 1.1) for s in STD_FIBERS
                    if km.get(s, 0.0) > 0}
        dh = t.dh_total
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
            key=key, net=v['net'],
            dhx_served=dh, couplers=t.n_couplers, mufty=r_old['mufty'],
            feeder_km=round(sum(L for _, _, L in t.edges) / 1000.0, 2),
            drop_km=round(t.drop_km, 2),
            avg_drop_m=old['avg_drop_m'], max_drop_m=old['max_drop_m'],
            n_zones=len(cuts), orsh=1 + len(cuts),
            zones=zones_geo,
            fiber_km=round(A['fiber_km'], 1), total_cable_km=round(A['cable_km'], 3),
            cable_km=cable_km, cable_km_raw=round(A['cable_km'] * 1.1, 2),
            drop_cable_km=m['drop_cable_km'],
            orsh_ports=m['orsh_ports'], splitters64=r_old['splitters'],
            top_fibers=A['top_fibers'], max_parallel=A['max_parallel'],
            feeder_route_km=round(A['feeder_route_km'], 2),
            routes=r_old['routes'],
            cut_log=old['cut_log'],
            materials=m,
            feeder_model='v2: кратчайший путь Дейкстра по дорожному графу',
        ))
        out_villages.append(vv)

        # --- B: повторная оптимизация врезов с новой экономикой ---
        cutsB, logB = V.greedy_v2(S_MIN_REC, 'short')
        if cutsB == cuts:
            rB = dict(fiber_km=round(A['fiber_km'], 1),
                      cable_km_raw=round(A['cable_km'] * 1.1, 2),
                      n_zones=len(cuts))
        else:
            B = V.account(cutsB, 'short')
            rB = dict(fiber_km=round(B['fiber_km'], 1),
                      cable_km_raw=round(B['cable_km'] * 1.1, 2),
                      n_zones=len(cutsB))
        same = 'те же' if cutsB == cuts else 'ИЗМЕНИЛИСЬ'

        # --- сводка ---
        s = dict(
            key=key,
            root_dist_old=[z['root_dist_m'] for z in old['zones']],
            root_dist_new=[z['root_dist_m'] for z in zones_geo],
            fiber_km_old=old['fiber_km'], fiber_km_new=vv['fiber_km'],
            cable_km_raw_old=old['cable_km_raw'], cable_km_raw_new=vv['cable_km_raw'],
            feeder_route_km_old=old['feeder_route_km'],
            feeder_route_km_new=vv['feeder_route_km'],
            km_by_size_old=old['cable_km'], km_by_size_new=cable_km,
            reopt=dict(same_zones=same, n_zones=rB['n_zones'],
                       fiber_km=rB['fiber_km'], cable_km_raw=rB['cable_km_raw'],
                       cuts=[[round(c[0], 2), round(c[1], 2)] for c in cutsB]),
        )
        summary.append(s)

        d_fib = 100 * (vv['fiber_km'] - old['fiber_km']) / old['fiber_km']
        d_cab = 100 * (vv['cable_km_raw'] - old['cable_km_raw']) / old['cable_km_raw']
        print(f"{de29.VILLAGES_META[key]['name']:<18}{len(cuts):>4}"
              f"{old['fiber_km']:>12.1f}{vv['fiber_km']:>8.1f}{d_fib:>+6.1f}"
              f"{old['cable_km_raw']:>12.1f}{vv['cable_km_raw']:>8.1f}{d_cab:>+6.1f}"
              f"{old['feeder_route_km']:>12.1f} -> {vv['feeder_route_km']:.1f} км"
              f"  (B: зон {rB['n_zones']}, {same})")

    # --- итоги (как в шаге 29) ---
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
                   '(v2: фидеры по кратчайшим путям)',
            s_min_km=S_MIN_REC, min_zone=MIN_ZONE,
            fiber_reserve=1.25, min_fibers=8, std_fibers=STD_FIBERS,
            cable_stock=1.10, drop_stock=1.05, suspend_per_km=30,
            drop_anchors_per_dh=2, drop_fix_per_dh=6, consum_stock=1.10,
            split_ratio=64,
            orsh_ports_row=[144, 288, 576, 864, 1152],
            orsh_ports_row_zone=ORSH_PORTS_ROW_ZONE,
            feeder_fibers='ceil(1.25 x сплиттеры зоны)',
            feeder_routing='v2: кратчайший путь ЦУ->ОРШ по дорожному графу (Дейкстра); '
                           'на общих с деревом участках — в одном кабеле, вне дерева — '
                           'отдельный кабель >= 8 волокон',
            note='Топология распределительной сети, муфты, дропы и состав зон — без '
                 'изменений (как в выпущенной книге); исправлена только прокладка '
                 'фидерных трасс ЦУ->зонные ОРШ (шаг 43: путь в дереве мог быть вдвое '
                 'длиннее кратчайшего). Межселённый транспорт — за рамками расчёта.',
        ),
        villages=out_villages, totals=tot, materials_total=dict(mat_tot),
    )
    json.dump(data, open(f'{BASE}/work/boq_decentral_data_v2.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    js = dict(
        old_totals=OLD['totals'], new_totals=tot,
        reopt=dict(n_zones=sum(s['reopt']['n_zones'] for s in summary),
                   changed=[s['key'] for s in summary if s['reopt']['same_zones'] != 'те же']),
        villages=summary,
    )
    json.dump(js, open(f'{BASE}/work/feeder_v2_summary.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('\nИТОГО (v2, фиксированные зоны):')
    for k in ('dhx_served', 'n_zones', 'orsh', 'feeder_km', 'fiber_km', 'cable_km_raw',
              'drop_km', 'drop_cable_km', 'total_length_km', 'mufty', 'splitters64',
              'orsh_ports', 'splices'):
        o, n_ = OLD['totals'][k], tot[k]
        mark = '  (без изменений)' if o == n_ else f'  (было {o})'
        print(f"  {k:>16}: {n_}{mark}")
    print('\nСохранено: work/boq_decentral_data_v2.json, work/feeder_v2_summary.json')


if __name__ == '__main__':
    main()
