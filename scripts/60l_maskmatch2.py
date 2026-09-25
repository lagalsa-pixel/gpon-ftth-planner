#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60l: маск-матчинг v2 — тугой шаблон: только правая часть
скриншота (муфта + дроп + квадрат + конец кабеля), жёлтый канал с
максимальным весом (дропы редки). Диапазон Z 1.30-1.90, шаг 0.0125."""
import cv2
import numpy as np

BASE = '/home/z/my-project'
FIG = f'{BASE}/work/altay3/img_9_p1.png'
MAP = f'{BASE}/work/altay3/map06_v8.jpg'
# тугой шаблон: x 240..370 (муфта 283-317, дроп 274-303, квадрат 292-317,
# конец кабеля 240-295), y 0..200
TX0, TY0, TX1, TY1 = 240, 0, 370, 200


def masks_bgr(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    yel = ((s > 90) & (v > 90) & (h >= 18) & (h <= 36)).astype(np.float32)
    blu = ((s > 120) & (v > 80) & (h >= 95) & (h <= 120)).astype(np.float32)
    cyn = ((s > 110) & (v > 90) & (h >= 75) & (h <= 95)).astype(np.float32)
    return yel, blu, cyn


def main():
    fig = cv2.imread(FIG)
    mp = cv2.imread(MAP)
    fy, fb, fc = masks_bgr(fig)
    my, mb, mc = masks_bgr(mp)
    # тугой шаблон
    ty0 = fy[TY0:TY1, TX0:TX1]
    tb0 = fb[TY0:TY1, TX0:TX1]
    tc0 = fc[TY0:TY1, TX0:TX1]
    print(f'шаблон {TX1-TX0}x{TY1-TY0}: жёлт {int(ty0.sum())}, '
          f'син {int(tb0.sum())}, циан {int(tc0.sum())} px')

    results = []
    for Z in np.arange(1.30, 1.9125, 0.0125):
        tw = int((TX1 - TX0) / Z)
        th = int((TY1 - TY0) / Z)
        if tw < 40 or th < 60:
            continue
        ty = (cv2.resize(ty0, (tw, th), interpolation=cv2.INTER_AREA) > 0.35).astype(np.float32)
        tb = (cv2.resize(tb0, (tw, th), interpolation=cv2.INTER_AREA) > 0.35).astype(np.float32)
        tc = (cv2.resize(tc0, (tw, th), interpolation=cv2.INTER_AREA) > 0.35).astype(np.float32)
        if ty.sum() < 15 or tb.sum() < 15 or tc.sum() < 5:
            continue
        score = None
        for tm, mm, wgt in ((ty, my, 3.0), (tb, mb, 1.0), (tc, mc, 2.0)):
            r = cv2.matchTemplate(mm, tm, cv2.TM_CCOEFF_NORMED)
            r = np.nan_to_num(r)
            score = r if score is None else score + wgt * r
        score /= 6.0
        _, mx, _, loc = cv2.minMaxLoc(score)
        results.append((float(mx), float(Z), loc, tw, th))

    results.sort(reverse=True)
    print('\nТОП-10:')
    for s, z, loc, tw, th in results[:10]:
        print(f'  score={s:.4f} Z={z:.4f} at {loc} (шаблон {tw}x{th})')
    # кропы топ-3 (полный кадр скриншота вокруг матча)
    Hf, Wf = fig.shape[:2]
    for i, (s, z, loc, tw, th) in enumerate(results[:3]):
        # loc — левый-верх шаблона; полный кадр: сдвиг на TX0/Z, TY0/Z
        fx0 = int(loc[0] - TX0 / z)
        fy0 = int(loc[1] - TY0 / z)
        fw, fh = int(Wf / z), int(Hf / z)
        crop = mp[max(0, fy0):fy0 + fh, max(0, fx0):fx0 + fw]
        big = cv2.resize(crop, None, fx=z, fy=z, interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(f'{BASE}/work/altay3/t60_m2_top{i}.png', big)
        print(f'top{i}: score={s:.4f} Z={z:.4f} полный-кадр at({fx0},{fy0})')
    np.save(f'{BASE}/work/altay3/t60_m2_scores.npy',
            np.array([(s, z, loc[0], loc[1]) for s, z, loc, tw, th in results]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
