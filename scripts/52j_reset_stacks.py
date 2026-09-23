# -*- coding: utf-8 -*-
"""Task 47 (продолжение). Сброс стековых вердиктов (stack:true) в verdicts.json
по всем сёлам — парный режим не прошёл валидацию (реальная согласованность
0,65 < 0,90; прежний отчёт 0,50/FP=0 был багом 52i gate_pass), эти вердикты
должны быть переверифицированы одиночными вызовами."""
import json

BASE = '/home/z/my-project/work/hh2'
for key in ['verhneberezovka', 'prigorodnoe', 'perevalnoe', 'solnechnoe', 'vinnoe', 'altaiskiy']:
    p = f'{BASE}/{key}/verdicts.json'
    try:
        v = json.load(open(p, encoding='utf-8'))
    except FileNotFoundError:
        continue
    drop = [cid for cid, x in v.items() if isinstance(x, dict) and x.get('stack')]
    for cid in drop:
        del v[cid]
    if drop:
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(v, f, ensure_ascii=False, indent=1)
        import os
        os.replace(tmp, p)
    print(f'{key}: сброшено {len(drop)} стековых вердиктов, осталось {len(v)}')
