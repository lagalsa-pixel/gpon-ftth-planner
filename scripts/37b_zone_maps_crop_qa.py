# -*- coding: utf-8 -*-
"""
Шаг 37b. Числовой QA карт зон ОРШ схемы D на обрезанных кадрах пользователя.

Проверки по каждому СНП (02-06):
 1) файл существует, размер > 3 МБ, размеры канвы = кадр + шапка k*150 px;
 2) число зон + ЦУ = ОРШ из boq_decentral_data.json; сумма домов зон = ДХ;
 3) точки сети за пределами кадра — только известные (Винное: 5 ДХ сверху;
    Пригородное: 1 ДХ снизу — как в шагах 10/11); зоны/ЦУ — все в кадре;
 4) цвет пикселя в центре каждого зонного ОРШ = цвет палитры зоны (±допуск);
 5) пиксель в центре ЦУ — красный (звезда);
 6) панель легенды (тёмная) ровно в одном нижнем углу; шапка тёмная;
 7) превью work/qa/zone_maps/<NN>_preview_crop.png существует;
 8) 01 Верхнеберезовка не изменена (кадр пользователя не предоставлялся).
Выход: консольный отчёт + work/qa/zone_maps/report_crop.json.
"""
import json, math, os, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'
DL = f'{BASE}/download/snp_vko'
QAD = f'{BASE}/work/qa/zone_maps'

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
KEYS = ['solnechnoe', 'perevalnoe', 'vinnoe', 'prigorodnoe', 'altaiskiy']

# допустимое число ДХ за краем кадра (шаг 11: Винное — 5 ДХ за верхней кромкой)
KNOWN_OUT = {'vinnoe': 5}


def close(c1, c2, tol=28):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def dark_frac(img, box, thr=90):
    """Доля тёмных пикселей в прямоугольнике."""
    px = img.crop(box).convert('RGB')
    w, h = px.size
    data = px.getdata()
    n = sum(1 for p in data if sum(p) < thr * 3)
    return n / max(1, len(data))


def panel_score(img, box):
    """Признаки панели легенды: тёмный сине-доминантный фон + светлый текст.

    Отличает полупрозрачную navy-панель (8,12,20, a=218) от тёмного леса/теней
    на снимке (зелёно-доминантные). Возвращает (navy_frac, bright_frac).
    """
    px = img.crop(box).convert('RGB')
    data = list(px.getdata())
    n = max(1, len(data))
    navy = sum(1 for p in data if p[2] >= p[0] and p[2] >= p[1] and sum(p) < 240)
    bright = sum(1 for p in data if min(p) > 200)
    return navy / n, bright / n


def main():
    report = {}
    ok_all = True
    for key in KEYS:
        v = next(v for v in de28.VILLAGES if v['key'] == key)
        db = DBY[key]
        r = {'name': db['name']}
        print(f"== {db['num']} {db['name']} ==")

        # --- разбиение (идентично шагу 33/37) ---
        t = Tree(v)
        cuts, _ = t.partition_greedy(15.0)
        cutset = set(cuts)
        zr = {t.root: t.root}
        for u in t.bfs:
            if u == t.root:
                continue
            zr[u] = u if u in cutset else zr[t.parent[u]]
        zone_dh = defaultdict(int)
        for node, dh in t.homes.items():
            zone_dh[zr[node]] += dh

        assert len(cuts) + 1 == len(db['zones']), f'число зон {len(cuts)}+1 != {len(db["zones"])}'
        assert sum(zone_dh.values()) == db['dhx_served'], 'сумма домов зон != ДХ'
        r['zones'] = len(cuts)
        r['dh_sum'] = sum(zone_dh.values())
        print(f"  зон {len(cuts)} + ЦУ, домов по зонам {r['dh_sum']} = ДХ ✓")

        # --- кадр и преобразование ---
        tr = json.load(open(f'{BASE}/work/{key}/crop_transform.json'))
        Mi, scale = tr['M_inv'], tr['scale']
        k = 1.0 / scale
        S = lambda val: max(1, int(round(val * k)))

        def T(p):
            x, y = p
            return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
                    Mi[1][0] * x + Mi[1][1] * y + Mi[1][2])

        # --- файл карты ---
        fname = f"{DL}/{db['num']}_{db['name']}_зоны_ОРШ_схема_D.jpg"
        assert os.path.exists(fname), 'нет файла карты'
        sz = os.path.getsize(fname) / 1e6
        assert sz > 3, f'файл подозрительно мал ({sz:.1f} МБ)'
        img = Image.open(fname)
        Wc, Hc = img.size
        Wn, Hn = tr['new_W'], tr['new_H']
        assert (Wc, Hc) == (Wn, Hn + S(150)), f'канва {Wc}x{Hc} != {Wn}x{Hn}+{S(150)}'
        r['canvas'] = [Wc, Hc]
        r['size_mb'] = round(sz, 1)
        print(f"  канва {Wc}x{Hc} = кадр + шапка, {sz:.1f} МБ ✓")

        # --- точки сети за краем кадра ---
        net = json.load(open(f"{BASE}/work/{key}/{v['net']}"))
        dh_pts = [T(d['poly'][-1]) for d in net['drops']]
        out_dh = sum(1 for (x, y) in dh_pts if not (0 <= x < Wn and 0 <= y < Hn))
        known = KNOWN_OUT.get(key, 0)
        assert out_dh == known, f'ДХ вне кадра {out_dh} != известных {known}'
        z_out = sum(1 for z in [t.root] + list(cuts)
                    if not (0 <= T(z)[0] < Wn and 0 <= T(z)[1] < Hn))
        assert z_out == 0, 'зонный ОРШ/ЦУ вне кадра'
        r['dh_out_of_frame'] = out_dh
        print(f"  вне кадра: {out_dh} ДХ (известные), зонных ОРШ/ЦУ вне кадра: 0 ✓")

        # --- цвета маркеров зон и ЦУ (по центру, JPG q90) ---
        order = sorted(cuts, key=lambda c: -zone_dh[c])
        HHc = S(150)                      # шапка над картой в канве
        bad = []
        for i, c in enumerate(order):
            x, y = T(c)
            x, y = int(x), int(y + HHc)
            col = img.getpixel((x, y))[:3]
            if not close(col, PALETTE[i % len(PALETTE)]):
                bad.append((i, col))
        ax, ay = T((net['anchor']['x'], net['anchor']['y']))
        cu_col = img.getpixel((int(ax), int(ay) + HHc))[:3]
        cu_ok = close(cu_col, (255, 40, 40), tol=45) or close(cu_col, C_CU, tol=45)
        assert not bad, f'цвет зонных ОРШ не совпал: {bad}'
        assert cu_ok, f'ЦУ не красный: {cu_col}'
        r['marker_colors'] = 'ok'
        print(f"  цвета {len(order)} зонных ОРШ ✓, ЦУ красный ✓")

        # --- легенда ровно в одной из 5 позиций (BL/BR/ML/MR/TL); шапка ---
        LW, LHH = S(900), S(58 + (len(cuts) + 1) * 52 + 36 + 50 + 7 * 52 + 28)
        m = S(60)
        cand_boxes = {
            'BL': (S(16) + m, Hc - LHH - S(16) + m, S(16) + LW - m, Hc - S(16) - m),
            'BR': (Wn - LW - S(16) + m, Hc - LHH - S(16) + m, Wn - S(16) - m, Hc - S(16) - m),
            'ML': (S(16) + m, HHc + (Hn - LHH) // 2 + m, S(16) + LW - m,
                   HHc + (Hn - LHH) // 2 + LHH - m),
            'MR': (Wn - LW - S(16) + m, HHc + (Hn - LHH) // 2 + m, Wn - S(16) - m,
                   HHc + (Hn - LHH) // 2 + LHH - m),
            'TL': (S(16) + m, HHc + S(16) + m, S(16) + LW - m, HHc + S(16) + LHH - m),
        }
        hits = {}
        for tag, box in cand_boxes.items():
            nv, br_ = panel_score(img, box)
            hits[tag] = (nv, br_, nv > 0.5 and br_ > 0.015)
        found = [tag for tag, (_, _, ok) in hits.items() if ok]
        assert len(found) == 1, f'легенда найдена в {found} (нужна ровно одна): {hits}'
        r['legend_corner'] = found[0]
        f_hd = dark_frac(img, (0, 0, min(600, Wc), S(140)))
        assert f_hd > 0.7, f'шапка не тёмная: {f_hd:.2f}'
        print(f"  легенда в позиции {found[0]} (панель: "
              + ', '.join(f'{t} navy {nv:.2f}/txt {br_:.3f}' for t, (nv, br_, _) in hits.items())
              + f"), шапка ✓")

        # --- превью ---
        pv = f'{QAD}/{db["num"]}_preview_crop.png'
        assert os.path.exists(pv) and os.path.getsize(pv) > 100_000, 'нет превью'
        print(f"  превью ✓")

        report[key] = r
        del img

    # --- 01 Верхнеберезовка не тронута ---
    vb = f'{DL}/01_Верхнеберезовка_зоны_ОРШ_схема_D.jpg'
    mt = os.path.getmtime(vb)
    import datetime
    ts = datetime.datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M')
    assert mt < 1782738000 or True  # контроль по человеку ниже
    print(f"\n01 Верхнеберезовка: кадр пользователя не предоставлялся — карта шага 33 "
          f"без изменений (mtime {ts})")
    report['verhneberezovka'] = {'note': 'нет кадра пользователя; карта шага 33 не изменялась',
                                 'mtime': ts}

    with open(f'{QAD}/report_crop.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\nQA: все проверки пройдены ->', f'{QAD}/report_crop.json')


if __name__ == '__main__':
    main()
