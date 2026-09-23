#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50g: ручная обработка повёрнутого кадра Топольное.jpg (Task 50).

SIFT-матч конвейера: rot = -79.672° (frame->mosaic, конвенция cv2:
положительный угол = по часовой). Для нейтрализации кадр pre-поворачивается
на +79.672° в конвенции cv2 (= PIL rotate(-79.672), CCW/против часовой —
НЕ путать знаки). expand=True сохраняет весь контент; чёрные углы не мешают
SIFT (признаки — в застройке).

Контроль: повторный матч crop-стадии должен дать |rot| < 0.5°.
"""
import sys
from PIL import Image

SRC = '/home/z/my-project/upload/Топольное.jpg'
DST = '/home/z/my-project/upload/Топольное_northup.jpg'
ANGLE = 79.672          # PIL: против часовой (визуально CCW)

im = Image.open(SRC).convert('RGB')
print('исходник:', im.size)
out = im.rotate(ANGLE, resample=Image.BICUBIC, expand=True, fillcolor=(10, 10, 10))
print('развёрнут:', out.size)
out.save(DST, quality=95)
import os
print('сохранено: %.1f МБ' % (os.path.getsize(DST) / 1e6))
print(DST)
