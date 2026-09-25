#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 58b: экспорт операторской страницы контроля/правки ДХ (HTML, без сервера).

Промежуточный этап конвейера «ручная корректировка оператором» (запрос
заказчика, Task 58): после программной идентификации домохозяйств
(детекция + VLM) оператор открывает страницу, сверяет ДХ по спутниковой
подложке и вносит правки:
  ➕ добавить ДХ (клик по месту — пропущенный дом);
  🗑 удалить ДХ (клик по квадрату — ложное срабатывание);
  🏇 МЖД квартиры (клик по зданию — группа квартирных ДХ пересоздаётся);
Правки выгружаются в corrections.json и применяются к network_hh2.json
скриптом 58c_apply_corrections.py (идемпотентно, с бэкапом), после чего
конвейер 52d -> 54 -> 48b -> ... -> QA пересчитывает сеть и материалы.

Выход: download/snp_vko/operator_review/<key>/{index.html, base.jpg, data.js}
Запуск: python3 58b_export_review_html.py <key>|all
"""
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image

BASE = Path('/home/z/my-project')
sys.path.insert(0, str(BASE / 'scripts'))
from common import VILLAGES, load_json  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
MAX_SIDE = 2400          # длинная сторона подложки (достаточно для контроля)
APT_MIN_N = 4            # как в 58a: МЖД-значки для групп квартир >= 4 ДХ


def g2p(la, lo, west, north, mpp):
    return ((lo - west) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (north - la) * 111132.0 / mpp)


def export(key):
    v = next(x for x in VILLAGES if x['key'] == key)
    vdir = BASE / 'work' / key
    out = BASE / 'download/snp_vko/operator_review' / key
    out.mkdir(parents=True, exist_ok=True)

    geo = load_json(BASE / 'work/mosaic_geo.json')[key]
    mpp, west, north = geo['mpp'], geo['west'], geo['north']

    # подложка: кадр пользователя (кроп) или полная мозаика
    if os.path.exists(vdir / 'crop_transform.json'):
        tr = load_json(vdir / 'crop_transform.json')
        M, img_path = tr['M_inv'], tr['new_image']
        if not os.path.isabs(img_path):
            img_path = str(BASE / img_path)
    else:
        M, img_path = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], str(vdir / 'mosaic.jpg')

    im = Image.open(img_path).convert('RGB')
    ds = min(1.0, MAX_SIDE / max(im.size))
    if ds < 1.0:
        im = im.resize((max(1, round(im.width * ds)), max(1, round(im.height * ds))),
                       Image.LANCZOS)
    im.save(out / 'base.jpg', quality=82, subsampling=1)
    print(f'  base.jpg {im.size} (ds={ds:.3f})')

    # дропы (финальная сеть, мозаичные координаты)
    net = load_json(vdir / 'network_hh3.json')
    drops = [dict(i=d['hh_id'],
                  p=[[round(x, 1), round(y, 1)] for x, y in d['poly']],
                  len=round(d.get('length_m', 0.0), 1))
             for d in net['drops']]
    couplers = [dict(x=round(c['x'], 1), y=round(c['y'], 1))
                for c in net['couplers']]

    # здания OSM (в зоне кадра, как в 52c reproduce)
    osm = load_json(vdir / 'osm.json')
    buildings = []
    for b in osm['buildings']:
        pts = [g2p(la, lo, west, north, mpp) for la, lo in b['poly']]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        buildings.append(dict(
            id=b['id'], c=[round(cx, 1), round(cy, 1)],
            w=round((max(xs) - min(xs)) * mpp, 1),
            h=round((max(ys) - min(ys)) * mpp, 1),
            p=[[round(x, 1), round(y, 1)] for x, y in pts],
            tags={k: b['tags'][k] for k in ('building', 'building:levels')
                  if isinstance(b.get('tags'), dict) and k in b['tags']}))

    # МЖД-группы (значки, как на карте)
    mzd = []
    mg_path = vdir / 'mzd_groups.json'
    if os.path.exists(mg_path):
        for g in load_json(mg_path):
            if g.get('kind') == 'apartment':
                mzd.append(dict(bid=g['bid'], cx=g['cx'], cy=g['cy'],
                                n=g['n'], hh_ids=g['hh_ids']))

    data = dict(key=key, name=v['name'], mpp=mpp, ds=round(ds, 4), M=M,
                drops=drops, couplers=couplers, buildings=buildings, mzd=mzd)
    (out / 'data.js').write_text(
        'const DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';',
        encoding='utf-8')
    print(f'  data.js: дропов {len(drops)}, муфт {len(couplers)}, '
          f'зданий {len(buildings)}, МЖД {len(mzd)}')

    tpl = (BASE / 'scripts/58b_review_template.html').read_text(encoding='utf-8')
    (out / 'index.html').write_text(
        tpl.replace('{{VILLAGE_NAME}}', v['name']), encoding='utf-8')
    print(f'  index.html -> {out}')


def main():
    keys = sys.argv[1:] if len(sys.argv) > 1 else ['all']
    if keys == ['all']:
        keys = [v['key'] for v in VILLAGES]
    for key in keys:
        print(f'== {key} ==')
        export(key)
    print('\nГотово:', len(keys), 'сёл -> download/snp_vko/operator_review/')


if __name__ == '__main__':
    main()
