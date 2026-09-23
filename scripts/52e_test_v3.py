# -*- coding: utf-8 -*-
"""
Шаг 52a-test (Task 46). Проверка НОВЫХ критериев сплита (v3, геометрия) на
меченом датасете Верхнеберезовки (86 A-кандидатов с VLM-вердиктами, Task 45):
  - recall: сколько из 40 подтверждённых (n_properties>=2) остались кандидатами;
  - фильтрация: сколько из 46 отклонённых (пристройки/одиночные) отсечены CV;
  - новизна: сколько БОЛЬШИХ зданий, не проходивших старый хроматический фильтр,
    теперь кандидаты (одноцветные пары — раньше невидимые).
Кропы НЕ перезаписываются, verdicts НЕ трогаются.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from importlib import import_module
from common import vdir, load_json

BASE = '/home/z/my-project'
lib = import_module('52_hh_refine_lib')

key = 'verhneberezovka'
R = lib.reproduce_04f(key)
mos, mpp, blds = R['mos'], R['mpp'], R['blds']

old = load_json(f'{BASE}/work/hh2/{key}/candidates.json')
verd = load_json(f'{BASE}/work/hh2/{key}/verdicts.json')

old_A = {c['hh_id']: c for c in old if c['type'] == 'A'}
confirmed = set()
rejected = set()
for c in old:
    if c['type'] != 'A':
        continue
    vd = verd.get(c['cid'], {})
    if not vd.get('ok'):
        continue
    if (vd.get('n_properties') or 0) >= 2:
        confirmed.add(c['hh_id'])
    else:
        rejected.add(c['hh_id'])

# прогон новых критериев по всем главным зданиям ДХ
new_A = {}
for yinfo in R['yards_hh']:
    hid, mi = yinfo['hh_id'], yinfo['main']
    if hid is None:
        continue
    main_b = blds[mi]
    info = lib.roof_split_info(mos, main_b['poly'], mpp)
    if info:
        new_A[hid] = info

print(f'ВБ: старые A-кандидаты {len(old_A)}, подтверждено VLM {len(confirmed)}, '
      f'отклонено {len(rejected)}')
print(f'Новые критерии (v3): кандидатов {len(new_A)}')
lost = confirmed - set(new_A)
kept_conf = confirmed & set(new_A)
filt = rejected - set(new_A)
kept_rej = rejected & set(new_A)
print(f'RECALL подтверждённых: {len(kept_conf)}/{len(confirmed)} '
      f'({100*len(kept_conf)/max(1,len(confirmed)):.0f}%); потеряно: {sorted(lost)}')
print(f'Отсечено отклонённых (анти-пристройка и пр.): {len(filt)}/{len(rejected)}; '
      f'остались на VLM: {sorted(kept_rej)}')
new_only = sorted(set(new_A) - set(old_A))
print(f'НОВЫЕ кандидаты (ранее невидимые, в т.ч. одноцветные пары): {len(new_only)}')
prio = [new_A[h].get('priority') for h in new_only]
tc = sum(1 for h in new_only if new_A[h].get('two_color'))
sm = sum(1 for h in new_only if new_A[h].get('seam_frac', 0) >= lib.SEAM_FRAC_MIN)
print(f'  из них two_color={tc}, со швом={sm}, приоритеты: '
      f'P1={sum(1 for p in prio if p==1)} P2={sum(1 for p in prio if p==2)} P3={sum(1 for p in prio if p==3)}')
# примеры потерь с причинами
for h in sorted(lost)[:12]:
    main_b = None
    for yinfo in R['yards_hh']:
        if yinfo['hh_id'] == h:
            main_b = blds[yinfo['main']]
            break
    if main_b is None:
        continue
    x0, y0, x1, y1 = min(p[0] for p in main_b['poly']), min(p[1] for p in main_b['poly']), \
                     max(p[0] for p in main_b['poly']), max(p[1] for p in main_b['poly'])
    W_, H_ = x1 - x0, y1 - y0
    bbox_m2 = W_ * H_ * mpp * mpp
    print(f'  ПОТЕРЯН hh{h}: bbox={bbox_m2:.0f} м² (порог {lib.MIN_BBOX_M2}), '
          f'long={max(W_,H_)*mpp:.1f} м (порог {lib.MIN_LONG_M})')
