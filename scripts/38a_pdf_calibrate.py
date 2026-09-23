# -*- coding: utf-8 -*-
"""
Шаг 38a. Калибровка сжатия карт зон ОРШ для альбома PDF <= 10 МБ.

Исходники: download/snp_vko/<NN>_<Село>_зоны_ОРШ_схема_D.jpg (124 МБ суммарно).
Подбираем (max_px, quality, subsampling): даунсемпл LANCZOS длинной стороны до
max_px, кодирование JPEG в BytesIO, замер байтов. Вывод — матрица кандидатов,
итог — рекомендация под бюджет (с учётом ~0.15 МБ титульного листа и структуры).

Запуск: python3 38a_pdf_calibrate.py
"""
import io
import json
import os
import time

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

BASE = '/home/z/my-project'
SRC = f'{BASE}/download/snp_vko'
BUDGET = 9.6e6            # байтов на карты (0.4 МБ запас на титул + структуру)

FILES = sorted(f for f in os.listdir(SRC) if f.endswith('.jpg'))

# Кандидаты в порядке убывания качества: (max_px, quality, subsampling)
CANDIDATES = [
    (3600, 86, 0),
    (3500, 85, 0),
    (3400, 84, 0),
    (3300, 83, 2),
    (3200, 82, 2),
    (3000, 80, 2),
    (2800, 78, 2),
    (2600, 75, 2),
]


def encode(path, max_px, quality, subsampling):
    """Быстрый тест-энкод: draft-декод до ~2x цели, затем LANCZOS."""
    t0 = time.time()
    im = Image.open(path)
    w, h = im.size
    target = max_px / max(w, h)
    if target < 1.0:
        # draft: DCT-доменное сокращение (степень 2^k) — сильно ускоряет декод
        draft_w = max(1, int(w * target * 2) // 2)
        im.draft('RGB', (draft_w, draft_w))
        im = im.resize((max(1, round(w * target)), max(1, round(h * target))),
                       Image.LANCZOS, reducing_gap=3.0)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=quality, subsampling=subsampling,
            optimize=True)
    return buf.tell(), time.time() - t0, im.size


def main():
    results = {}
    for cand in CANDIDATES:
        total = 0
        rows = []
        for f in FILES:
            n, dt, size = encode(os.path.join(SRC, f), *cand)
            total += n
            rows.append((f[:2], n / 1e6, size, dt))
        results[cand] = total
        flag = 'OK  ' if total <= BUDGET else 'over'
        print(f'{cand}: total {total / 1e6:6.2f} МБ  {flag}   '
              + '  '.join(f'{n:.2f}' for _, n, _, _ in rows), flush=True)
        if total <= BUDGET:
            print(f'\nРЕКОМЕНДАЦИЯ: max_px={cand[0]}, quality={cand[1]}, '
                  f'subsampling={cand[2]} -> {total / 1e6:.2f} МБ')
            json.dump({'choice': list(cand), 'total_bytes': total},
                      open(f'{BASE}/work/pdf_album_calib.json', 'w'))
            return
    print('Ни один кандидат не уложился в бюджет — требуется ручная настройка')


if __name__ == '__main__':
    main()
