#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""50j: отладка координат иконок карты Топольного."""
import json, os
D = '/home/z/my-project/work/topolnoe_test/work/topolnoe'
for f in sorted(os.listdir(D)):
    print(f, os.path.getsize(os.path.join(D, f)) // 1024, 'КБ')
print()
db = json.load(open(os.path.join(D, 'boq.json'), encoding='utf-8'))
print("db['net'] =", repr(db['net']))
for f in ['network.json', 'network_v2.json', 'network_crop.json']:
    p = os.path.join(D, f)
    if os.path.exists(p):
        n = json.load(open(p))
        anc = n.get('anchor') or {}
        x, y = anc.get('x'), anc.get('y')
        print(f"{f}: anchor=({x},{y}) type={type(x).__name__}, drops={len(n.get('drops') or [])}, "
              f"couplers={len(n.get('couplers') or [])}")
        # диапазон координат дропов
        pts = [d['poly'][-1] for d in (n.get('drops') or []) if d.get('poly')]
        if pts:
            xs = [p_[0] for p_ in pts]; ys = [p_[1] for p_ in pts]
            print(f"  дропы: x {min(xs):.0f}..{max(xs):.0f}, y {min(ys):.0f}..{max(ys):.0f}")
print()
for i, z in enumerate(db['zones']):
    print(f"зона[{i}]: {z.get('zone')!r} px={z.get('px')}")
ct = json.load(open(os.path.join(D, 'crop_transform.json'), encoding='utf-8'))
print()
print("M_inv:", ct['M_inv'])
print("M_full:", ct['M_full'])
print("кадр:", ct['new_image'], ct['new_W'], 'x', ct['new_H'])
print("мозаика:", ct['mosaic_W'], 'x', ct['mosaic_H'])
