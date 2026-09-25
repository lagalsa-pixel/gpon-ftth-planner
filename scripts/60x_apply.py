#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60x: правка по altay3.pdf — ИСПРАВЛЕНИЕ ложной идентификации
Task 59 (Пригородное) на правильную: здание в селе АЛТАЙСКИЙ.

Идентификация (маск-матчинг символики, 6 элементов совпали с точностью
1-2 px на карте v4): квадрат ДХ hh131 на (3746,7826), муфта M24 севернее
(3746,7779), дроп 19.5 м вертикально вниз, кабель западнее муфты; здание —
вне-OSM барак ~29x13 м (3663-3741, 7789-7827), тёмная двускатная крыша,
3 крыльца + ряд окон по южному фасаду, 1 этаж (3 калиброванных VLM-прохода,
в т.ч. пара с известным 2-эт бараком 637127282 рядом). Это то самое здание,
что заказчик показывал в altay2 как img_12 («дуплекс», 1->2 ДХ, Task 55);
теперь слово заказчика: «Это многоквартирный дом».

Формула пайплайна (Task 53): N = max(2, min(round(min(lv*S_bbox/55,
lv*подъезды*4)), 400)); lv=1, S_bbox=29.4*13.5=397, подъезды=round(29.4/28)=1
-> N = min(7, 4) = 4.
Прецеденты 54q/59g: первый существующий дроп сохраняется, лишние удаляются,
остальные N-1 добавляются вдоль длинной оси (placeholder: coupler=None,
52d перепривяжет к ближайшим муфтам)."""
import json
import shutil
import sys
from pathlib import Path

BASE = Path('/home/z/my-project')
NP = BASE / 'work/altaiskiy/network_hh2.json'
N = 4
# вдоль южного фасада (y=7826), от существующего квадрата (3746) на запад,
# шаг 6.0 м = 15.7 px мозаики
POS = [(3746.0, 7826.0), (3730.3, 7826.0),
       (3714.6, 7826.0), (3698.9, 7826.0)]
KEEP_HH = 131          # существующий дроп от M24 (19.5 м)
REMOVE_HH = [702]      # «дуплекс» Task 55 (конец 3733,7826)


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
    new_ids = []
    for p in POS[1:]:
        max_id += 1
        max_hh += 1
        new_ids.append(max_id)
        drops.append(dict(hh=max_hh, hh_id=max_id, coupler=None,
                          poly=[[p[0], p[1]], [p[0], p[1]]], length_m=0.0))

    net['drops'] = drops
    st = net.get('stats', {})
    st['served'] = len(drops)
    st['remark_task60'] = ('altay3 (исправление Task 59): вне-OSM барак '
                           '3663-3741x7789-7827 (Алтайский, у M24) — '
                           'многоквартирный 1-эт дом по слову заказчика, '
                           '2 -> 4 ДХ (формула lv=1, S=397, подъезды=1)')
    net['stats'] = st

    shutil.copy(NP, NP.with_suffix('.json.bak_t60'))
    json.dump(net, open(NP, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'Алтайский: дропов {n0} -> {len(drops)}; сохранён hh{KEEP_HH} '
          f'(len {keep["length_m"]:.1f} м), удалён hh{REMOVE_HH[0]}; '
          f'добавлены hh_id {new_ids}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
