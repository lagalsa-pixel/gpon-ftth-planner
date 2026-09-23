# -*- coding: utf-8 -*-
"""Тест 1: сверка boq-стадии конвейера с эталоном boq_decentral_data.json (схема D)."""
import json

ref = json.load(open('/home/z/my-project/work/boq_decentral_data.json', encoding='utf-8'))
new = json.load(open('/home/z/my-project/work/boq_total.json', encoding='utf-8'))
rmap = {v['key']: v for v in ref['villages']}

fails = 0
def chk(name, a, b, tol=0.0):
    global fails
    ok = (abs(a - b) <= tol) if isinstance(a, (int, float)) else (a == b)
    if not ok:
        fails += 1
        print(f'  FAIL {name}: new={a} ref={b}')
    return ok

print('Построчно по сёлам (схема D):')
for v in new['villages']:
    r = rmap[v['key']]
    chk(f"{v['key']}.dhx", v['dhx_served'], r['dhx_served'])
    chk(f"{v['key']}.n_zones", v['n_zones'], r['n_zones'])
    chk(f"{v['key']}.orsh", v['orsh'], r['orsh'])
    chk(f"{v['key']}.fiber_km", v['fiber_km'], r['fiber_km'], 0.05)
    chk(f"{v['key']}.cable_km_raw", v['cable_km_raw'], r['cable_km_raw'], 0.05)
    chk(f"{v['key']}.drop_cable_km", v['drop_cable_km'], r['drop_cable_km'], 0.05)
    chk(f"{v['key']}.splitters", v['splitters64'], r['splitters64'])
    chk(f"{v['key']}.mufty", v['mufty'], r['mufty'])
    chk(f"{v['key']}.splices", v['materials']['splices'], r['materials']['splices'])
    chk(f"{v['key']}.orsh_ports", v['orsh_ports'], r['orsh_ports'])
    # зоны: состав (ДХ по зонам)
    znew = [z['houses'] for z in v['zones']]
    zref = [z['houses'] for z in r['zones']]
    chk(f"{v['key']}.zone_houses", znew, zref)
    # материалы
    for k2 in ('drop_cable_km', 'fast_conn', 'abonent_boxes', 'drop_anchors', 'drop_fix'):
        chk(f"{v['key']}.m.{k2}", v['materials'][k2], r['materials'][k2], 0.05)
    for s in (8, 12, 16, 24, 32, 48, 64, 72, 96):
        chk(f"{v['key']}.cable_{s}", v['materials'].get(f'cable_{s}', 0.0),
            r['materials'].get(f'cable_{s}', 0.0), 0.05)

print('Итоги:')
for k2 in ('dhx_served', 'n_zones', 'orsh', 'fiber_km', 'drop_km', 'drop_cable_km',
           'splitters64', 'orsh_ports', 'splices', 'mufty'):
    chk(f'tot.{k2}', new['totals'][k2], ref['totals'][k2], 0.1)
# scheme A totals
chk('tot.fiber_km_a', new['totals']['fiber_km_a'], 4375.1, 0.1)

print(f"\n{'ВСЕ ЗНАЧЕНИЯ СХОДЯТСЯ' if fails == 0 else f'РАСХОЖДЕНИЙ: {fails}'}")
