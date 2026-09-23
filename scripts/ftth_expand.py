#!/usr/bin/env python3
"""Сверка числа домохозяйств с таблицей СНП ВКО и добавление недостающих абонентов.

Логика: в сёлах, где выявлено ДХ меньше официального числа, недостающие абоненты
добавляются как дополнительные точки рядом с выявленными домохозяйствами
(смещение 13-19 м в свободную сторону, без наложений) — «ещё один абонент
рядом с идентифицированным». Выход: {key}_hh_full.json."""
import json, math, os, sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
HH_DIR = os.path.join(BASE, 'ftth_out')

# Минимальные расстояния размещения доп. абонентов
OFFSET_MIN_M = 13.0     # м от центроида выявленного ДХ
OFFSET_MAX_M = 19.0
MIN_DIST_M = 9.0        # м: не ближе этого к любому ДХ/доп. абоненту
EXTRA_PER_HH_CAP = 12   # защита от патологий


def local_frame(lat0):
    ky = 111132.0
    kx = 111320.0 * math.cos(math.radians(lat0))
    return ky, kx


def place_extras(hh_list, deficit, ky, kx, seed=42):
    """Расстановка deficit доп. абонентов рядом с выявленными ДХ (равномерно)."""
    n = len(hh_list)
    if deficit <= 0 or n == 0:
        return []
    deficit = min(deficit, n * EXTRA_PER_HH_CAP)
    base, rem = divmod(deficit, n)
    # индексы ДХ, получающих +1 сверх равномерного остатка (разнесённые по списку)
    extra_one = set()
    if rem:
        step = n / rem
        for j in range(rem):
            extra_one.add(min(n - 1, int(round(j * step))))
    rng = np.random.default_rng(seed)
    # существующие точки для контроля наложений (центроиды ДХ)
    all_xy = [(h['lat'] * ky, h['lon'] * kx) for h in hh_list]
    extras = []
    nxt = max((h.get('n', 0) for h in hh_list), default=0)
    for i, h in enumerate(hh_list):
        k_extra = base + (1 if i in extra_one else 0)
        for t in range(k_extra):
            placed = False
            ang0 = rng.uniform(0, 2 * math.pi)
            r = OFFSET_MIN_M + rng.uniform(0, OFFSET_MAX_M - OFFSET_MIN_M)
            for att in range(24):
                ang = ang0 + att * (math.pi / 6.0) * (0.5 + 0.5 * rng.uniform(0, 1))
                rr = r * (1.0 + 0.04 * att)
                la = h['lat'] + math.sin(ang) * rr / ky
                lo = h['lon'] + math.cos(ang) * rr / kx
                x, y = la * ky, lo * kx
                ok = True
                for (ox_, oy_) in all_xy:
                    if math.hypot(x - ox_, y - oy_) < MIN_DIST_M:
                        ok = False
                        break
                if ok:
                    nxt += 1
                    extras.append(dict(
                        type='extra', extra=True, lat=la, lon=lo, n=nxt,
                        parent=h.get('n'), polygons=[], main_area=None, n_bld=0,
                    ))
                    all_xy.append((x, y))
                    placed = True
                    break
            if not placed:
                # некуда — ставим с минимальным смещением всё равно
                ang = ang0 + math.pi
                la = h['lat'] + math.sin(ang) * OFFSET_MAX_M / ky
                lo = h['lon'] + math.cos(ang) * OFFSET_MAX_M / kx
                nxt += 1
                extras.append(dict(
                    type='extra', extra=True, lat=la, lon=lo, n=nxt,
                    parent=h.get('n'), polygons=[], main_area=None, n_bld=0,
                ))
                all_xy.append((la * ky, lo * kx))
    return extras


def main():
    from ftth_households import VILLAGES
    print(f"{'Село':<20}{'выявлено':>9}{'офиц.':>7}{'дефицит':>9}{'добавл.':>9}{'итого':>7}")
    tot_id = tot_exp = tot_add = 0
    for v in VILLAGES:
        key = v['key']
        hhj = json.load(open(os.path.join(HH_DIR, f'{key}_hh.json')))
        hh = hhj['households']
        for h in hh:
            h['extra'] = False
        n_id = len(hh)
        expected = hhj['expected']
        deficit = expected - n_id
        ky, kx = local_frame(v['lat'])
        extras = place_extras(hh, deficit, ky, kx, seed=42 + hash(key) % 1000)
        hh_full = hh + extras
        out = dict(hhj)
        out['n_identified'] = n_id
        out['n_added'] = len(extras)
        out['households'] = hh_full
        with open(os.path.join(HH_DIR, f'{key}_hh_full.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"{v['name']:<20}{n_id:>9}{expected:>7}{deficit:>9}{len(extras):>9}{len(hh_full):>7}"
              + ('  (избыток, без добавления)' if deficit < 0 else ''))
        tot_id += n_id; tot_exp += expected; tot_add += len(extras)
    print(f"{'ИТОГО':<20}{tot_id:>9}{tot_exp:>7}{tot_exp-tot_id:>9}{tot_add:>9}{tot_id+tot_add:>7}")


if __name__ == '__main__':
    main()
