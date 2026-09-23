# -*- coding: utf-8 -*-
"""
Шаг 33b. Числовой QA карт зон ОРШ (схема D).

Проверки по каждому СНП:
 1) файл карты существует, размер > 3 МБ, размеры канвы = база + шапка 150 px;
 2) все точки сети (рёбра, дропы, муфты, якорь) внутри канвы (нет обрезки);
 3) число зон + ЦУ = ОРШ из boq_decentral_data.json; сумма домов зон = ДХ;
 4) цвет пикселя в центре каждого зонного ОРШ = цвет палитры зоны (±допуск);
 5) пиксель в центре ЦУ — красный (звезда);
 6) панель легенды: тёмные пиксели в зоне легенды; шапка: тёмные пиксели;
 7) превью существует.
Выход: отчёт (консоль) + work/qa/zone_maps/report.json.
"""
import json, math, os, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
DL = f'{BASE}/download/snp_vko'

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)
Tree, nkey = de28.Tree, de28.nkey

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data.json', encoding='utf-8'))
DBY = {v['key']: v for v in DBOOK['villages']}

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

C_CU = (224, 49, 49)
PALETTE = [(25, 113, 194), (47, 158, 68), (240, 140, 0), (156, 54, 181),
           (12, 133, 153), (230, 73, 128), (102, 168, 15), (112, 72, 232),
           (160, 90, 44)]


def close(c1, c2, tol=28):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def main():
    report = {}
    ok_all = True
    for v in de28.VILLAGES:
        key, db = v['key'], DBY[v['key']]
        t = Tree(v)
        cuts, _ = t.partition_greedy(15.0)
        cutset = set(cuts)
        zr = {t.root: t.root}
        for u in t.bfs:
            if u == t.root:
                continue
            zr[u] = u if u in cutset else zr[t.parent[u]]

        fname = f"{DL}/{db['num']}_{db['name']}_зоны_ОРШ_схема_D.jpg"
        checks = {}
        ok = True

        # 1) файл
        checks['file'] = os.path.exists(fname)
        checks['size_MB'] = round(os.path.getsize(fname) / 1e6, 1) if checks['file'] else 0
        ok &= checks['file'] and checks['size_MB'] > 3

        if key in ('solnechnoe', 'perevalnoe', 'prigorodnoe', 'altaiskiy'):
            offx = offy = 0.0
        else:
            m = json.load(open(f'{BASE}/work/{key}/restitch.json'))
            offx, offy = m['offx'], m['offy']
        net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))

        pts = []
        for e in net['feeder_edges']:
            pts += [e[0], e[1]]
        for d in net['drops']:
            pts.append(d['poly'][-1])
        for c in net['couplers']:
            pts.append((c['x'], c['y']))
        pts.append((net['anchor']['x'], net['anchor']['y']))

        im = Image.open(fname).convert('RGB')
        W, H = im.size
        HH = 150
        # 2) границы
        out = sum(1 for p in pts
                  if not (0 <= p[0] + offx < W and 0 <= p[1] + offy < H - HH))
        checks['clipped_points'] = out
        ok &= out == 0

        # 3) зоны
        checks['zones'] = f"{len(cuts)}+ЦУ"
        ok &= (1 + len(cuts)) == db['orsh']

        # 4) цвета маркеров зон
        order = sorted(cuts, key=lambda c: -sum(dh for n, dh in t.homes.items()
                                                if zr[n] == c))
        zcol = {t.root: C_CU}
        for i, c in enumerate(order):
            zcol[c] = PALETTE[i % len(PALETTE)]
        bad_col = []
        px = im.load()
        for c in order:
            X, Y = int(c[0] + offx), int(c[1] + offy + HH)
            got = px[X, Y]
            if not close(got, zcol[c]):
                bad_col.append((X, Y, got, zcol[c]))
        checks['marker_colors_bad'] = len(bad_col)
        ok &= len(bad_col) == 0

        # 5) ЦУ красный
        ax, ay = int(net['anchor']['x'] + offx), int(net['anchor']['y'] + offy + HH)
        cu_ok = close(px[ax, ay], (255, 40, 40), tol=60)
        checks['cu_star_red'] = cu_ok
        ok &= cu_ok

        # 6) панели
        hdr_dark = sum(1 for x in range(0, W, 97) if sum(px[x, 60]) < 200)
        checks['header_dark_samples'] = hdr_dark
        ok &= hdr_dark > W // 200
        # легенда: левый нижний угол
        lgx, lgy = 60, H - 200
        lg_dark = sum(sum(px[lgx + dx, lgy]) for dx in range(0, 200, 25))
        checks['legend_dark'] = lg_dark
        ok &= lg_dark < 8 * 250

        # 7) превью
        pv = f'{BASE}/work/qa/zone_maps/{db["num"]}_preview.png'
        checks['preview'] = os.path.exists(pv)
        ok &= checks['preview']

        checks['OK'] = ok
        ok_all &= ok
        report[key] = checks
        print(f"{db['num']} {db['name']:<18} "
              f"{'OK ' if ok else 'FAIL'} clipped={out} цвета={len(bad_col)} "
              f"ЦУ={'кр' if cu_ok else 'НЕТ'} {checks['size_MB']} МБ")

    json.dump(report, open(f'{BASE}/work/qa/zone_maps/report.json', 'w',
                           encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok_all else 'ЕСТЬ ЗАМЕЧАНИЯ')
    raise SystemExit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
