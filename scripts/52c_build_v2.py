# -*- coding: utf-8 -*-
"""
Шаг 52c (v2, многоуровневый). Сборка households_v2.json.

Tier 1 — детерминированно (без VLM):
  многоэтажки по OSM: building=apartments ИЛИ (levels>=3 И площадь/этаж в
  разумных пределах). N квартир = min(этажей x площадь / 55,
  этажей x подъезды_оценка x 4), подъезды_оценка = round(длинная_сторона/28).
Tier 2 — по готовым VLM-вердиктам (work/hh2/<key>/verdicts.json):
  A: n_properties >= 2 И НЕ пристройка И есть признак раздела (забор у центра
     фасада / продолжение вглубь двора / стык крыш; legacy: fence_between) —
     критерии пользователя Task 46: цвет крыши не достаточен, решает
     ограждение перпендикулярно фасаду ближе к центру при одинаковой форме
     кровли (пристройка = меньший прямоугольник — отсекается);
  B: n_properties >= 2 -> новые ДХ на крупных зданиях кластера;
  C: apartment_block && residential -> N квартир (levels/entrances из вердикта).
Tier 3 — кандидаты без вердиктов: НЕ применяются (ждут квоту VLM),
  фиксируются в hh2_pending.json.

Выход: work/<key>/households_v2.json, work/hh2_summary.json, work/hh2_pending.json.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, vdir, load_json, save_json

BASE = '/home/z/my-project'
APT_M2_PER_FLAT = 55.0
APT_MAX = 400
SANE_FPF_MIN, SANE_FPF_MAX = 40.0, 3500.0   # м² этажа — отсев ошибок тегов


def px_to_geo(x, y, lat_ref, west, north, mpp):
    return (north - y * mpp / 111320,
            west + x * mpp / (111320 * math.cos(math.radians(lat_ref))))


def apt_n(lv, area_m2, long_m, levels_vlm=None, entrances_vlm=None):
    lv = max(1, int(levels_vlm or lv or 2))
    n_area = lv * area_m2 / APT_M2_PER_FLAT
    ent = entrances_vlm or max(1, round(long_m / 28.0))
    n_ent = lv * int(ent) * 4
    n = round(min(n_area, n_ent))
    return max(2, min(n, APT_MAX))


def facade_positions(cx, cy, w, h, mpp, n):
    if n <= 1:
        return [(cx, cy)]
    long_px, horiz = (w, True) if w >= h else (h, False)
    long_m = long_px * mpp
    spacing_m = min(6.0, long_m / (n + 1))
    return [((cx + (i - (n - 1) / 2.0) * spacing_m / mpp, cy) if horiz else
             (cx, cy + (i - (n - 1) / 2.0) * spacing_m / mpp)) for i in range(n)]


def main():
    summary = {}
    pending_all = {}
    for v in VILLAGES:
        key = v['key']
        geo = load_json(f'{BASE}/work/mosaic_geo.json')[key]
        mpp, west, north = geo['mpp'], geo['west'], geo['north']
        hh = load_json(f'{vdir(key)}/households.json')
        cands = load_json(f'{BASE}/work/hh2/{key}/candidates.json')
        try:
            verd = load_json(f'{BASE}/work/hh2/{key}/verdicts.json')
        except FileNotFoundError:
            verd = {}

        hh_by_id = {h['id']: dict(h) for h in hh}
        next_id = max(hh_by_id) + 1
        stats = dict(tier1_apt_buildings=0, tier1_apt_hh=0, tier2_split_roof=0,
                     tier2_split_yard=0, tier2_apt_buildings=0, tier2_apt_hh=0)
        pending = []
        flags = []

        # здания (для координат полигонов кластеров/многоэтажек)
        from importlib import import_module
        lib = import_module('52_hh_refine_lib')
        R = lib.reproduce_04f(key)
        blds = R['blds']

        for c in cands:
            cv = verd.get(c['cid'])
            has_v = bool(cv and cv.get('ok'))
            if c['type'] in ('A', 'B') and not has_v:
                pending.append(dict(cid=c['cid'], type=c['type'], hh_id=c.get('hh_id')))
                continue
            if c['type'] == 'A':
                nprop = cv.get('n_properties')
                if not isinstance(nprop, (int, float)) or nprop < 2:
                    continue
                # гейт Task 46: НЕ пристройка + признак раздела (забор/стык)
                is_annex = bool(cv.get('annex'))
                fence_sig = (cv.get('fence_perp_center') or cv.get('fence_extends')
                             or cv.get('seam_visible') or cv.get('fence_between'))
                if is_annex and not cv.get('fence_perp_center'):
                    continue  # пристройка (меньший прямоугольник) — не владение
                if not fence_sig:
                    continue  # нет ограждения/стыка — признаков двух владений нет
                parent = hh_by_id.get(c['hh_id'])
                if parent is None:
                    continue
                info = c['cv']
                p0, p1 = info['part0'], info['part1']
                d0 = math.hypot(parent['cx'] - p0['cx'], parent['cy'] - p0['cy'])
                d1 = math.hypot(parent['cx'] - p1['cx'], parent['cy'] - p1['cy'])
                near, far = (p0, p1) if d0 <= d1 else (p1, p0)
                parent['cx'], parent['cy'] = near['cx'], near['cy']
                parent['lat'], parent['lon'] = px_to_geo(near['cx'], near['cy'],
                                                         v['lat'], west, north, mpp)
                la2, lo2 = px_to_geo(far['cx'], far['cy'], v['lat'], west, north, mpp)
                hh_by_id[next_id] = dict(
                    id=next_id, cx=far['cx'], cy=far['cy'], lat=la2, lon=lo2,
                    n_bld=1, main_w=parent['main_w'], main_h=parent['main_h'],
                    main_src=parent['main_src'], parent_id=c['hh_id'],
                    source='split_roof', dE_ab=info['dE_ab'],
                    ratio=info.get('ratio'), prio=c.get('prio'),
                    fence_perp=cv.get('fence_perp_center'),
                    seam=cv.get('seam_visible'))
                next_id += 1
                stats['tier2_split_roof'] += 1
            elif c['type'] == 'B':
                nprop = cv.get('n_properties')
                if not isinstance(nprop, (int, float)) or nprop < 2:
                    continue
                parent = hh_by_id.get(c['hh_id'])
                if parent is None:
                    continue
                others = [j for j in c['bigs'] if j != c['bld']]
                others.sort(key=lambda j: -(blds[j]['w'] * blds[j]['h']))
                k = int(min(nprop - 1, len(others)))
                for j in others[:k]:
                    b = blds[j]
                    la, lo = px_to_geo(b['cx'], b['cy'], v['lat'], west, north, mpp)
                    hh_by_id[next_id] = dict(
                        id=next_id, cx=b['cx'], cy=b['cy'], lat=la, lon=lo,
                        n_bld=1, main_w=b['w'], main_h=b['h'], main_src=b['src'],
                        parent_id=c['hh_id'], source='split_yard',
                        fence_perp=cv.get('fence_perp_center'))
                    next_id += 1
                stats['tier2_split_yard'] += 1
            else:  # C
                b = blds[c['bld']]
                area = c['area_m2']
                long_m = max(b['w'], b['h']) * mpp
                lv = c.get('lv', 1) or 1
                fpf = area / max(1.0, lv)
                tag = c.get('tag')
                tier1 = (tag == 'apartments' or
                         (lv >= 3 and SANE_FPF_MIN <= fpf <= SANE_FPF_MAX))
                if tier1:
                    N = apt_n(lv, area, long_m)
                    if N > 100:
                        flags.append(f'{key} {c["cid"]}: N={N} (S={area:.0f}, lv={lv}) — проверить вручную')
                elif has_v and cv.get('apartment_block') and cv.get('residential'):
                    N = apt_n(lv, area, long_m, cv.get('levels'), cv.get('entrances'))
                else:
                    if not has_v:
                        pending.append(dict(cid=c['cid'], type='C', bld=c['bld'],
                                            hh_id=c.get('hh_id')))
                    continue
                parent_id = c.get('hh_id')
                pos = facade_positions(b['cx'], b['cy'], b['w'], b['h'], mpp, N)
                first = True
                tier = 'tier1' if tier1 else 'tier2'
                for (px_, py_) in pos:
                    la, lo = px_to_geo(px_, py_, v['lat'], west, north, mpp)
                    if first and parent_id and parent_id in hh_by_id:
                        p = hh_by_id[parent_id]
                        p.update(cx=px_, cy=py_, lat=la, lon=lo,
                                 source='apartments_main', apt_total=N, apt_tier=tier)
                        first = False
                        continue
                    hh_by_id[next_id] = dict(
                        id=next_id, cx=px_, cy=py_, lat=la, lon=lo,
                        n_bld=1, main_w=b['w'], main_h=b['h'], main_src=b['src'],
                        parent_id=parent_id, source='apartments',
                        apt_total=N, apt_tier=tier)
                    next_id += 1
                if tier1:
                    stats['tier1_apt_buildings'] += 1
                    stats['tier1_apt_hh'] += N
                else:
                    stats['tier2_apt_buildings'] += 1
                    stats['tier2_apt_hh'] += N
        del R

        out = sorted(hh_by_id.values(), key=lambda h: h['id'])
        save_json(f'{vdir(key)}/households_v2.json', out)
        pending_all[key] = pending
        summary[key] = dict(name=v['name'], excel=v['hh'], v1=len(hh), v2=len(out),
                            pending=len(pending), **stats,
                            dev_v1=round(100 * (len(hh) - v['hh']) / v['hh'], 1),
                            dev_v2=round(100 * (len(out) - v['hh']) / v['hh'], 1))
        print(f"{v['name']:20s} {len(hh)} -> {len(out)} ДХ (Excel {v['hh']}; "
              f"{summary[key]['dev_v1']:+.1f}% -> {summary[key]['dev_v2']:+.1f}%) | "
              f"T1: {stats['tier1_apt_buildings']} зд./+{stats['tier1_apt_hh']} кв. | "
              f"T2: сплиты {stats['tier2_split_roof']}+{stats['tier2_split_yard']}, "
              f"многоэт. {stats['tier2_apt_buildings']}/+{stats['tier2_apt_hh']} | "
              f"без вердикта: {len(pending)}", flush=True)
        for f in flags:
            print('  ФЛАГ:', f, flush=True)
    save_json(f'{BASE}/work/hh2_summary.json', summary)
    save_json(f'{BASE}/work/hh2_pending.json', pending_all)
    tp = sum(len(x) for x in pending_all.values())
    print(f'\nОжидают VLM (tier 3): {tp} кандидатов')


if __name__ == '__main__':
    main()
