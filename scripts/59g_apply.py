#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59g: правка по altay3.pdf заказчика («Это многоквартирный дом»).

Идентификация: скриншот заказа привязан к карте 05 Пригородного (визуальное
сравнение СОВПАДАЕТ — здание с 3-секционной крышей: рыжие торцы + светлая
середина, дроп от муфты 108 на магистральном кабеле, квадрат зоны 1).
OSM bid=688327687, 10.9x25.7 м, полный прямоугольник, lv=1 (двускатная
крыша, ширина 10.8 м, тени как у 1-эт соседей; VLM 85%).

Формула пайплайна (Task 53): N = max(2, min(round(min(lv*S_bbox/55,
lv*подъезды*4)), 400)); S_bbox=279.5, подъезды=round(25.7/28)=1 -> N=4.
Прецедент 54q: первый существующий дроп сохраняется, лишние удаляются,
остальные N-1 добавляются вдоль длинной оси (placeholder: coupler=None,
52d перепривяжет к ближайшим муфтам)."""
import json
import shutil
import sys
from pathlib import Path

BASE = Path('/home/z/my-project')
NP = BASE / 'work/prigorodnoe/network_hh2.json'
BID = 688327687
N = 4
POS = [(3832.03, 4272.30), (3832.03, 4285.77),
       (3832.03, 4299.24), (3832.03, 4312.72)]
KEEP_HH = 90          # первый (мин. hh_id) из существующих
REMOVE_HH = [384]     # второй существующий (лишний при квартирной схеме)


def main():
    net = json.load(open(NP, encoding='utf-8'))
    drops = net['drops']
    n0 = len(drops)

    here = [d for d in drops if d['hh_id'] in (KEEP_HH,) + tuple(REMOVE_HH)]
    assert len(here) == 2, f'ожидалось 2 дропа здания, найдено {len(here)}'
    keep = [d for d in drops if d['hh_id'] == KEEP_HH][0]
    drops = [d for d in drops if d['hh_id'] not in REMOVE_HH]

    max_id = max(d['hh_id'] for d in drops)
    max_hh = max(d['hh'] for d in drops)
    for p in POS[1:]:
        max_id += 1
        max_hh += 1
        drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                          poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))

    net['drops'] = drops
    st = net.get('stats', {})
    st['served'] = len(drops)
    st['remark_task59'] = ('altay3: bid 688327687 (Пригородное) — '
                           'многоквартирный 1-эт дом по слову заказчика, '
                           '2 -> 4 ДХ (формула lv=1, S=279.5, подъезды=1)')
    net['stats'] = st

    shutil.copy(NP, NP.with_suffix('.json.bak_t59'))
    json.dump(net, open(NP, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'Пригородное: дропов {n0} -> {len(drops)} (+{len(drops) - n0}); '
          f'сохранён hh{KEEP_HH} (len {keep["length_m"]:.1f} м), '
          f'удалён hh{REMOVE_HH[0]}; добавлены hh_id '
          f'{[d["hh_id"] for d in drops if d["poly"][0] == d["poly"][-1] and d["length_m"] == 0.0][-3:]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
