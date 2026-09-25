#!/usr/bin/env python3
"""Task 53: сопоставление изображений и подписей в altay.pdf по их Y-позициям."""
import fitz

doc = fitz.open('/home/z/my-project/download/snp_vko/altay.pdf')
for pno, page in enumerate(doc, 1):
    imgs = []
    for info in page.get_image_info():
        bbox = info['bbox']
        imgs.append({'y0': round(bbox[1], 1), 'y1': round(bbox[3], 1),
                     'w': info['width'], 'h': info['height'],
                     'x0': round(bbox[0], 1), 'x1': round(bbox[2], 1)})
    caps = []
    for b in page.get_text('blocks'):
        txt = b[4].strip().replace('\n', ' ')
        if txt.startswith('Рисунок'):
            caps.append({'y0': round(b[1], 1), 'txt': txt[:80]})
    print(f'--- PAGE {pno} ---')
    for i in imgs:
        print(f'  IMG y[{i["y0"]}..{i["y1"]}] px {i["w"]}x{i["h"]}')
    for c in caps:
        print(f'  CAP y[{c["y0"]}..] : {c["txt"]}')
