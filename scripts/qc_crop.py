#!/usr/bin/env python3
"""QC-кропы полноразмерных промаркированных PNG: вырезаем фрагмент в JPEG для VLM.
Использование: python3 qc_crop.py <файл.png> <x> <y> <size> <out.jpg>"""
import sys
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

src, x, y, size, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
img = Image.open(src)
W, H = img.size
x = max(0, min(W - size, x))
y = max(0, min(H - size, y))
crop = img.crop((x, y, x + size, y + size))
crop.save(out, "JPEG", quality=90)
print(f"{out}: {size}x{size} из ({x},{y}), кадр {W}x{H}")
