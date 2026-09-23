# -*- coding: utf-8 -*-
"""Сетка координат на обзоре Пригородного для VLM-разметки + финальные bbox всех сёл."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from common import vdir, load_json, save_json
from PIL import Image, ImageDraw, ImageFont

d = load_json('/home/z/my-project/work/overview_geo.json')['prigorodnoe']
geo = d['geo']
img = Image.open(f"{vdir('prigorodnoe')}/overview.png").convert('RGB')
W, H = img.size
dr = ImageDraw.Draw(img)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)
cols, rows = 10, 8
cw, ch = W / cols, H / rows
for i in range(cols + 1):
    x = i * cw
    dr.line([(x, 0), (x, H)], fill=(255, 255, 0), width=2)
    if i < cols:
        dr.text((x + 6, 6), chr(65 + i), fill=(255, 255, 0), font=font)
for j in range(rows + 1):
    y = j * ch
    dr.line([(0, y), (W, y)], fill=(255, 255, 0), width=2)
    if j < rows:
        dr.text((6, y + 6), str(j + 1), fill=(255, 255, 0), font=font)
# центр села (камера)
cx = (83.52094976 - geo['west']) / (geo['east'] - geo['west']) * W
cy = (50.321981 - geo['south']) / (geo['north'] - geo['south']) * H
dr.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=(255, 0, 0), width=4)
img.save(f"{vdir('prigorodnoe')}/overview_grid.png")
print(f"Сетка {cols}x{rows}, ячейка {cw*geo['ov_mpp']/1000:.2f}x{ch*geo['ov_mpp']/1000:.2f} км")
print(f"гео-углы: west={geo['west']:.4f} east={geo['east']:.4f} north={geo['north']:.4f} south={geo['south']:.4f}")

# печать geo-координат линий сетки для пересчёта ячеек
for i in range(cols + 1):
    lon = geo['west'] + (geo['east'] - geo['west']) * i / cols
    print(f"колонка {chr(65+i) if i<cols else '|'} левый край lon={lon:.4f}")
for j in range(rows + 1):
    lat = geo['north'] - (geo['north'] - geo['south']) * j / rows
    print(f"строка {j+1 if j<rows else '|'} верхний край lat={lat:.4f}")
