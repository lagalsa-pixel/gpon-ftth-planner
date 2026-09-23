#!/usr/bin/env python3
"""Проектирование FTTH (GPON, каскад 1x4 + 1x16 = 1:64) для 6 СНП ВКО
с реальной прокладкой кабелей по улично-дорожной сети OSM.

Архитектура на село:
- OLT (узел доступа) в центре села, взвешенном по абонентам
- PON-порт -> магистральный кабель -> муфта М1 (сплиттер 1x4)
- от М1 -> распределительный кабель -> бокс зоны (сплиттер 1x16)
- от бокса зоны -> индивидуальные абонентские вводы (дроп-кабель 2 волокна)
  к каждому домохозяйству (по улицам + воздушный ввод ~15 м)

Зона = <=12 домохозяйств (загрузка сплиттера <=75%, резерв портов на развитие).
PON-группа = <=4 зоны (одна М1, один PON-порт, до 48 абонентов).

Маршруты — кратчайшие пути по графу улиц (Dijkstra). Домохозяйства — из
scripts/households/<key>_numbered.geojson (Task 3). Дороги — scripts/osm_roads/<key>.json.

Выход: scripts/ftth_design/<key>.json

Использование: python3 design_ftth.py <index 0..5|all>
"""
import json, math, os, sys, heapq
import numpy as np

ROADS_DIR = "/home/z/my-project/scripts/osm_roads"
HH_DIR = "/home/z/my-project/scripts/households"
OUT_DIR = "/home/z/my-project/scripts/ftth_design"
os.makedirs(OUT_DIR, exist_ok=True)

RIDDER_POLY_BBOXES = [
    (50.33472, 50.34025, 83.51045, 83.51941), (50.32017, 50.32509, 83.50425, 83.51132),
    (50.32208, 50.32903, 83.49661, 83.50787), (50.32620, 50.33259, 83.48943, 83.49963),
    (50.32786, 50.33281, 83.52260, 83.52510), (50.33243, 50.34807, 83.51552, 83.53243),
    (50.32833, 50.33238, 83.52475, 83.53007), (50.33394, 50.33601, 83.49872, 83.50192),
    (50.33137, 50.33548, 83.49349, 83.50037), (50.32962, 50.33224, 83.49751, 83.50169),
    (50.33260, 50.33495, 83.50097, 83.50477), (50.33392, 50.33623, 83.50257, 83.50630),
    (50.32663, 50.32774, 83.51046, 83.51421), (50.32400, 50.32674, 83.52580, 83.53057),
    (50.31809, 50.33490, 83.52610, 83.55400),
]

ROAD_OK = {"primary", "primary_link", "secondary", "secondary_link", "tertiary",
           "tertiary_link", "unclassified", "residential", "living_street",
           "service", "road", "track"}

ZONE_CAP = 12        # ДХ на зону (сплиттер 1x16, загрузка <=75%)
ZONE_MIN = 5         # зоны мельче сливаются с соседними
GROUP_CAP = 4        # зон на PON-группу (сплиттер 1x4)
ENTRY_M = 15.0       # ввод в дом: крепление по фасаду + запас
SLACK = 1.03         # запас на провис и подъёмы (магистраль/распределение)
FIB_STD = [2, 4, 8, 12, 16, 24, 32, 48, 64]
POLE_SPAN = 45.0     # шаг опор (точки подвеса)
SPL1_4_DB = 7.4      # вносимое затухание сплиттера 1x4
SPL1_16_DB = 13.9    # сплиттер 1x16
FIBER_DB_KM = 0.35   # G.652D/G.657A @1310 нм
CONN_DB = 0.5        # коннектор APC
SPLICE_DB = 0.05     # сварка
BUDGET_DB = 28.0     # GPON Class B+


def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * \
        math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class Geo:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.mlat = 111132.92 - 559.82 * math.cos(2 * math.radians(lat0))
        self.mlon = 111412.84 * math.cos(math.radians(lat0))

    def to_xy(self, lat, lon):
        return ((lon - self.lon0) * self.mlon, (lat - self.lat0) * self.mlat)

    def to_latlon(self, x, y):
        return (self.lat0 + y / self.mlat, self.lon0 + x / self.mlon)


def load_roads(key, anchor, apply_ridder):
    with open(os.path.join(ROADS_DIR, f"{key}.json"), encoding="utf-8") as f:
        data = json.load(f)
    nodes, edges, hist = {}, {}, {}
    for el in data.get("elements", []):
        if el.get("type") == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        hw = el.get("tags", {}).get("highway", "?")
        if hw not in ROAD_OK:
            continue
        hist[hw] = hist.get(hw, 0) + 1
        nds = [n for n in el.get("nodes", []) if n in nodes]
        for a, b in zip(nds, nds[1:]):
            if a == b:
                continue
            la, lo = nodes[a]
            lb, lob = nodes[b]
            mid = ((la + lb) / 2, (lo + lob) / 2)
            if apply_ridder:
                if any(bb[0] <= mid[0] <= bb[1] and bb[2] <= mid[1] <= bb[3]
                      for bb in RIDDER_POLY_BBOXES):
                    continue
                if hav(anchor[0], anchor[1], mid[0], mid[1]) > 1600:
                    continue
            L = hav(la, lo, lb, lob)
            if L < 0.5:
                continue
            k = (min(a, b), max(a, b))
            if k not in edges or L < edges[k]:
                edges[k] = L
    return nodes, edges, hist


def main_component(edges):
    adj = {}
    for (a, b) in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, best = set(), []
    for start in list(adj.keys()):
        if start in seen:
            continue
        comp, st = [], [start]
        seen.add(start)
        while st:
            u = st.pop()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    st.append(v)
        if len(comp) > len(best):
            best = comp
    keep = set(best)
    medges = {k: v for k, v in edges.items() if k[0] in keep and k[1] in keep}
    return keep, medges


class EdgeIndex:
    """Сеточный индекс рёбер для быстрого снапа точки к ближайшему ребру."""

    def __init__(self, medges, nodes, geo):
        self.geo = geo
        self.cell = 100.0
        self.grid = {}
        self.epos = {}
        for (a, b), L in medges.items():
            ax, ay = geo.to_xy(*nodes[a])
            bx, by = geo.to_xy(*nodes[b])
            self.epos[(a, b)] = ((ax, ay), (bx, by))
            x0, x1 = sorted((ax, bx))
            y0, y1 = sorted((ay, by))
            for cx in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
                for cy in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                    self.grid.setdefault((cx, cy), []).append((a, b))

    def nearest_edge(self, px, py, max_r=4):
        ccx, ccy = int(px // self.cell), int(py // self.cell)
        for r in range(1, max_r + 1):
            cand = []
            for cx in range(ccx - r, ccx + r + 1):
                for cy in range(ccy - r, ccy + r + 1):
                    cand += self.grid.get((cx, cy), [])
            if not cand:
                continue
            best, bd, bq = None, None, None
            for k in cand:
                (ax, ay), (bx, by) = self.epos[k]
                vx, vy = bx - ax, by - ay
                vv = vx * vx + vy * vy
                t = ((px - ax) * vx + (py - ay) * vy) / vv if vv > 0 else 0.0
                t = max(0.0, min(1.0, t))
                qx, qy = ax + t * vx, ay + t * vy
                d = math.hypot(px - qx, py - qy)
                if bd is None or d < bd:
                    best, bd, bq = k, d, (qx, qy, t)
            if best is not None:
                return best, bq
        return None, None


def dijkstra_multi(adj, source, targets):
    """Кратчайшие пути от source до всех целей. Возвращает {target: path}."""
    orig = set(targets)
    left = set(targets)
    dist = {source: 0.0}
    prev = {}
    pq = [(0.0, source)]
    done = set()
    while pq and left:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if u in left:
            left.discard(u)
            if not left:
                break
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    out = {}
    for t in orig:
        if t not in dist:
            out[t] = None
            continue
        p, c = [], t
        while c != source:
            p.append(c)
            c = prev[c]
        p.append(source)
        out[t] = p[::-1]
    return out


def knn_graph(X, k):
    n = len(X)
    k = min(k, n - 1)
    d2 = ((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(d2, np.inf)
    adj = {}
    for i in range(n):
        nb = np.argsort(d2[i])[:k]
        adj[i] = [int(v) for v in nb]
    return adj


def grow_regions(X, cap, k=8):
    """Выращивание компактных областей до ёмкости cap по kNN-смежности.
    Семена — с северного края, зоны получаются полными и смежными."""
    n = len(X)
    if n == 0:
        return []
    adj = knn_graph(X, k)
    order = sorted(range(n), key=lambda i: (round(X[i][1] / 50.0), X[i][0]))
    label = [-1] * n
    zones = []
    for seed in order:
        if label[seed] != -1:
            continue
        zi = len(zones)
        zone = [seed]
        label[seed] = zi
        qi = 0
        while qi < len(zone) and len(zone) < cap:
            u = zone[qi]
            qi += 1
            for v in adj[u]:
                if label[v] == -1 and len(zone) < cap:
                    label[v] = zi
                    zone.append(v)
        zones.append(zone)
    return zones


def merge_small(X, groups, min_size, cap, merge_r=450.0):
    """Слияние зон мельче min_size с ближайшими, пока позволяет ёмкость."""
    groups = [g for g in groups if g]
    if min_size <= 1:
        return groups
    merged = True
    while merged:
        merged = False
        cents = [X[g].mean(0) for g in groups]
        small = [i for i, g in enumerate(groups) if len(g) < min_size]
        for si in small:
            best, bestd = None, None
            for oi in range(len(groups)):
                if oi == si:
                    continue
                if len(groups[oi]) + len(groups[si]) > cap:
                    continue
                d = float(np.hypot(*(cents[oi] - cents[si])))
                if bestd is None or d < bestd:
                    best, bestd = oi, d
            if best is not None and bestd < merge_r:
                groups[best] = groups[best] + groups[si]
                groups[si] = []
                merged = True
        groups = [g for g in groups if g]
    return groups


def fib_type(n_fib):
    for f in FIB_STD:
        if f >= n_fib:
            return f
    return FIB_STD[-1]


def process(v, idx):
    key = v["key"]
    bbox = v["bbox_final"]
    print(f"\n===== [{idx}] {v['name']} =====", flush=True)

    lat0 = (bbox["lat_lo"] + bbox["lat_hi"]) / 2
    lon0 = (bbox["lon_lo"] + bbox["lon_hi"]) / 2
    geo = Geo(lat0, lon0)

    nodes, edges, hist = load_roads(key, v.get("anchor"), key == "prigorodnoe")
    mc_nodes, medges = main_component(edges)
    print(f"  улицы: рёбер {len(edges)}, главный компонент: {len(mc_nodes)} узлов, "
          f"{len(medges)} рёбер; типы: {dict(sorted(hist.items(), key=lambda kv: -kv[1])[:6])}", flush=True)

    with open(os.path.join(HH_DIR, f"{key}_numbered.geojson"), encoding="utf-8") as f:
        hh_fc = json.load(f)
    hhs = []
    for ft in hh_fc["features"]:
        p = ft["properties"]
        hhs.append(dict(num=p["num"], lat=p["clat"], lon=p["clon"],
                        xy=geo.to_xy(p["clat"], p["clon"])))
    print(f"  абонентов (ДХ): {len(hhs)}", flush=True)

    # граф
    adj = {}
    def add_edge(a, b, w):
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))
    for (a, b), L in medges.items():
        add_edge(a, b, L)

    eidx = EdgeIndex(medges, nodes, geo)
    vnode_xy = {}
    vid_cnt = [-1]

    def node_xy(u):
        if u in vnode_xy:
            return vnode_xy[u]
        return geo.to_xy(*nodes[u])

    def node_latlon(u):
        x, y = node_xy(u)
        return geo.to_latlon(x, y)

    def snap(px, py):
        ek, q = eidx.nearest_edge(px, py)
        vid_cnt[0] -= 1
        vid = vid_cnt[0]
        if ek is None:
            best, bd = None, None
            for u in mc_nodes:
                ux, uy = geo.to_xy(*nodes[u])
                d = math.hypot(px - ux, py - uy)
                if bd is None or d < bd:
                    best, bd = u, d
            vnode_xy[vid] = (px, py)
            add_edge(vid, best, max(1.0, bd))
            return vid, 0.0
        qx, qy, t = q
        vnode_xy[vid] = (qx, qy)
        a, b = ek
        L = medges[ek]
        add_edge(vid, a, max(1.0, t * L))
        add_edge(vid, b, max(1.0, (1 - t) * L))
        return vid, math.hypot(px - qx, py - qy)

    def path_len(path):
        s = 0.0
        for a, b in zip(path, path[1:]):
            ax, ay = node_xy(a)
            bx, by = node_xy(b)
            s += math.hypot(bx - ax, by - ay)
        return s

    # снап абонентов
    for h in hhs:
        vid, entry = snap(*h["xy"])
        h["vid"] = vid
        h["entry"] = entry

    # OLT — взвешенный центр абонентов
    X = np.array([h["xy"] for h in hhs])
    olt_vid, _ = snap(float(X[:, 0].mean()), float(X[:, 1].mean()))
    olt_xy = vnode_xy[olt_vid]

    # зоны (<= ZONE_CAP ДХ): выращивание областей по kNN-смежности + слияние хвостов
    zone_idx = grow_regions(X, ZONE_CAP, k=8)
    zone_idx = merge_small(X, zone_idx, ZONE_MIN, ZONE_CAP, 450.0)
    zone_idx.sort(key=lambda g: (round(float(X[g].mean(0)[1]) / 50.0), float(X[g].mean(0)[0])))
    zones = []
    for zi, g in enumerate(zone_idx, 1):
        c = X[g].mean(0)
        zvid, _ = snap(float(c[0]), float(c[1]))
        zones.append(dict(id=zi, idxs=g, vid=zvid, xy=vnode_xy[zvid],
                          hh_nums=[hhs[i]["num"] for i in g]))
    # группы зон (<= GROUP_CAP) -> М1 + PON-порт
    ZX = np.array([z["xy"] for z in zones])
    if len(zones) > GROUP_CAP:
        gidx = grow_regions(ZX, GROUP_CAP, k=4)
        gidx = merge_small(ZX, gidx, 2, GROUP_CAP, 600.0)
    else:
        gidx = [[i] for i in range(len(zones))]
    gidx.sort(key=lambda g: (round(float(ZX[g].mean(0)[1]) / 50.0), float(ZX[g].mean(0)[0])))
    groups = []
    for gi, gz in enumerate(gidx, 1):
        c = ZX[gz].mean(0)
        gvid, _ = snap(float(c[0]), float(c[1]))
        groups.append(dict(id=gi, zone_pos=gz, vid=gvid, xy=vnode_xy[gvid]))
    print(f"  зон распределения: {len(zones)} (медиана {int(np.median([len(z['idxs']) for z in zones]))} ДХ), "
          f"PON-групп/муфт М1: {len(groups)}", flush=True)

    # ---- маршрутизация ----
    def path_edges(path):
        return [(min(a, b), max(a, b)) for a, b in zip(path, path[1:])]

    # магистраль: OLT -> М1
    feeder_paths = {}
    feeder_load = {}
    for g in groups:
        p = dijkstra_multi(adj, olt_vid, [g["vid"]])[g["vid"]]
        feeder_paths[g["id"]] = p
        for ek in path_edges(p):
            feeder_load[ek] = feeder_load.get(ek, 0) + 1
    # распределение: М1 -> зоны
    dist_load = {}
    dist_paths = {}
    for g in groups:
        tset = [zones[i]["vid"] for i in g["zone_pos"]]
        res = dijkstra_multi(adj, g["vid"], tset)
        for i in g["zone_pos"]:
            z = zones[i]
            p = res[z["vid"]]
            dist_paths[(g["id"], z["id"])] = p
            if p:
                for ek in path_edges(p):
                    dist_load[ek] = dist_load.get(ek, 0) + 1
    # вводы: зона -> ДХ
    drop_load = {}
    hh_out = []
    for z in zones:
        tset = [hhs[i]["vid"] for i in z["idxs"]]
        res = dijkstra_multi(adj, z["vid"], tset)
        for i in z["idxs"]:
            h = hhs[i]
            p = res[h["vid"]]
            if p:
                for ek in path_edges(p):
                    drop_load[ek] = drop_load.get(ek, 0) + 1
                plen = path_len(p)
            else:  # резервный вариант — прямой воздушный segment
                zx, zy = z["xy"]
                plen = math.hypot(h["xy"][0] - zx, h["xy"][1] - zy)
            hh_out.append(dict(num=h["num"], zone=z["id"], entry=h["entry"],
                               drop_len=round(plen + h["entry"] + ENTRY_M, 1)))

    # связи ДХ с зонами/группами для бюджета потерь
    zone_by_pos = {pos: zones[pos]["id"] for pos in range(len(zones))}
    group_of_zone = {}
    for g in groups:
        for pos in g["zone_pos"]:
            group_of_zone[zone_by_pos[pos]] = g["id"]

    # ---- длины и волокна ----
    def edge_pts(ek):
        a, b = ek
        la, loa = node_latlon(a)
        lb, lob = node_latlon(b)
        return [[loa, la], [lob, lb]]

    feeder_cables = []
    for ek, load in feeder_load.items():
        a, b = ek
        ax, ay = node_xy(a)
        bx, by = node_xy(b)
        L = math.hypot(bx - ax, by - ay) * SLACK
        fibers = fib_type(2 * load)
        feeder_cables.append(dict(pts=edge_pts(ek), load=load, fibers=fibers, len_m=round(L, 1)))
    dist_cables = []
    for ek, load in dist_load.items():
        a, b = ek
        ax, ay = node_xy(a)
        bx, by = node_xy(b)
        L = math.hypot(bx - ax, by - ay) * SLACK
        fibers = fib_type(2 * load)
        dist_cables.append(dict(pts=edge_pts(ek), load=load, fibers=fibers, len_m=round(L, 1)))
    drop_cables = []
    for ek, load in drop_load.items():
        a, b = ek
        ax, ay = node_xy(a)
        bx, by = node_xy(b)
        drop_cables.append(dict(pts=edge_pts(ek), load=load,
                                len_m=round(math.hypot(bx - ax, by - ay), 1)))
    feeder_len = sum(c["len_m"] for c in feeder_cables)
    dist_len = sum(c["len_m"] for c in dist_cables)
    # вводные воздушные сегменты: от точки снапа на улице до центроида дома
    entries = []
    for h in hhs:
        qx, qy = vnode_xy[h["vid"]]
        qlat, qlon = geo.to_latlon(qx, qy)
        entries.append([h["num"], [qlon, qlat], [h["lon"], h["lat"]]])
    entry_len = 0.0
    for num, q, hp in entries:
        entry_len += hav(q[1], q[0], hp[1], hp[0])
    drop_network_len = sum(c["len_m"] for c in drop_cables) + entry_len
    drop_total = sum(h["drop_len"] for h in hh_out)
    # абонентская разводка: малосчётный кабель по нагрузке (волокон = ДХ + 2 резерва)
    drop_by_fibers = {}
    for c in drop_cables:
        c["fibers"] = fib_type(c["load"] + 2)
        drop_by_fibers[c["fibers"]] = drop_by_fibers.get(c["fibers"], 0.0) + c["len_m"]
    # физический метраж: уличная часть + вводные сегменты + 15 м на дом (фасад/запас)
    drop_cable_m = drop_network_len + ENTRY_M * len(hhs)

    by_fibers_f, by_fibers_d = {}, {}
    for c in feeder_cables:
        by_fibers_f[c["fibers"]] = by_fibers_f.get(c["fibers"], 0.0) + c["len_m"]
    for c in dist_cables:
        by_fibers_d[c["fibers"]] = by_fibers_d.get(c["fibers"], 0.0) + c["len_m"]

    # ---- бюджет потерь (худший абонент) ----
    fl = {g["id"]: path_len(feeder_paths[g["id"]]) for g in groups}
    dl = {}
    for (gid, zid), p in dist_paths.items():
        if p:
            dl[zid] = path_len(p)
    worst = 0.0
    for h in hh_out:
        zid = h["zone"]
        gid = group_of_zone[zid]
        tot = fl.get(gid, 0) + dl.get(zid, 0) + h["drop_len"]
        worst = max(worst, tot)
    loss_db = worst / 1000.0 * FIBER_DB_KM + SPL1_4_DB + SPL1_16_DB + \
        2 * CONN_DB + 4 * SPLICE_DB

    # ---- оборудование ----
    aerial_km = (feeder_len + dist_len + drop_network_len) / 1000.0
    equip = dict(
        olt_units=math.ceil(len(groups) / 16),
        pon_ports=len(groups),
        odf=1,
        spl1x4=len(groups),
        spl1x16=len(zones),
        muf_trunk=len(groups) + int(round(feeder_len / 800.0)),  # М1 + проходные
        boxes_zone=len(zones),
        ont=len(hhs),
        drop_patches=len(hhs),
        suspension_points=int(round((feeder_len + dist_len + drop_network_len) / POLE_SPAN)),
    )

    stats = dict(
        name=v["name"],
        n_households=len(hhs), official=v["households"],
        n_zones=len(zones), n_groups=len(groups),
        feeder_km=round(feeder_len / 1000, 3), dist_km=round(dist_len / 1000, 3),
        drop_network_km=round(drop_network_len / 1000, 3),
        drop_path_km=round(drop_total / 1000, 3),
        drop_cable_km=round(drop_cable_m / 1000, 3),
        drop_entry_km=round((entry_len + ENTRY_M * len(hhs)) / 1000, 3),
        total_km=round((feeder_len + dist_len + drop_cable_m) / 1000, 3),
        feeder_by_fibers={str(k): round(v, 1) for k, v in sorted(by_fibers_f.items())},
        dist_by_fibers={str(k): round(v, 1) for k, v in sorted(by_fibers_d.items())},
        drop_by_fibers={str(k): round(v, 1) for k, v in sorted(drop_by_fibers.items())},
        drop_mean_m=round(float(np.mean([h["drop_len"] for h in hh_out])), 1),
        drop_median_m=round(float(np.median([h["drop_len"] for h in hh_out])), 1),
        drop_max_m=round(float(np.max([h["drop_len"] for h in hh_out])), 1),
        zone_median=int(np.median([len(z["idxs"]) for z in zones])),
        worst_path_m=round(worst, 1),
        loss_db=round(loss_db, 2), budget_db=BUDGET_DB, margin_db=round(BUDGET_DB - loss_db, 2),
        aerial_km=round(aerial_km, 3),
        equipment=equip,
    )
    print(f"  кабель: магистраль {stats['feeder_km']:.2f} км, распределение {stats['dist_km']:.2f} км, "
          f"абонентская разводка {stats['drop_cable_km']:.2f} км (из них вводы {stats['drop_entry_km']:.2f} км)", flush=True)
    print(f"  худший путь {worst:.0f} м -> затухание {loss_db:.1f} дБ (запас {BUDGET_DB-loss_db:.1f} дБ)", flush=True)

    olt_lat, olt_lon = geo.to_latlon(*olt_xy)
    out = dict(
        index=idx, key=key, name=v["name"], district=v["district"], okrug=v["okrug"],
        olt=dict(lat=olt_lat, lon=olt_lon),
        groups=[dict(id=g["id"], pon_port=g["id"], lat=node_latlon(g["vid"])[0], lon=node_latlon(g["vid"])[1],
                     zones=[zone_by_pos[p] for p in g["zone_pos"]]) for g in groups],
        zones=[dict(id=z["id"], lat=node_latlon(z["vid"])[0], lon=node_latlon(z["vid"])[1],
                    n=len(z["idxs"]), households=sorted(z["hh_nums"])) for z in zones],
        cables=dict(feeder=feeder_cables, dist=dist_cables, drop=drop_cables, entries=entries),
        households=hh_out,
        stats=stats,
    )
    with open(os.path.join(OUT_DIR, f"{key}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"  сохранено: ftth_design/{key}.json", flush=True)
    return stats


def main():
    with open("/home/z/my-project/scripts/snp_bounds_final.json", encoding="utf-8") as f:
        villages = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    idxs = range(len(villages)) if arg == "all" else [int(arg)]
    summary = []
    for i in idxs:
        try:
            summary.append(process(villages[i], i))
        except FileNotFoundError as e:
            print(f"  !! пропуск: {e}", flush=True)
    if summary:
        print("\n=== СВОДКА ===")
        print(f"{'село':<28}{'ДХ':>5}{'зоны':>6}{'PON':>5}{'маг.км':>8}{'расп.км':>9}{'абон.км':>9}{'всего.км':>9}{'дБ':>6}")
        for s in summary:
            print(f"{s.get('name', ''):<28}{s['n_households']:>5}{s['n_zones']:>6}{s['n_groups']:>5}"
                  f"{s['feeder_km']:>8.2f}{s['dist_km']:>9.2f}{s['drop_cable_km']:>9.2f}"
                  f"{s['total_km']:>9.2f}{s['loss_db']:>6.1f}")


if __name__ == "__main__":
    main()
