#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 60y: добавление измеренного вне-OSM барака (многоквартирный дом
по слову заказчика, altay3) в work/altaiskiy/osm.json — чтобы 58a сгруппировал
4 ДХ по зданию (R_TOL 14 м от полигона) и поставил значок МЖД.

Полигон: мозаика (3663..3741) x (7789..7827) -> lat/lon (по mosaic_geo).
_footprint уточнён поперечными срезами яркости: тёмная крыша 3663-3741,
южная стена ~7827, северная ~7789; лёгкая восточная секция включена
(крыльца до x~3734 по VLM фасада)."""
import json
import math
import shutil
from pathlib import Path

BASE = Path('/home/z/my-project')
OP = BASE / 'work/altaiskiy/osm.json'
BID = 900001331            # синтетический id (прослеживается к hh131)
X0, X1, Y0, Y1 = 3663.0, 3741.0, 7789.0, 7827.0


def main():
    geo = json.load(open(BASE / 'work/mosaic_geo.json'))['altaiskiy']
    west, north, mpp = geo['west'], geo['north'], geo['mpp']

    def px2ll(x, y):
        # обратное к 58a g2p: (north-la)*111132/mpp — иначе полигон
        # смещается к северу на ~0.17% (6.5 м) при обратном чтении
        lat = north - y * mpp / 111132.0
        lon = west + x * mpp / (111320.0 * math.cos(math.radians(lat)))
        return [round(lat, 7), round(lon, 7)]

    poly = [px2ll(X0, Y0), px2ll(X1, Y0), px2ll(X1, Y1), px2ll(X0, Y1),
            px2ll(X0, Y0)]
    cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
    area = round((X1 - X0) * mpp * (Y1 - Y0) * mpp, 1)

    osm = json.load(open(OP, encoding='utf-8'))
    assert not any(b['id'] == BID for b in osm['buildings']), 'уже добавлен'
    shutil.copy(OP, OP.with_suffix('.json.bak_t60'))
    osm['buildings'].append(dict(
        id=BID, poly=poly, center=px2ll(cx, cy), area=area,
        tags={'building': 'yes', 'building:levels': '1',
              'note': 'altay3: вне-OSM барак, многоквартирный дом '
                      '(заказчик, Task 60); 4 ДХ по формуле lv=1'}))
    json.dump(osm, open(OP, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'добавлено здание id={BID}: {poly[:2]}... area={area} м2; '
          f'зданий стало {len(osm["buildings"])}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
