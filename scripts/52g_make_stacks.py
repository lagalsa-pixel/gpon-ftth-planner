# -*- coding: utf-8 -*-
"""
Шаг 52g (Task 47). Генерация парных стеков кандидатов для экономии VLM-квоты:
два кандидата склеиваются в одно изображение (верх/низ, разделитель, метки 1/2),
один вызов VLM верифицирует оба. Паруются только однотипные A/A и B/B
(приоритетный порядок как в 52b: B -> A prio 1/2 -> A prio 3; C — одиночные).

Выход: work/hh2/<key>/stack_<cid1>__<cid2>.jpg + work/hh2/<key>/stacks.json
  {stack_file: {cids: [cid1, cid2], type: 'A'|'B'}}
Идемпотентно: учитывает уже готовые вердикты (в стек не попадают).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
KEYS = ['prigorodnoe', 'altaiskiy', 'vinnoe', 'solnechnoe', 'perevalnoe', 'verhneberezovka']
SKIP_AREA_C = {'solnechnoe', 'perevalnoe', 'vinnoe'}
SEP_H = 14          # белый разделитель, px
LABEL_H = 54        # полоса метки сверху каждой половины
MAX_W = 1400        # нормировка ширины (апскейл мелких кропов не делаем)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

try:
    font = ImageFont.truetype(FONT, 34)
except Exception:
    font = ImageFont.load_default()


def todo_list(key):
    d = f'{BASE}/work/hh2/{key}'
    cands = json.load(open(f'{d}/candidates.json', encoding='utf-8'))
    try:
        v = json.load(open(f'{d}/verdicts.json', encoding='utf-8'))
        ok_ids = {cid for cid, x in v.items() if x.get('ok')}
    except FileNotFoundError:
        ok_ids = set()
    todo = [c for c in cands if c['cid'] not in ok_ids
            and not (c['type'] == 'C' and key in SKIP_AREA_C
                     and not (c.get('lv', 0) >= 2 or c.get('tag') == 'apartments'))]
    def po(c):
        if c['type'] == 'B':
            return 0
        if c['type'] == 'A':
            return c.get('prio') or 3
        return 4
    todo.sort(key=po)
    return todo


def make_stack(p1, p2, out, n1, n2):
    im1 = Image.open(p1).convert('RGB')
    im2 = Image.open(p2).convert('RGB')
    w = max(im1.width, im2.width, 200)
    w = min(w, MAX_W)
    h1 = LABEL_H + int(im1.height * w / im1.width)
    h2 = LABEL_H + int(im2.height * w / im2.width)
    canvas = Image.new('RGB', (w, h1 + SEP_H + h2), (255, 255, 255))
    dr = ImageDraw.Draw(canvas)
    # половина 1
    r1 = im1.resize((w, h1 - LABEL_H))
    canvas.paste(r1, (0, LABEL_H))
    dr.rectangle([0, 0, w, LABEL_H], fill=(16, 16, 16))
    dr.text((12, 8), f'FRAGMENT 1 (TOP) - {n1}', fill=(255, 255, 60), font=font)
    # разделитель
    dr.rectangle([0, h1, w, h1 + SEP_H], fill=(255, 255, 255))
    # половина 2
    r2 = im2.resize((w, h2 - LABEL_H))
    canvas.paste(r2, (0, h1 + SEP_H + LABEL_H))
    dr.rectangle([0, h1 + SEP_H, w, h1 + SEP_H + LABEL_H], fill=(16, 16, 16))
    dr.text((12, h1 + SEP_H + 8), f'FRAGMENT 2 (BOTTOM) - {n2}', fill=(60, 255, 60), font=font)
    canvas.save(out, quality=88)
    return canvas.size


def main():
    total_pairs = 0
    for key in KEYS:
        d = f'{BASE}/work/hh2/{key}'
        if not os.path.exists(f'{d}/candidates.json'):
            continue
        todo = todo_list(key)
        # пары однотипных A/A, B/B (C не стекуем)
        by_type = {'A': [c for c in todo if c['type'] == 'A'],
                   'B': [c for c in todo if c['type'] == 'B']}
        manifest = {}
        for t, lst in by_type.items():
            for i in range(0, len(lst) - 1, 2):
                c1, c2 = lst[i], lst[i + 1]
                f1 = f'{d}/cand_{c1["cid"]}.jpg'
                f2 = f'{d}/cand_{c2["cid"]}.jpg'
                if not (os.path.exists(f1) and os.path.exists(f2)):
                    continue
                sf = f'stack_{c1["cid"]}__{c2["cid"]}.jpg'
                out = f'{d}/{sf}'
                if not os.path.exists(out):        # уже собранные не пересобираем
                    make_stack(f1, f2, out, c1['cid'], c2['cid'])
                manifest[sf] = dict(cids=[c1['cid'], c2['cid']], type=t)
                total_pairs += 1
        json.dump(manifest, open(f'{d}/stacks.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        n_single = len([c for c in todo if c['type'] == 'C'])
        print(f'{key}: пар {len(manifest)}, одиночных C {n_single}, todo {len(todo)}')
    print('всего пар:', total_pairs)


if __name__ == '__main__':
    main()
