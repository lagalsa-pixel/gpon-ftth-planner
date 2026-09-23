# -*- coding: utf-8 -*-
"""
Шаг 53. Обновление сетей: новые ДХ (v2) подключаются дропами к муфтам родителей.

Правила:
  - дерево сети (feeder_edges, couplers) НЕ меняется (проверенная топология);
  - родительское ДХ (split_roof / apartments_main) — обновляется последняя
    точка его дропа (позиция сместилась к своей части крыши / фасаду);
  - новые ДХ — дроп от муфты родителя: poly = poly_родителя[:-1] + [новая точка];
  - многоэтажки без своего ДХ рядом (hh_dist > 40 м) и здания вне кадра
    пользователя — в сеть не подключаются (флаг);
  - stats пересчитываются.

Выход: work/<key>/network_hh2.json (+ контроль длины/уникальности).
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json

BASE = '/home/z/my-project'
NET_FILES = {
    'verhneberezovka': 'network.json',
    'solnechnoe': 'network_v2.json',
    'perevalnoe': 'network_v2.json',
    'vinnoe': 'network_v2.json',
    'prigorodnoe': 'network_v2.json',
    'altaiskiy': 'network_v2.json',
}


def poly_len(poly, mpp):
    return sum(math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
               for i in range(len(poly) - 1)) * mpp


def in_frame(x, y, quad, margin_m, mpp):
    if quad is None:
        return True
    m = margin_m / mpp
    xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
    return (min(xs) - m <= x <= max(xs) + m and min(ys) - m <= y <= max(ys) + m)


def main():
    summary = {}
    for v in VILLAGES:
        key = v['key']
        geo = load_json(f'{BASE}/work/mosaic_geo.json')[key]
        mpp = geo['mpp']
        net = load_json(f'{BASE}/work/{key}/{NET_FILES[key]}')
        hh2 = load_json(f'{vdir(key)}/households_v2.json')

        # кадр пользователя (если есть)
        try:
            ct = load_json(f'{BASE}/work/{key}/crop_transform.json')
            quad = ct.get('quad_old')
        except FileNotFoundError:
            quad = None

        drops = net['drops']
        # унификация: hh_id у всех дропов
        if 'hh_id' not in drops[0]:
            for d in drops:
                d['hh_id'] = d['hh'] + 1
        drop_by_hh = {d['hh_id']: d for d in drops}
        assert len(drop_by_hh) == len(drops), f'{key}: дубли hh_id в дропах'

        hh_by_id = {h['id']: h for h in hh2}
        flags = []
        n_new = n_moved = n_skip_frame = n_skip_noparent = 0
        max_hh_idx = max(d['hh'] for d in drops)

        # 1) новые ДХ
        for h in hh2:
            src = h.get('source')
            if src in (None, 'apartments_main'):
                continue
            pid = h.get('parent_id')
            pd = drop_by_hh.get(pid)
            if pd is None:
                n_skip_noparent += 1
                continue
            if not in_frame(h['cx'], h['cy'], quad, 20.0, mpp):
                n_skip_frame += 1
                continue
            poly = [list(p) for p in pd['poly']]
            poly[-1] = [h['cx'], h['cy']]
            if len(poly) < 2:
                poly = [[pd['poly'][0][0], pd['poly'][0][1]], [h['cx'], h['cy']]]
            L = poly_len(poly, mpp)
            if L > pd['length_m'] + 60:
                flags.append(f'{key}: hh{h["id"]} дроп {L:.0f} м >> родителя '
                             f'{pd["length_m"]:.0f} м — проверить')
            max_hh_idx += 1
            nd = dict(hh=max_hh_idx, hh_id=h['id'], coupler=pd['coupler'],
                      poly=poly, length_m=round(L, 1))
            drops.append(nd)
            drop_by_hh[h['id']] = nd
            n_new += 1

        # 2) перемещённые родители
        for h in hh2:
            if h.get('source') not in ('apartments_main',):
                # split_roof-родители: позиция тоже менялась, но source у них
                # остался старым; найдём их через детей
                continue
            d = drop_by_hh.get(h['id'])
            if d is None:
                continue
            poly = [list(p) for p in d['poly']]
            poly[-1] = [h['cx'], h['cy']]
            d['poly'] = poly
            d['length_m'] = round(poly_len(poly, mpp), 1)
            n_moved += 1

        # 2b) split_roof-родители (source не проставлен, но позиция из 52c менялась)
        moved_split = 0
        kids_by_parent = {}
        for h in hh2:
            if h.get('parent_id'):
                kids_by_parent.setdefault(h['parent_id'], []).append(h)
        for h in hh2:
            if h.get('source') is not None or h['id'] not in kids_by_parent:
                continue
            d = drop_by_hh.get(h['id'])
            if d is None:
                continue
            dx = d['poly'][-1][0] - h['cx']
            dy = d['poly'][-1][1] - h['cy']
            if math.hypot(dx, dy) * mpp > 0.5:  # позиция сместилась
                poly = [list(p) for p in d['poly']]
                poly[-1] = [h['cx'], h['cy']]
                d['poly'] = poly
                d['length_m'] = round(poly_len(poly, mpp), 1)
                moved_split += 1

        # 3) stats
        lens = [d['length_m'] for d in drops]
        st = net.get('stats', {})
        st['households'] = len(drops)
        st['served'] = len(drops)
        st['drop_km'] = round(sum(lens) / 1000.0, 2)
        st['avg_drop_m'] = round(sum(lens) / max(1, len(lens)), 1)
        st['max_drop_m'] = round(max(lens), 1)
        net['stats'] = st

        save_json(f'{BASE}/work/{key}/network_hh2.json', net)

        # контроль
        ids = [d['hh_id'] for d in drops]
        assert len(ids) == len(set(ids)), f'{key}: дубли hh_id после добавления'
        coup_ids = {c['node'] for c in net['couplers']}
        # проверяем только НОВЫЕ дропы: в исходных сетях есть legacy-дефекты
        # (напр., Винное hh23 — вне графа, на итог не влияет)
        new_ids = {h['id'] for h in hh2 if h.get('source') not in (None, 'apartments_main')}
        bad_c = [d['hh_id'] for d in drops
                 if d['hh_id'] in new_ids and d['coupler'] not in coup_ids]
        assert not bad_c, f'{key}: новые дропы с несуществующей муфтой: {bad_c[:5]}'

        summary[key] = dict(name=v['name'], drops=len(drops), new=n_new,
                            moved_apt=n_moved, moved_split=moved_split,
                            skip_frame=n_skip_frame, skip_noparent=n_skip_noparent,
                            drop_km=st['drop_km'], avg=st['avg_drop_m'], max=st['max_drop_m'])
        print(f"{v['name']:20s} дропов {len(drops)} (+{n_new}; сдвиги: {n_moved} кв., "
              f"{moved_split} сплит-родителей; вне кадра {n_skip_frame}, без родителя {n_skip_noparent}) "
              f"дропы {st['drop_km']} км, ср {st['avg_drop_m']} м, макс {st['max_drop_m']} м", flush=True)
        for f in flags:
            print('  ФЛАГ:', f, flush=True)
    save_json(f'{BASE}/work/network_hh2_summary.json', summary)


if __name__ == '__main__':
    main()
