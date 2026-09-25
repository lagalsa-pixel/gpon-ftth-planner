#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60m: точная калибровка Z скриншота: профили ширины кабеля,
дропа, стороны муфты и квадрата (по заливке) на скриншоте и на карте.
Вывод: оценка Z по каждому элементу."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
FIG = f'{BASE}/work/altay3/img_9_p1.png'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'


def runs(col, lo, hi):
    """подряд идущие индексы в [lo,hi] -> список (start,end,len)"""
    out = []
    inr = False
    for i, v in enumerate(col):
        if lo <= v <= hi and not inr:
            s = i
            inr = True
        elif not (lo <= v <= hi) and inr:
            out.append((s, i - 1, i - s))
            inr = False
    if inr:
        out.append((s, len(col) - 1, len(col) - s))
    return out


def main():
    fig = cv2.imread(FIG)
    hsv = cv2.cvtColor(fig, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    # 1) квадрат: вертикальный и горизонтальный профили по центру (304,167)
    sq = ((s > 120) & (v > 70) & (h > 100) & (h < 135)).astype(np.uint8)
    col_v = sq[:, 304]
    col_h = sq[167, :]
    print('СКРИНШОТ:')
    print('  квадрат верт. профиль при x=304:',
          runs(col_v, 1, 1))
    print('  квадрат гориз. профиль при y=167:',
          runs(col_h, 1, 1))
    # 2) муфта: циан-заливка при x=300 (центр (300,28))
    cy = ((s > 110) & (v > 90) & (h >= 75) & (h <= 95)).astype(np.uint8)
    print('  муфта верт. профиль при x=300:', runs(cy[:, 300], 1, 1))
    print('  муфта гориз. профиль при y=28:', runs(cy[28, :], 1, 1))
    # 3) дроп: жёлтая ширина при y=100
    yl = ((s > 90) & (v > 90) & (h >= 18) & (h <= 36)).astype(np.uint8)
    for yy in (80, 100, 120):
        rr = runs(yl[yy, :], 1, 1)
        rr = [r for r in rr if r[0] > 200]
        print(f'  дроп ширина при y={yy}: {rr}')
    # 4) кабель: синяя толщина при x=100,150,200
    bl = ((s > 120) & (v > 80) & (h >= 95) & (h <= 120)).astype(np.uint8)
    for xx in (60, 100, 150, 200):
        rr = runs(bl[:, xx], 1, 1)
        rr = [r for r in rr if r[2] > 5]
        print(f'  кабель толщина при x={xx}: {rr}')

    mp = cv2.imread(MAP)
    mhsv = cv2.cvtColor(mp, cv2.COLOR_BGR2HSV)
    mh, ms, mv = mhsv[:, :, 0], mhsv[:, :, 1], mhsv[:, :, 2]
    mcy = ((ms > 110) & (mv > 90) & (mh >= 75) & (mh <= 95)).astype(np.uint8)
    n, lab, st, cent = cv2.connectedComponentsWithStats(mcy * 255, 8)
    print('\nКАРТА 06:')
    for i in range(1, min(n, 400)):
        x, y, w2, h2, a = st[i]
        if a < 250 or a > 290:
            continue
        cx, cy2 = int(cent[i][0]), int(cent[i][1])
        print(f'  муфта at({x},{y}) {w2}x{h2}: верт. {runs(mcy[:, cx], 1, 1)} '
              f'гориз. {runs(mcy[cy2, :], 1, 1)}')
        break
    mbl = ((ms > 120) & (mv > 80) & (mh >= 95) & (mh <= 120)).astype(np.uint8)
    # квадрат: возьмём hh526: map (2311,5426)
    for (qx, qy, tag) in [(2311, 5426, 'hh526'), (1850 + 8, 6300 + 8, 'A'),
                          (1662 + 8, 6310 + 8, 'B')]:
        col_v = mbl[:, qx]
        rr = [r for r in runs(col_v, 1, 1) if r[0] < qy + 30 and r[2] > 8]
        col_h = mbl[qy, :]
        rr2 = [r for r in runs(col_h, 1, 1) if r[0] < qx + 30 and r[2] > 8]
        print(f'  квадрат {tag} at({qx},{qy}): верт {rr} гориз {rr2}')
    # кабель: толщина в чистом месте (вертикальный кабель x~2278)
    for xx in (2278, 2281):
        rr = [r for r in runs(mbl[:, xx], 1, 1) if r[2] > 5]
        print(f'  верт.кабель толщина при x={xx}: {rr[:3]}')
    # горизонт. кабель y~5355
    for yy in (5355, 5358):
        rr = [r for r in runs(mbl[yy, :], 1, 1) if r[2] > 5]
        print(f'  гориз.кабель толщина при y={yy}: {rr[:3]}')
    # жёлтый дроп на карте: толщина
    myl = ((ms > 90) & (mv > 90) & (mh >= 18) & (mh <= 36)).astype(np.uint8)
    # дроп hh528: от M41(3684,7217) к sq(3702,7170): map M41=(2275,5558) sq=(2311,5464)
    for xx in (2300, 2305):
        rr = [r for r in runs(myl[:, xx], 1, 1) if r[2] > 2]
        print(f'  дроп толщина при x={xx}: {rr[:4]}')


if __name__ == '__main__':
    main()
