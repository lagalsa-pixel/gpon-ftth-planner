#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60d: калибровка зума скриншота altay3 по элементам символики
(квадрат ДХ, муфта, толщина дропа/кабеля) — скриншот vs карта 06 (v8).
Затем сегментация здания на скриншоте -> реальные размеры в метрах.
Сдвиг шапки +300px по Y на карте учтён (урок Task 59)."""
import json, math
import cv2
import numpy as np

BASE = '/home/z/my-project'
KEY = 'altaiskiy'
FIG = f'{BASE}/work/altay3/img_9_p1.png'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
HH = 300


def mosaic_to_map(tr, x, y):
    Mi = tr['M_inv']
    return (Mi[0][0] * x + Mi[0][1] * y + Mi[0][2],
            Mi[1][0] * x + Mi[1][1] * y + Mi[1][2] + HH)


def measure_square(img, cx, cy, R=22):
    """Размер цветного квадрата с тёмной обводкой: ширина линии профиля."""
    row = img[int(cy), int(cx) - R:int(cx) + R].astype(int)
    best = None
    # ищем подряд идущие пиксели «насыщенно-синие»
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = (s > 130) & (v > 70) & (h > 100) & (h < 130)
    col = m[int(cy), int(cx) - R:int(cx) + R]
    idx = np.where(col)[0]
    if len(idx) > 0:
        best = int(idx.max() - idx.min() + 1)
    col2 = m[int(cx) and int(cy) - R or 0: 0, 0]  # noop
    # вертикальный профиль
    colv = m[int(cy) - R:int(cy) + R, int(cx)]
    idxv = np.where(colv)[0]
    bestv = int(idxv.max() - idxv.min() + 1) if len(idxv) else None
    return best, bestv


def main():
    # ---------- 1. измерения на скриншоте ----------
    fig = cv2.imread(FIG)
    hsv = cv2.cvtColor(fig, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    print('=== СКРИНШОТ 459x339 ===')
    # квадрат: центр по блобу (292..317,155..179)
    sq_cx, sq_cy = 304, 167
    m_sq = (s > 120) & (v > 70) & (h > 100) & (h < 135)
    # морфология: взять связный компонент вокруг центра
    n, lab, st, cent = cv2.connectedComponentsWithStats((m_sq * 255).astype(np.uint8), 8)
    sq_sz = None
    for i in range(1, n):
        x, y, w2, hh2, a = st[i]
        if x <= sq_cx < x + w2 and y <= sq_cy < y + hh2 and a > 200:
            sq_sz = (w2, hh2, a)
            print(f'  квадрат ДХ: bbox {w2}x{hh2}, area {a}, at({x},{y})')
    # муфта (циан): блоб у (288,16,27x27)
    m_cy = (s > 110) & (v > 70) & (h > 78) & (h < 100)
    n, lab, st, cent = cv2.connectedComponentsWithStats((m_cy * 255).astype(np.uint8), 8)
    for i in range(1, n):
        x, y, w2, hh2, a = st[i]
        if a > 300:
            print(f'  муфта: bbox {w2}x{hh2}, area {a}, at({x},{y})')
    # дроп: толщина жёлтой линии на y=100 (между муфтой y43 и квадратом y155)
    m_y = (s > 110) & (v > 70) & (h > 20) & (h < 38)
    widths = []
    for yy in (70, 90, 110, 130):
        col = m_y[yy, :]
        idx = np.where(col)[0]
        if len(idx):
            # самый правый кластер (дроп у x~274-303)
            splits = np.where(np.diff(idx) > 3)[0]
            groups = np.split(idx, splits + 1)
            g = max(groups, key=lambda g: g.max())
            widths.append(int(g.max() - g.min() + 1))
    print(f'  дроп: толщина по горизонтали на y=70..130: {widths}')
    # кабель: толщина на x=100
    m_c = (s > 120) & (v > 70) & (h > 100) & (h < 130)
    col = m_c[:, 100]
    idx = np.where(col)[0]
    if len(idx):
        print(f'  кабель: толщина при x=100: {int(idx.max()-idx.min()+1)} px '
              f'(y {idx.min()}..{idx.max()})')

    # ---------- 2. измерения на карте 06 ----------
    print('=== КАРТА 06 (v8) ===')
    tr = json.load(open(f'{BASE}/work/{KEY}/crop_transform.json'))
    net = json.load(open(f'{BASE}/work/{KEY}/network_hh3.json'))
    mpp = json.load(open(f'{BASE}/work/mosaic_geo.json'))[KEY]['mpp']
    scale = tr['scale']
    mpp_new = mpp * scale
    print(f'  mpp мозаики {mpp:.3f}, м/px карты {mpp_new:.3f}')
    img = cv2.imread(MAP)
    print(f'  размер карты {img.shape[1]}x{img.shape[0]}')
    drop_by_id = {d['hh_id']: d for d in net['drops']}
    # квадрат hh53 (зона 1)
    for hh_id in (53, 88, 102):
        d = drop_by_id[hh_id]
        ex, ey = d['poly'][-1]
        mx, my = mosaic_to_map(tr, ex, ey)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hh_, ss, vv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        m_sq = (ss > 130) & (vv > 70) & (hh_ > 100) & (hh_ < 135)
        n, lab, st, cent = cv2.connectedComponentsWithStats((m_sq * 255).astype(np.uint8), 8)
        for i in range(1, n):
            x, y, w2, h2, a = st[i]
            if x - 3 <= mx < x + w2 + 3 and y - 3 <= my < y + h2 + 3 and a > 100:
                print(f'  кв. hh{hh_id} map({int(mx)},{int(my)}): {w2}x{h2} area {a}')
    # муфта M139
    for c in net['couplers']:
        if c['label'] in ('M139', 'M133', 'M132'):
            mx, my = mosaic_to_map(tr, c['x'], c['y'])
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            hh_, ss, vv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
            m_cy = (ss > 110) & (vv > 70) & (hh_ > 78) & (hh_ < 100)
            n, lab, st, cent = cv2.connectedComponentsWithStats((m_cy * 255).astype(np.uint8), 8)
            for i in range(1, n):
                x, y, w2, h2, a = st[i]
                if x - 4 <= mx < x + w2 + 4 and y - 4 <= my < y + h2 + 4 and a > 300:
                    print(f'  муфта {c["label"]} map({int(mx)},{int(my)}): {w2}x{h2} area {a}')

    # ---------- 3. сегментация здания на скриншоте ----------
    print('=== ЗДАНИЕ НА СКРИНШОТЕ ===')
    # крыша: рыжие торцы + светлая середина; двор: грунт.
    # ищем «крышные» цвета в области y=45..160 (между кабелем и квадратом)
    bgr = fig.astype(int)
    zone = bgr[40:160, 60:360]
    # рыжий/красноватый: R заметно > B, средняя насыщенность
    r, g, b = zone[:, :, 2], zone[:, :, 1], zone[:, :, 0]
    red = (r > 110) & (r - b > 40) & (g < r - 10)
    light = (r > 150) & (b > 130) & (abs(r - b) < 45) & (g > 120)
    mask = (red | light).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, cent = cv2.connectedComponentsWithStats(mask, 8)
    print('  крупнейшие светлые/рыжие блобы (кандидаты крыши):')
    for i in sorted(range(1, n), key=lambda i: -st[i][4])[:6]:
        x, y, w2, h2, a = st[i]
        if a < 400:
            continue
        print(f'    bbox=({x+60},{y+40},{w2}x{h2}) area={a} '
              f'соотношение {w2/max(1,h2):.2f}')
    cv2.imwrite(f'{BASE}/work/altay3/t60_fig_bldmask.png', mask)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
