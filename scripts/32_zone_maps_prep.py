# -*- coding: utf-8 -*-
"""
Шаг 32. Подготовка данных для карт зон ОРШ (схема D) + валидация привязки.

1) Для каждого села воспроизводится разбиение partition_greedy(S_MIN=15)
   (модель шага 28) и сверяется с work/boq_decentral_data.json:
   - узлы врезов (px) == cut_log;
   - распределение домов по зонам == zones[].houses.
2) Строится преобразование координат сеть -> кадр work/full/<NN>_<Село>.png:
   аффинная привязка по якорю (px -> lat/lon) + обратная привязка кадра
   (lat/lon -> px кадра по *_final.json). Для 4 сёл с mosaic.jpg выполняется
   независимая проверка NCC (патч вокруг якоря: мозаика vs кадр).
3) Проверка попадания всех элементов сети в кадр.

Выход: work/zone_maps_prep.json (зоны, счётчики, трансформ, отчёт валидации).
"""
import json, math, importlib.util
from collections import defaultdict, Counter

BASE = '/home/z/my-project'

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)
Tree = de28.Tree

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}
MPP_LAT = 110574.0

NUMS = {'verhneberezovka': '01', 'solnechnoe': '02', 'perevalnoe': '03',
        'vinnoe': '04', 'prigorodnoe': '05', 'altaiskiy': '06'}
FULLIMG = {
    'verhneberezovka': 'work/full/01_Верхнеберезовка.png',
    'solnechnoe': 'work/full/02_Солнечное.png',
    'perevalnoe': 'work/full/03_Перевальное.png',
    'vinnoe': 'work/full/04_Винное.png',
    'prigorodnoe': 'work/full/05_Пригородное.png',
    'altaiskiy': 'work/full/06_Алтайский.png',
}
FIN = {  # lat_max, lon_min, m_per_px кадра work/full
    'verhneberezovka': (50.29903091237, 82.18631207942963, 0.381575968885646),
    'solnechnoe': (50.06210832835728, 82.69829213619232, 0.38343626568040323),
    'perevalnoe': (50.250823856348404, 82.26839303970337, 0.38191911638781334),
    'vinnoe': (50.06967703845101, 82.80938923358917, 0.38338297391059084),
    'prigorodnoe': (50.33231295699761, 83.50476801395416, 0.38127303114972124),
    'altaiskiy': (50.2731935293285, 82.33995974063873, 0.38189822479928953),
}


def build_transform(key, net):
    """(x, y) сети -> (X, Y) кадра work/full. Аффинная цепочка через lat/lon."""
    geo = json.load(open(f'{BASE}/work/mosaic_geo.json'))[key]
    ax, ay = net['anchor']['x'], net['anchor']['y']
    alat, alon = net['anchor']['lat'], net['anchor']['lon']
    mpp = geo['mpp']
    lat_max, lon_min, mpp_f = FIN[key]
    kx = mpp / (111320.0 * math.cos(math.radians(alat)))   # град/px сети по X
    ky = mpp / MPP_LAT                                     # град/px сети по Y
    KX = 111320.0 * math.cos(math.radians(alat)) / mpp_f   # px кадра / град
    KY = MPP_LAT / mpp_f

    def T(p):
        lon = alon + (p[0] - ax) * kx
        lat = alat - (p[1] - ay) * ky
        return ((lon - lon_min) * KX, (lat_max - lat) * KY)
    return T, mpp_f


def ncc_offset(pa, pb):
    """Смещение максимума NCC патча pa относительно pb (поиск в окне +-12 px)."""
    import numpy as np
    a = np.asarray(pa, dtype=np.float32).mean(axis=2)
    b = np.asarray(pb, dtype=np.float32).mean(axis=2)
    a = (a - a.mean()) / (a.std() + 1e-6)
    best, bo = -2.0, (0, 0)
    R = 12
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            bb = b[dy:dy + a.shape[0], dx:dx + a.shape[1]]
            if bb.shape != a.shape:
                continue
            bb = (bb - bb.mean()) / (bb.std() + 1e-6)
            c = float((a * bb).mean())
            if c > best:
                best, bo = c, (dx, dy)
    return bo, best


def main():
    report = {}
    for v in de28.VILLAGES:
        key = v['key']
        t = Tree(v)
        cuts, log = t.partition_greedy(15.0)
        r = t.layout(cuts)
        db = DBY[key]

        # --- сверка врезов с книгой D ---
        cuts_px = [[round(c[0], 2), round(c[1], 2)] for c in cuts]
        log_px = [[round(c['node'][0], 2), round(c['node'][1], 2)] for c in db['cut_log']]
        assert cuts_px == log_px, f'{key}: врезы не совпали\n{cuts_px}\n{log_px}'

        # --- зоны: узлы и дома ---
        zr = {}
        zr[t.root] = t.root
        for u in t.bfs:
            if u == t.root:
                continue
            zr[u] = u if u in set(cuts) else zr[t.parent[u]]
        zone_dh = Counter()
        for node, dh in t.homes.items():
            zone_dh[zr[node]] += dh
        # сверка с JSON: ЦУ + врезы в том же порядке
        json_zones = [z['houses'] for z in db['zones']]
        calc_zones = [zone_dh.get(t.root, 0)] + [zone_dh[c] for c in cuts]
        assert json_zones == calc_zones, f'{key}: дома зон {calc_zones} != {json_zones}'

        # --- элементы сети ---
        net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
        T, mpp_f = build_transform(key, net)

        pts_all = []
        for e in net['feeder_edges']:
            pts_all += [e[0], e[1]]
        for d in net['drops']:
            pts_all.append(d['poly'][-1])
        for c in net['couplers']:
            pts_all.append([c['x'], c['y']])
        pts_all.append([net['anchor']['x'], net['anchor']['y']])

        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(f'{BASE}/{FULLIMG[key]}')
        W, H = im.size
        X = [T(p) for p in pts_all]
        xs = [p[0] for p in X]; ys = [p[1] for p in X]
        inside = sum(1 for x, y in X if 0 <= x < W and 0 <= y < H)

        # --- NCC-проверка по якорю (села с mosaic.jpg) ---
        ncc = None
        import os
        mpath = f'{BASE}/work/{key}/mosaic.jpg'
        if os.path.exists(mpath):
            ax, ay = net['anchor']['x'], net['anchor']['y']
            AX, AY = T([ax, ay])
            S = 220
            mos = Image.open(mpath).convert('RGB')
            pa = mos.crop((int(ax - S), int(ay - S), int(ax + S), int(ay + S)))
            pb = im.convert('RGB').crop((int(AX - S), int(AY - S), int(AX + S), int(AY + S)))
            (dx, dy), peak = ncc_offset(pa, pb)
            ncc = dict(dx=dx, dy=dy, peak=round(peak, 3))
            # dx,dy > 0 значит: патч кадра смещён вправо/вниз относительно мозаики,
            # т.е. истинное положение точки в кадре = расчётное + (dx, dy)

        report[key] = dict(
            name=db['name'], num=db['num'],
            img=FULLIMG[key], W=W, H=H, mpp_frame=mpp_f,
            n_zones=len(cuts), orsh=1 + len(cuts),
            zone_dh=[dict(root='ЦУ' if z == t.root else 'зона',
                          houses=zone_dh.get(z, 0) if z == t.root else zone_dh[z],
                          px=[round(z[0], 1), round(z[1], 1)]) for z in [t.root] + list(cuts)],
            bounds=dict(x_min=round(min(xs), 1), x_max=round(max(xs), 1),
                        y_min=round(min(ys), 1), y_max=round(max(ys), 1)),
            points=len(pts_all), inside=inside, outside=len(pts_all) - inside,
            ncc=ncc,
        )
        print(f"{db['num']} {db['name']:<18} зон {len(cuts):>2}+ЦУ  кадр {W}x{H}  "
              f"в кадре {inside}/{len(pts_all)}  X[{min(xs):.0f}..{max(xs):.0f}] "
              f"Y[{min(ys):.0f}..{max(ys):.0f}]  NCC {ncc}")

    json.dump(report, open(f'{BASE}/work/zone_maps_prep.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\nСохранено: work/zone_maps_prep.json')
    print('Сверка врезов и домов зон с boq_decentral_data.json — OK по всем 6 СНП')


if __name__ == '__main__':
    main()
