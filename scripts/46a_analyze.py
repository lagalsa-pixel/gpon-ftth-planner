# -*- coding: utf-8 -*-
"""
Шаг 46a. Анализ проектных материалов перед оптимизацией топологии (v3).

Вопросы пользователя:
  1) ОРШ располагать ближе к центру секторов?
  2) Определять границу НП и ограничивать ею проектируемую сеть.

Что считается:
  A. ГРАНИЦА НП: морфология застройки — объединение дисков радиуса R_BOUND вокруг
     каждого ДХ + замыкание (closing) для слияния кластеров и заполнения бухт;
     внешний контур = граница населённого пункта (внутренние поля — внутри НП).
  B. СЕТЬ vs ГРАНИЦА: доля рёбер дерева (магистраль) вне границы; муфты вне
     границы; фидерные трассы v2 (Дейкстра по ПОЛНОМУ графу) вне границы.
  C. ОРШ vs ЦЕНТР ЗОНЫ: для каждой зоны — смещение узла вреза от взвешенного
     центроида домов зоны; потенциал экономии от переноса ОРШ в медиану дерева
     (точный пересчёт g(v) по формуле волокон модели, без фидерного члена).

Выход: work/v3_analysis.json + консольный отчёт.
"""
import json
import math
import importlib.util
from collections import defaultdict

from shapely.geometry import Point, shape
from shapely.ops import unary_union

BASE = '/home/z/my-project'


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


de28 = load_mod('de28', f'{BASE}/scripts/28_decentral_explore.py')
de44 = load_mod('de44', f'{BASE}/scripts/44_feeder_shortest.py')

OLD = json.load(open(f'{BASE}/work/boq_decentral_data.json'))
OLD_BY = {v['key']: v for v in OLD['villages']}

R_BOUND_M = 175.0      # диск вокруг ДХ
CLOSING_M = 250.0      # замыкание: dilate + erode (слияние кластеров <= 500 м)
MIN_CLUSTER_HH = 8     # компонент границы с < 8 ДХ отбрасывается


# ================================================================ граница ===
def boundary_polygon(hhs, mpp, r_bound_m=None, closing_m=None):
    """Граница НП (px мозаики): объединение дисков ДХ + closing, без дыр."""
    r_bound_m = r_bound_m or R_BOUND_M
    closing_m = closing_m if closing_m is not None else CLOSING_M
    r_px = r_bound_m / mpp
    disks = [Point(h['cx'], h['cy']).buffer(r_px, 6) for h in hhs]
    A = unary_union(disks)
    # компоненты до замыкания — статистика кластеров
    def comps_of(g):
        return list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    pre = comps_of(A)
    # closing: слияние кластеров, заполнение бухт; затем только внешний контур
    c_px = closing_m / mpp
    B = A.buffer(c_px).buffer(-c_px)
    # отбросить микрокомпоненты (одиночные выселки < MIN_CLUSTER_HH ДХ)
    kept, dropped = [], []
    for comp in comps_of(B):
        n_hh = sum(1 for h in hhs if comp.covers(Point(h['cx'], h['cy'])))
        (kept if n_hh >= MIN_CLUSTER_HH else dropped).append((comp, n_hh))
    if kept:
        B = unary_union([c for c, _ in kept])
    # дыры (внутренние незасторенные поля) — считаем внутри НП: берём внешний контур
    ext = []
    for comp in comps_of(B):
        ext.append(comp.buffer(0))
    B = unary_union(ext)
    holes_filled = B
    # финальный полигон
    P = holes_filled
    hh_in = sum(1 for h in hhs if P.covers(Point(h['cx'], h['cy'])))
    return P, hh_in, dict(pre_components=len(pre),
                          kept=[n for _, n in kept], dropped=[n for _, n in dropped])


def poly_stats_m(P, mpp):
    return dict(area_km2=round(P.area * mpp * mpp / 1e6, 2),
                bounds_m=[round(c * mpp, 0) for c in P.bounds])


# ================================================================== main ===
def main():
    out = dict(r_bound_m=R_BOUND_M, closing_m=CLOSING_M, villages=[])

    print('=' * 112)
    print('A+B. ГРАНИЦА НП (морфология застройки) и текущая сеть относительно границы')
    print('=' * 112)
    print(f"{'Село':<18}{'ДХ':>5}{'внутри':>7}{'кластеры(ДХ)':>22}{'S, км2':>8}"
          f"{'дерево вне':>11}{'%':>5}{'муфт вне':>9}{'фидер v2 вне':>13}")

    for v in de28.VILLAGES:
        key = v['key']
        rec = dict(key=key, name=v['name'])

        hhs = json.load(open(f'{BASE}/work/{key}/households.json'))
        geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
        mpp = geo['mpp']

        # --- A. граница ---
        P, hh_in, cinfo = boundary_polygon(hhs, mpp)
        rec['boundary'] = poly_stats_m(P, mpp)
        rec['boundary'].update(hh_total=len(hhs), hh_inside=hh_in,
                               clusters=cinfo['kept'], dropped=cinfo['dropped'])
        # сохранить границу (упрощённый полигон) для шагов 46-47
        simp = P.simplify(2.0)
        rec['boundary_poly_px'] = [list(c) for c in simp.exterior.coords] if simp.geom_type == 'Polygon' else None
        if simp.geom_type == 'MultiPolygon':
            rec['boundary_poly_px'] = [list(c) for g in simp.geoms for c in g.exterior.coords]

        # --- B. текущая сеть vs граница ---
        net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
        tree_out_m = 0.0
        tree_tot_m = 0.0
        for e in net['feeder_edges']:
            L = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * mpp
            mx, my = (e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2
            tree_tot_m += L
            if not P.covers(Point(mx, my)):
                tree_out_m += L
        # та же проверка для более тесной границы (R=100 м, closing 150 м)
        P_tight, hh_in_t, _ = boundary_polygon(hhs, mpp, r_bound_m=100.0, closing_m=150.0)
        tree_out_tight = 0.0
        for e in net['feeder_edges']:
            mx, my = (e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2
            if not P_tight.covers(Point(mx, my)):
                tree_out_tight += math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) * mpp
        coup_out = sum(1 for c in net['couplers']
                       if not P.covers(Point(c['x'], c['y'])))

        # --- фидерные трассы v2 (Дейкстра по полному графу) vs граница ---
        V = de44.VillageV2(v)
        t = V.t
        cuts = [tuple(l['node']) for l in OLD_BY[key]['cut_log']]
        feed_out_m = 0.0
        feed_tot_m = 0.0
        for z in cuts:
            for e in V.path_edges(z, 'short'):
                a, b = V.P[e[0]], V.P[e[1]]
                L = math.hypot(b[0] - a[0], b[1] - a[1]) * mpp
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                feed_tot_m += L
                if not P.covers(Point(mx, my)):
                    feed_out_m += L
        rec['network_vs_boundary'] = dict(
            tree_km=round(tree_tot_m / 1000, 2),
            tree_out_km=round(tree_out_m / 1000, 2),
            tree_out_pct=round(100 * tree_out_m / max(tree_tot_m, 1e-9), 1),
            couplers_out=coup_out,
            feeder_v2_km=round(feed_tot_m / 1000, 2),
            feeder_v2_out_km=round(feed_out_m / 1000, 2),
            feeder_v2_out_pct=round(100 * feed_out_m / max(feed_tot_m, 1e-9), 1),
            tree_out_tight_km=round(tree_out_tight / 1000, 2),
        )

        # --- C. ОРШ vs центр зоны (зона = узлы с zr[u]==z, без вложенных врезов) ---
        zr, zone_dh, spl, df, _ = t.flows(cuts)
        zones_info = []
        for z in cuts:
            sub_set = {u for u in t.bfs if zr[u] == z}
            hx = hy = hd = 0.0
            dh_z = 0
            for node, dh in t.homes.items():
                if node in sub_set:
                    hx += node[0] * dh; hy += node[1] * dh; hd += dh; dh_z += dh
            if hd == 0:
                continue
            cx, cy = hx / hd, hy / hd
            offset = math.hypot(z[0] - cx, z[1] - cy) * mpp

            # медиана дерева: точный DP g(v) по формуле волокон
            def F(fl):
                return max(de28.MIN_FIBERS, de28.ceilr(de28.FIBER_RESERVE * fl))
            g = {z: 0.0}
            for u in t.bfs:
                if u not in sub_set or u == z:
                    continue
                p = t.parent[u]
                e = (min(u, p), max(u, p))
                L = t.edge_len[e]
                # поток на ребре при корне z: ДХ под u внутри зоны
                below = 0
                stack2 = [u]
                while stack2:
                    w = stack2.pop()
                    below += t.homes.get(w, 0)
                    stack2.extend(c for c in t.children[w] if c in sub_set)
                g[u] = g[p] - F(below) * L + F(dh_z - below) * L
            best_v = min(g, key=g.get)
            sav_km = (g[z] - g[best_v]) / 1000.0
            zones_info.append(dict(
                cut=[round(z[0], 1), round(z[1], 1)],
                houses=dh_z,
                centroid_off_m=round(offset, 0),
                median=[round(best_v[0], 1), round(best_v[1], 1)],
                median_shift_m=round(math.hypot(best_v[0] - z[0], best_v[1] - z[1]) * mpp, 0),
                dist_saving_km=round(sav_km, 2),
            ))
        rec['zones_orsh'] = zones_info

        out['villages'].append(rec)
        nb = rec['network_vs_boundary']
        cl = ','.join(str(x) for x in cinfo['kept']) or '-'
        print(f"{v['name']:<18}{len(hhs):>5}{hh_in:>7}{cl:>22}{rec['boundary']['area_km2']:>8}"
              f"{nb['tree_out_km']:>8} км{nb['tree_out_pct']:>5}%{coup_out:>9}"
              f"{nb['feeder_v2_out_km']:>9} км/{nb['feeder_v2_out_pct']}%")

    # --- сводка по ОРШ ---
    print()
    print('=' * 112)
    print('C. ОРШ vs ЦЕНТР ЗОНЫ (смещение вреза от центроида домов; потенциал переноса в медиану)')
    print('=' * 112)
    print(f"{'Село':<18}{'зона':>6}{'ДХ':>5}{'смещ. от центроида':>19}{'перенос в медиану':>18}"
          f"{'экономия вол-км':>16}")
    tot_sav = 0.0
    n_moved = 0
    for rec in out['villages']:
        for i, z in enumerate(rec['zones_orsh']):
            tot_sav += z['dist_saving_km']
            if z['median_shift_m'] > 1:
                n_moved += 1
            print(f"{rec['name']:<18}{i + 1:>6}{z['houses']:>5}"
                  f"{z['centroid_off_m']:>13.0f} м{z['median_shift_m']:>13.0f} м"
                  f"{z['dist_saving_km']:>13.2f}")
    print(f"\n  ИТОГО зон с переносом: {n_moved}; суммарный потенциал (только распределение,"
          f" без фидеров): {tot_sav:.1f} волокно-км из {OLD['totals']['fiber_km']}")

    json.dump(out, open(f'{BASE}/work/v3_analysis.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nСохранено: work/v3_analysis.json')


if __name__ == '__main__':
    main()
