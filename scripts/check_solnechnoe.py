#!/usr/bin/env python3
"""Диагностика верхней части снимка Солнечного: ищем однотонные серые зоны."""
from PIL import Image
import numpy as np, os

p = "/home/z/my-project/download/snp_vko/02_Солнечное_Google_z18.png"
img = Image.open(p)
W, H = img.size
print(f"Полный кадр: {W}x{H}")

# Верхняя полоса (верхние 30%)
top = img.crop((0, 0, W, int(H * 0.30)))
arr = np.array(top).astype(float)
print(f"Верхняя полоса: {top.size}, средняя яркость={arr.mean():.1f}, std={arr.std():.1f}")

# Сетка 12x6, ищем блоки с низкой вариативностью (потенциальные заглушки)
gw, gh = 12, 6
bw, bh = W // gw, int(H * 0.30) // gh
suspects = []
for gy in range(gh):
    for gx in range(gw):
        block = arr[gy*bh:(gy+1)*bh, gx*bw:(gx+1)*bw]
        s = block.std()
        if s < 8:
            suspects.append((gx, gy, s, block.mean()))
print("Подозрительные блоки (std<8):", suspects if suspects else "не найдено")

# Сохраним увеличенный кроп верхней трети для визуальной проверки
crop_debug = img.crop((0, 0, W, int(H * 0.33)))
crop_debug.thumbnail((1800, 1800), Image.LANCZOS)
crop_debug.save("/home/z/my-project/scripts/tiles_cache/solnechnoe_top_debug.jpg", "JPEG", quality=90)
print("Сохранён кроп верхней трети: scripts/tiles_cache/solnechnoe_top_debug.jpg")
