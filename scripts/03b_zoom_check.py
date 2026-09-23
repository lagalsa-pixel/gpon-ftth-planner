# -*- coding: utf-8 -*-
"""Определение максимального доступного зума ESRI для каждой деревни (детект заглушек)."""
import sys, os, io, math
sys.path.insert(0, os.path.dirname(__file__))
from common import VILLAGES, fetch_tile, lon2tx, lat2ty
import numpy as np
from PIL import Image

def tile_stats(z, lat, lon):
    tx, ty = int(lon2tx(lon, z)), int(lat2ty(lat, z))
    data = fetch_tile(z, tx, ty)
    if not data:
        return None
    im = np.asarray(Image.open(io.BytesIO(data)).convert('L'), dtype=np.float32)
    return im.mean(), im.std(), len(data)

print("z | средн. яркость | std | размер | вердикт")
for v in VILLAGES[:2] + VILLAGES[5:]:
    print(f"\n=== {v['name']} (центр {v['lat']:.4f},{v['lon']:.4f}) ===")
    for z in (18, 17, 16, 15, 14):
        st = tile_stats(z, v['lat'], v['lon'])
        if st is None:
            print(f"z{z}: нет данных")
            continue
        mean, std, sz = st
        verdict = 'ЗАГЛУШКА' if (110 < mean < 150 and std < 12) else ('снимок' if std > 25 else '?')
        print(f"z{z}: mean={mean:.1f} std={std:.1f} size={sz} -> {verdict}")
