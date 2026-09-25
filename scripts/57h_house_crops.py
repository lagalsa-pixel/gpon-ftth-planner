#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 57h: прицельные кропы 4 домов кармана (по VLM-позициям вопросного
кропа) для финального уточнения координат крыш."""
import cv2

BASE = '/home/z/my-project'
frame = cv2.imread(f'{BASE}/upload/06_Алтайский_граница.jpg')

# позиции домов (мозаика) из вопросного кропа (NCC 0.9992)
HOUSES = [
    ('h1', 3652, 7920, 'голубая/белая'),
    ('h2', 3711, 7909, 'голубая'),
    ('h3', 3810, 7899, 'красная/оранжевая'),
    ('h4', 3834, 7885, 'голубая'),
]
R = 30  # радиус окна в px мозаики (~11.5 м)

for name, mx, my, col in HOUSES:
    fx, fy = mx * 2 - 5092.87, my * 2 - 9176.04
    x0, y0 = int(fx - R * 2), int(fy - R * 2)
    x1, y1 = int(fx + R * 2), int(fy + R * 2)
    crop = frame[y0:y1, x0:x1]
    big = cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4),
                     interpolation=cv2.INTER_LANCZOS4)
    # сетка 20 px кропа = 10 px мозаики = 3.8 м, ячейки A-F / 0-5
    STEP = 20 * 4
    h, w = big.shape[:2]
    cols = 'ABCDEFGHIJ'
    for i, gx in enumerate(range(0, w + 1, STEP)):
        x = min(gx, w)
        cv2.line(big, (x, 0), (x, h), (180, 255, 255), 1)
        if i < len(cols):
            cv2.putText(big, cols[i], (x + 3, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    for j, gy in enumerate(range(0, h + 1, STEP)):
        y = min(gy, h)
        cv2.line(big, (0, y), (w, y), (180, 255, 255), 1)
        cv2.putText(big, str(j), (3, y + 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 255), 2)
    # центр окна (ожидаемая позиция дома)
    cx, cy = w // 2, h // 2
    cv2.circle(big, (cx, cy), 18, (0, 0, 255), 4)
    cv2.putText(big, 'expected', (cx + 24, cy - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    out = f'{BASE}/work/altay2/south57_{name}_grid.jpg'
    cv2.imwrite(out, big, [cv2.IMWRITE_JPEG_QUALITY, 93])
    # координаты: col A = мозаика x = mx - R + col*10; row 0 = my - R + row*10
    print(f'{name} ({col}): окно мозаика ({mx - R},{my - R})-'
          f'({mx + R},{my + R}); центр окна = ({mx},{my}) -> {out}')
    print(f'  col_i -> x = {mx - R} + i*10; row_j -> y = {my - R} + j*10')
