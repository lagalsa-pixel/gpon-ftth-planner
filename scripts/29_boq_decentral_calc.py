# -*- coding: utf-8 -*-
"""
Шаг 29. Итоговый расчёт BoQ децентрализованной схемы D (зонные ОРШ, единый OLT).

Рекомендованная конфигурация по шагу 28: S_MIN = 15 волокно-км на доп. ОРШ
(экономический порог окупаемости шкафа), MIN_ZONE = 48 ДХ.

Выход: work/boq_decentral_data.json — структура зеркалит boq_data.json
(централизованная книга): model / villages (с зонами и материалами) / totals /
materials_total. Инварианты сверяются с централизованной книгой: ДХ, дропы,
трасса магистрали (топология не менялась).
"""
import json, math, importlib.util
from collections import defaultdict

BASE = '/home/z/my-project'

spec = importlib.util.spec_from_file_location('de28', f'{BASE}/scripts/28_decentral_explore.py')
de28 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de28)

Tree = de28.Tree
ceilr, decompose, roundup01 = de28.ceilr, de28.decompose, de28.roundup01
STD_FIBERS, ORSH_PORTS_ROW_ZONE = de28.STD_FIBERS, de28.ORSH_PORTS_ROW_ZONE

S_MIN_REC = 15.0
MIN_ZONE = de28.MIN_ZONE

VILLAGES_META = {
    'verhneberezovka': dict(num='01', name='Верхнеберезовка', raion='Глубоковский р-н', so='Верхнеберезовский с.о.',
                            dhx_excel=940, orsh_bld='здание пожарной части №26 (198 м²)'),
    'solnechnoe': dict(num='02', name='Солнечное', raion='Глубоковский р-н', so='Бобровский с.о.',
                       dhx_excel=366, orsh_bld='общественное здание в центре села (145,7 м²)'),
    'perevalnoe': dict(num='03', name='Перевальное', raion='Глубоковский р-н', so='Красноярский с.о.',
                       dhx_excel=339, orsh_bld='общественное здание в центре (417 м²)'),
    'vinnoe': dict(num='04', name='Винное', raion='Глубоковский р-н', so='Тарханский с.о.',
                   dhx_excel=490, orsh_bld='здание у перекрёстка в центре (96 м²)'),
    'prigorodnoe': dict(num='05', name='Пригородное', raion='г. Риддер', so='—',
                        dhx_excel=365, orsh_bld='нежилое здание у развилки дорог (84 м²)'),
    'altaiskiy': dict(num='06', name='Алтайский', raion='Глубоковский р-н', so='Алтайский с.о.',
                      dhx_excel=716, orsh_bld='здание на развилке дорог (156 м²)'),
}


def geo_of(t, node):
    """Геокоординаты узла дерева (аффинная привязка по якорю сети)."""
    net = json.load(open(f"{BASE}/work/{t.key}/{t.net if hasattr(t, 'net') else ''}")) \
        if False else None
    return None


def main():
    book_a = json.load(open(f'{BASE}/work/boq_data.json'))
    ba = {v['key']: v for v in book_a['villages']}

    out_villages = []
    print(f"{'Село':<18}{'ДХ':>5}{'зон':>5}{'ОРШ':>5}{'вол-км':>9}{'кабель':>8}{'спл.':>6}"
          f"{'сварки':>7}{'порты':>7}{'ср.маршр':>9}")
    for v in de28.VILLAGES:
        t = Tree(v)
        cuts, log = t.partition_greedy(S_MIN_REC)
        r = t.layout(cuts)

        # геокоординаты зон (аффинная привязка по якорю: px -> lat/lon)
        net = json.load(open(f"{BASE}/work/{t.key}/{v['net']}"))
        ax, ay = net['anchor']['x'], net['anchor']['y']
        alat, alon = net['anchor']['lat'], net['anchor']['lon']
        mlat = -t.mpp / 110574.0
        mlon = t.mpp / (111320.0 * math.cos(math.radians(alat)))

        zones_geo = []
        for z, zdata in zip([t.root] + list(cuts), r['zones']):
            zx, zy = z
            zones_geo.append(dict(
                **zdata,
                zone='ЦУ (корневая)' if z == t.root else 'зонный ОРШ',
                px=[round(zx, 1), round(zy, 1)],
                lat=round(alat + (zy - ay) * mlat, 6),
                lon=round(alon + (zx - ax) * mlon, 6),
            ))

        km = r['km_by_size']
        cable_km = {str(s): roundup01(km.get(str(s), 0.0) * 1.1) for s in STD_FIBERS
                    if km.get(str(s), 0.0) > 0}
        dh = t.dh_total
        drops_sorted = sorted(d['length_m'] for d in net['drops'])
        m = dict(
            orsh=r['orsh'],
            splitters=r['splitters'], olt_ports=r['splitters'],
            pigtails=dh + 2 * r['splitters'],
            mufty=r['mufty'],
            drop_cable_km=roundup01(t.drop_km * 1.05),
            abonent_boxes=dh,
            fast_conn=ceilr(dh * 1.1),
            splices=r['splices'], kdzs=r['splices'],
            suspend_kits=r['suspend_kits'],
            drop_anchors=2 * dh, drop_fix=6 * dh,
            orsh_ports=r['orsh_ports'],
        )
        m.update({f'cable_{s}': cable_km.get(str(s), 0.0) for s in STD_FIBERS})

        vv = dict(VILLAGES_META[t.key])
        vv.update(dict(
            key=t.key, net=v['net'],
            dhx_served=dh, couplers=t.n_couplers, mufty=r['mufty'],
            feeder_km=round(sum(L for _, _, L in t.edges) / 1000.0, 2),
            drop_km=round(t.drop_km, 2),
            avg_drop_m=round(sum(drops_sorted) / max(1, dh), 1),
            max_drop_m=round(drops_sorted[-1], 1),
            n_zones=r['n_zones'], orsh=r['orsh'],
            zones=zones_geo,
            fiber_km=r['fiber_km'], total_cable_km=r['cable_km_raw'],
            cable_km=cable_km, cable_km_raw=round(r['cable_km_raw'] * 1.1, 2),
            drop_cable_km=m['drop_cable_km'],
            orsh_ports=r['orsh_ports'], splitters64=r['splitters'],
            top_fibers=r['top_fibers'], max_parallel=r['max_parallel'],
            feeder_route_km=r['feeder_route_km'],
            routes=r['routes'],
            cut_log=log,
            materials=m,
        ))
        out_villages.append(vv)
        print(f"{vv['name']:<18}{dh:>5}{r['n_zones']:>5}{r['orsh']:>5}{r['fiber_km']:>9.1f}"
              f"{r['cable_km_raw'] * 1.1:>8.1f}{r['splitters']:>6}{r['splices']:>7}"
              f"{r['orsh_ports']:>7}{r['routes']['avg_m']:>9.0f}")

        # инварианты против централизованной книги
        a = ba[t.key]
        assert dh == a['dhx_served'], f'{t.key}: ДХ {dh} != {a["dhx_served"]}'
        assert abs(vv['drop_km'] - a['drop_km']) < 0.02, f'{t.key}: дропы'
        assert abs(vv['feeder_km'] - a['feeder_km']) < 0.02, f'{t.key}: трасса'
        assert sum(z['houses'] for z in zones_geo) == dh, f'{t.key}: сумма зон != ДХ'

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
    mat_tot = dict(mat_tot)

    data = dict(
        model=dict(
            scheme='D — децентрализованная: зонные ОРШ 1:64, единый узел OLT',
            s_min_km=S_MIN_REC, min_zone=MIN_ZONE,
            fiber_reserve=1.25, min_fibers=8, std_fibers=STD_FIBERS,
            cable_stock=1.10, drop_stock=1.05, suspend_per_km=30,
            drop_anchors_per_dh=2, drop_fix_per_dh=6, consum_stock=1.10,
            split_ratio=64,
            orsh_ports_row=[144, 288, 576, 864, 1152],
            orsh_ports_row_zone=ORSH_PORTS_ROW_ZONE,
            feeder_fibers='ceil(1.25 x сплиттеры зоны), совместно с распределением',
            note='Топология сетей не менялась; фидер ЦУ->зонные ОРШ по дереву сети; '
                 'межселённый транспорт до ЦУ — за рамками расчёта (как во всех схемах)',
        ),
        villages=out_villages, totals=tot, materials_total=mat_tot,
    )
    json.dump(data, open(f'{BASE}/work/boq_decentral_data.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('\nИТОГО D (S_MIN=15):')
    for k in ('dhx_served', 'n_zones', 'orsh', 'feeder_km', 'fiber_km', 'cable_km_raw',
              'drop_km', 'drop_cable_km', 'total_length_km', 'mufty', 'splitters64',
              'orsh_ports', 'splices'):
        print(f"  {k:>16}: {tot[k]}")
    print('  материалы:', json.dumps(mat_tot, ensure_ascii=False))
    print('\nИнварианты: ДХ/дропы/трасса = централизованной книге; сумма домов зон = ДХ. OK')
    print('Сохранено: work/boq_decentral_data.json')


if __name__ == '__main__':
    main()
