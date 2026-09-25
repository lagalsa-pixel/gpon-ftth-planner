#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 54i: пересборка мозаики Алтайского из тайлов z18 + кропы
вне-кадровых кандидатов (север 1327888338/637127274, юг 759948641/643,
запад-контроль 637127240/637127230/637127234)."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path('/home/z/my-project')
KEY = 'altaiskiy'
FIGS = BASE / 'work/altay_remarks'
TILES = BASE / 'work/tiles/g18'

geo = json.load(open(BASE / 'work/mosaic_geo.json'))[KEY]
mpp, WEST, NORTH = geo['mpp'], geo['west'], geo['north']
MW, MH = geo['W'], geo['H']

Z = 18
N = 2 ** Z


def lonlat_to_tile(lo, la):
    x = (lo + 180.0) / 360.0 * N
    y = (1 - math.log(math.tan(math.radians(la)) +
                      1 / math.cos(math.radians(la))) / math.pi) / 2 * N
    return x, y


def g2p(la, lo):
    return ((lo - WEST) * 111320.0 * math.cos(math.radians(la)) / mpp,
            (NORTH - la) * 111132.0 / mpp)


mos_path = BASE / f'work/{KEY}/mosaic.jpg'
if mos_path.exists():
    print('мозаика уже есть:', mos_path)
else:
    # пересборка: для каждого тайла считаем смещение в мозаике
    mosaic = Image.new('RGB', (MW, MH), (128, 128, 128))
    n_put = 0
    txs = sorted(int(d.name) for d in TILES.iterdir() if d.is_dir())
    for tx in txs:
        tdir = TILES / str(tx)
        for f in tdir.glob('*.jpg'):
            ty = int(f.stem)
            # гео-границы тайла
            lo0 = tx / N * 360 - 180
            lo1 = (tx + 1) / N * 360 - 180
            la0 = math.degrees(math.atan(math.sinh(
                math.pi * (1 - 2 * (ty + 1) / N))))
            la1 = math.degrees(math.atan(math.sinh(
                math.pi * (1 - 2 * ty / N))))
            # угол тайла (лево-верх) в мозаике (по центру тайла для широты)
            lam = (la0 + la1) / 2
            x0 = (lo0 - WEST) * 111320.0 * math.cos(math.radians(lam)) / mpp
            y0 = (NORTH - la1) * 111132.0 / mpp
            xi, yi = int(round(x0)), int(round(y0))
            if xi + 256 < 0 or yi + 256 < 0 or xi >= MW or yi >= MH:
                continue
            tile = Image.open(f).convert('RGB')
            mosaic.paste(tile, (xi, yi))
            n_put += 1
    mosaic.save(mos_path, quality=90)
    print(f'мозаика собрана: {n_put} тайлов -> {mosaic} {mosaic.size}')

mosaic = Image.open(mos_path)

# кропы вне-кадровых кандидатов
CHECK = {
    1327888338: 'north_74m',   # 27x74, 0 дропов!
    637127274: 'north',
    759948641: 'south_out',
    759948643: 'south_out',
    637127240: 'west_farm?',   # 64x82
    637127230: 'west_industrial_control',
    637127234: 'west_lv10_oddity',
    637127239: 'west_farm?',
}
osm = json.load(open(BASE / f'work/{KEY}/osm.json'))
BLD = {b['id']: b for b in osm['buildings']}
MARGIN = 20

for bid, tag in CHECK.items():
    if bid not in BLD:
        print(f'{bid}: нет в OSM')
        continue
    b = BLD[bid]
    pts = [g2p(la, lo) for la, lo in b['poly']]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    m_px = MARGIN / mpp
    x0, y0 = int(max(0, min(xs) - m_px)), int(max(0, min(ys) - m_px))
    x1, y1 = int(min(MW, max(xs) + m_px)), int(min(MH, max(ys) + m_px))
    if x1 - x0 < 20 or y1 - y0 < 20:
        print(f'{bid} ({tag}): вне мозаики')
        continue
    crop = mosaic.crop((x0, y0, x1, y1))
    if crop.width * crop.height < 100:
        continue
    pts_px = [(x - x0, y - y0) for x, y in pts]
    dr = ImageDraw.Draw(crop)
    dr.line(pts_px + [pts_px[0]], fill=(255, 0, 255), width=3)
    up = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    p = FIGS / f't54_out_{bid}_2x.png'
    up.save(p)
    print(f'{bid} ({tag}): {crop.size[0]}x{crop.size[1]} -> {p.name}')
