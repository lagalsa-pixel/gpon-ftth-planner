#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60j: точная привязка скриншота altay3 к карте 06 — цветовой
маск-матчинг символики. Три канала-маски: жёлтый (дроп), тёмно-синий
(квадрат ДХ + кабель), циан (муфта). Мультимасштабный поиск Z=1.25..1.90.
Устойчиво к шуму спутника: сравниваются ТОЛЬКО элементы символики."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
FIG = f'{BASE}/work/altay3/img_9_p1.png'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'


def masks_bgr(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    sat = s > 90
    # жёлтый дроп (255,225,0)
    yel = sat & (v > 90) & (h >= 18) & (h <= 36)
    # тёмно-синий (25,113,194): H~104
    blu = (s > 120) & (v > 80) & (h >= 95) & (h <= 120)
    # циан-муфта (0,255,225): H~90
    cyn = (s > 110) & (v > 90) & (h >= 75) & (h <= 95)
    return (yel.astype(np.float32), blu.astype(np.float32),
            cyn.astype(np.float32))


def main():
    fig = cv2.imread(FIG)
    mp = cv2.imread(MAP)
    # маска валидности скриншота (без рамок) — вся картинка
    fy, fb, fc = masks_bgr(fig)
    my, mb, mc = masks_bgr(mp)
    print(f'скриншот: жёлтых {int(fy.sum())}, синих {int(fb.sum())}, '
          f'циан {int(fc.sum())} px')
    print(f'карта: жёлтых {int(my.sum())}, синих {int(mb.sum())}, '
          f'циан {int(mc.sum())} px')

    results = []
    Hf, Wf = fig.shape[:2]
    for Z in np.arange(1.25, 1.925, 0.025):
        tw, th = int(Wf / Z), int(Hf / Z)
        if tw < 100 or th < 100:
            continue
        ty = cv2.resize(fy, (tw, th), interpolation=cv2.INTER_AREA)
        tb = cv2.resize(fb, (tw, th), interpolation=cv2.INTER_AREA)
        tc = cv2.resize(fc, (tw, th), interpolation=cv2.INTER_AREA)
        # бинаризация после ресайза
        ty = (ty > 0.35).astype(np.float32)
        tb = (tb > 0.35).astype(np.float32)
        tc = (tc > 0.35).astype(np.float32)
        if ty.sum() < 20 or tb.sum() < 20 or tc.sum() < 5:
            continue
        score = None
        for tm, mm, wgt in ((ty, my, 1.0), (tb, mb, 1.2), (tc, mc, 1.5)):
            r = cv2.matchTemplate(mm, tm, cv2.TM_CCOEFF_NORMED)
            r = np.nan_to_num(r)
            score = r if score is None else score + wgt * r
        # нормировка на сумму весов
        score /= 3.7
        _, mx, _, loc = cv2.minMaxLoc(score)
        results.append((float(mx), float(Z), loc, tw, th))
        print(f'Z={Z:.3f}: max={mx:.4f} at {loc} (шаблон {tw}x{th})')

    results.sort(reverse=True)
    print('\nТОП-5:')
    for s, z, loc, tw, th in results[:5]:
        print(f'  score={s:.4f} Z={z:.3f} левый-верх карты=({loc[0]},{loc[1]}) '
              f'шаблон {tw}x{th}')
    # сохранить лучший кроп
    s, z, loc, tw, th = results[0]
    x0, y0 = loc
    crop = mp[y0:y0 + th, x0:x0 + tw]
    big = cv2.resize(crop, None, fx=z, fy=z, interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(f'{BASE}/work/altay3/t60_match_best.png', big)
    print(f'\nлучший: Z={z:.3f} at({x0},{y0}) score={s:.4f} -> t60_match_best.png')
    # топ-3 кропы
    for i, (s, z, loc, tw, th) in enumerate(results[:3]):
        x0, y0 = loc
        crop = mp[y0:y0 + th, x0:x0 + tw]
        big = cv2.resize(crop, None, fx=z, fy=z, interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(f'{BASE}/work/altay3/t60_match_top{i}.png', big)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
