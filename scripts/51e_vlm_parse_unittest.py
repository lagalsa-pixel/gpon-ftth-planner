#!/usr/bin/env python3
"""Юнит-тест _hh2_vlm_nproperties после фикса парсинга CLI z-ai vision
(Task 50-resume2). Живой вызов на синтетическом кропе: ожидаем число, не None."""
import sys
sys.path.insert(0, '/home/z/my-project/download/ftth_pipeline')
import numpy as np
import ftth_pipeline as fp

fp._HH2_VLM_VERDICTS = {}
# синтетический «двор»: серый фон + одиночное строение
img = np.full((300, 400, 3), 90, np.uint8)
img[100:200, 150:250] = (60, 60, 150)
img[40:60, 40:220] = (60, 150, 60)  # «забор» для реалистичности

r = fp._hh2_vlm_nproperties(img, 'unit-test')
print('RESULT:', r)
print('CACHE:', fp._HH2_VLM_VERDICTS)
sys.exit(0 if r is not None else 4)
