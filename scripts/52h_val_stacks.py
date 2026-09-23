# -*- coding: utf-8 -*-
"""
Шаг 52h (Task 47). Контрольные стеки для валидации парного режима VLM:
40 уже верифицированных кандидатов Верхнеберезовки (эталон — одиночные
вердикты Task 46) склеиваются в 20 стеков со стратификацией
принятые/отклонённые. Совпадение стек-вердиктов с эталоном >= 90-95%
допускает парный режим для остатка (экономия квоты вдвое).

Выход: work/hh2/verhneberezovka/val_stacks.json + val_*.jpg
"""
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

BASE = '/home/z/my-project'
KEY = 'verhneberezovka'
D = f'{BASE}/work/hh2/{KEY}'
SEP_H, LABEL_H = 14, 54
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font = ImageFont.truetype(FONT, 34)

N_ACCEPT = 20   # принятых сплитов (в 52c прошли гейт)
N_REJECT = 20   # отклонённых


def gate_pass(v):
    """Гейт 52c: кандидат даёт второе владение."""
    if not v.get('ok'):
        return False
    np_ = v.get('n_properties')
    if not isinstance(np_, (int, float)) or np_ < 2:
        return False
    if bool(v.get('annex')) and not v.get('fence_perp_center'):
        return False
    return bool(v.get('fence_perp_center') or v.get('fence_extends')
                or v.get('seam_visible') or v.get('fence_between'))


def make_stack(p1, p2, out, n1, n2):
    im1 = Image.open(p1).convert('RGB')
    im2 = Image.open(p2).convert('RGB')
    w = max(im1.width, im2.width, 200)
    h1 = LABEL_H + int(im1.height * w / im1.width)
    h2 = LABEL_H + int(im2.height * w / im2.width)
    canvas = Image.new('RGB', (w, h1 + SEP_H + h2), (255, 255, 255))
    dr = ImageDraw.Draw(canvas)
    canvas.paste(im1.resize((w, h1 - LABEL_H)), (0, LABEL_H))
    dr.rectangle([0, 0, w, LABEL_H], fill=(16, 16, 16))
    dr.text((12, 8), f'FRAGMENT 1 (TOP) - {n1}', fill=(255, 255, 60), font=font)
    dr.rectangle([0, h1, w, h1 + SEP_H], fill=(255, 255, 255))
    canvas.paste(im2.resize((w, h2 - LABEL_H)), (0, h1 + SEP_H + LABEL_H))
    dr.rectangle([0, h1 + SEP_H, w, h1 + SEP_H + LABEL_H], fill=(16, 16, 16))
    dr.text((12, h1 + SEP_H + 8), f'FRAGMENT 2 (BOTTOM) - {n2}', fill=(60, 255, 60), font=font)
    canvas.save(out, quality=88)


def main():
    cands = json.load(open(f'{D}/candidates.json', encoding='utf-8'))
    verd = json.load(open(f'{D}/verdicts.json', encoding='utf-8'))
    by_cid = {c['cid']: c for c in cands}
    accepted, rejected = [], []
    for cid, v in verd.items():
        if not v.get('ok') or cid not in by_cid:
            continue
        if by_cid[cid]['type'] not in ('A', 'B'):
            continue
        (accepted if gate_pass(v) else rejected).append(cid)
    rng = random.Random(47)
    rng.shuffle(accepted)
    rng.shuffle(rejected)
    sel_a = accepted[:N_ACCEPT]
    sel_r = rejected[:N_REJECT]
    print(f'эталон: принято {len(accepted)}, отклонено {len(rejected)}; берём {len(sel_a)}+{len(sel_r)}')
    # перемешиваем и паруем принятых с отклонёнными и между собой
    pool = sel_a + sel_r
    rng.shuffle(pool)
    manifest = {}
    for i in range(0, len(pool) - 1, 2):
        c1, c2 = pool[i], pool[i + 1]
        f1, f2 = f'{D}/cand_{c1}.jpg', f'{D}/cand_{c2}.jpg'
        if not (os.path.exists(f1) and os.path.exists(f2)):
            continue
        sf = f'val_{c1}__{c2}.jpg'
        make_stack(f1, f2, f'{D}/{sf}', c1, c2)
        manifest[sf] = dict(cids=[c1, c2])
    json.dump(manifest, open(f'{D}/val_stacks.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(dict(gate={c: gate_pass(verd[c]) for c in pool}),
              open(f'{D}/val_gate_ref.json', 'w', encoding='utf-8'), indent=1)
    print('контрольных стеков:', len(manifest))


if __name__ == '__main__':
    main()
