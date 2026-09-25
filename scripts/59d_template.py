#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 59d: шаблон-матчинг здания (3-секционная крыша) по 7 картам.
Масштабы выведены из размеров элементов аннотаций скриншота:
квадрат ДХ 26 px, муфта 36 px, кабель 21 px.
  crop-сёла (квадрат 17 px): zoom ~1.5
  ВБ (квадрат 9 px):        zoom ~2.9
  Топольное (квадрат 7 px): zoom ~3.7
Шаблон: здание со скриншота, 4 поворота, сетка масштабов ±20%."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

BASE = Path('/home/z/my-project')
DIR = BASE / 'work/altay3'

# (имя, путь, mpp-карты, zoom-гипотеза)
TARGETS = [
    ('ВБ (map01)', DIR / 'map01_half.jpg', 0.763, 2.9),
    ('Солнечное (map02)', DIR / 'map02_v8.jpg', None, 1.5),
    ('Перевальное (map03)', DIR / 'map03_half.jpg', None, 1.5),
    ('Винное (map04)', DIR / 'map04_half.jpg', None, 1.5),
    ('Пригородное (map05)', DIR / 'map05_v8.jpg', None, 1.5),
    ('Алтайский (map06)', DIR / 'map06_v8.jpg', None, 1.5),
    ('Топольное (map07)', DIR / 'map07_half.jpg', 0.598, 3.7),
]
TEMPLATE_BOX = (115, 100, 408, 280)     # x0, y0, x1, y1 здания


def main():
    fig = cv2.imread(str(DIR / 'img_9_p1.png'), cv2.IMREAD_GRAYSCALE)
    x0, y0, x1, y1 = TEMPLATE_BOX
    tpl0 = fig[y0:y1, x0:x1]
    print(f'шаблон {tpl0.shape[1]}x{tpl0.shape[0]}', flush=True)
    rots = {'raw': tpl0,
            'rotCW': cv2.rotate(tpl0, cv2.ROTATE_90_CLOCKWISE),
            'rotCCW': cv2.rotate(tpl0, cv2.ROTATE_90_COUNTERCLOCKWISE),
            'rot180': cv2.rotate(tpl0, cv2.ROTATE_180)}
    results = {}
    for name, path, _mpp, zoom0 in TARGETS:
        if not path.exists():
            print(f'{name}: нет файла {path.name}')
            continue
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        Hi, Wi = img.shape
        best = None
        for rname, tpl in rots.items():
            th, tw = tpl.shape
            for zoom in (zoom0 * f for f in
                         (0.8, 0.9, 1.0, 1.1, 1.2)):
                # размер шаблона в пикселях карты
                twm = max(12, int(round(tw / zoom)))
                thm = max(12, int(round(th / zoom)))
                if twm >= Wi or thm >= Hi:
                    continue
                t = cv2.resize(tpl, (twm, thm),
                               interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(res)
                if best is None or mx > best[0]:
                    best = (mx, rname, round(zoom, 2), loc,
                            (twm, thm))
        if best:
            mx, rname, zoom, loc, sz = best
            print(f'{name}: best corr={mx:.3f} rot={rname} '
                  f'zoom={zoom} at {loc} tpl={sz}', flush=True)
            results[name] = dict(corr=round(float(mx), 4), rot=rname,
                                 zoom=zoom, x=loc[0], y=loc[1],
                                 w=sz[0], h=sz[1], img=path.name)
        del img
    json.dump(results, open(DIR / 'tpl_match.json', 'w'),
              ensure_ascii=False, indent=1)
    # топ-3 по корреляции
    top = sorted(results.items(), key=lambda kv: -kv[1]['corr'])[:3]
    print('ТОП-3:', [(n, v['corr']) for n, v in top])
    return 0


if __name__ == '__main__':
    sys.exit(main())
