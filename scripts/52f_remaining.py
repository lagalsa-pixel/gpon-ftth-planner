# -*- coding: utf-8 -*-
"""Task 47. Остаток VLM-верификации по сёлам (с учётом SKIP_AREA_C как в 52b).
Выход: строки <key> <todo>; последняя строка TOTAL <n>. Код выхода 0 — всё готово."""
import json, os
BASE = '/home/z/my-project'
KEYS = ['prigorodnoe', 'altaiskiy', 'vinnoe', 'solnechnoe', 'perevalnoe', 'verhneberezovka']
SKIP_AREA_C = {'solnechnoe', 'perevalnoe', 'vinnoe'}
total = 0
for k in KEYS:
    d = f'{BASE}/work/hh2/{k}'
    cp = f'{d}/candidates.json'
    if not os.path.exists(cp):
        continue
    cands = json.load(open(cp))
    try:
        v = json.load(open(f'{d}/verdicts.json'))
        ok_ids = {cid for cid, x in v.items() if x.get('ok')}
    except Exception:
        ok_ids = set()
    todo = [c for c in cands if c['cid'] not in ok_ids
            and not (c['type'] == 'C' and k in SKIP_AREA_C
                     and not (c.get('lv', 0) >= 2 or c.get('tag') == 'apartments'))]
    total += len(todo)
    print(f'{k} {len(todo)}')
print(f'TOTAL {total}')
raise SystemExit(0 if total == 0 else 3)
