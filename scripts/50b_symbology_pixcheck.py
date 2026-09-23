#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пиксельный контроль образцов иконок (50): структура без VLM."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import importlib
ms = importlib.import_module('50_map_symbology'.replace('.py', '')) if False else None
# модуль с цифрой в имени — импортируем через exec
ns = {}
exec(open(os.path.join(os.path.dirname(__file__), '50_map_symbology.py')).read()
     .split("if __name__")[0], ns)
draw_olt_node, draw_orsh = ns['draw_olt_node'], ns['draw_orsh']

from PIL import ImageDraw
im = Image.new('RGB', (400, 300), (100, 110, 95))
dr = ImageDraw.Draw(im, 'RGBA')
draw_olt_node(dr, 100, 100, 40)
draw_orsh(dr, 280, 100, 34, (25, 113, 194), 7)
draw_orsh(dr, 100, 230, 26, (240, 140, 0), 12)

px = im.load()
def near(c, t, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(c, t))

ok = True
def chk(cond, msg):
    global ok
    print(('OK ' if cond else 'FAIL ') + msg)
    ok = ok and cond

# ЦУ: центр дома — светлый; рамка бейджа — красная; табличка OLT — красная с белым текстом
chk(near(px[100, 88], (245, 248, 252), 25), f"OLT: корпус здания светлый {px[100,88]}")
chk(near(px[100, 50], (224, 49, 49), 45), f"OLT: красная рамка бейджа {px[100,50]}")
chk(near(px[75, 126], (224, 49, 49), 45), f"OLT: красная табличка {px[75,126]}")
row = [px[x, 126] for x in range(75, 126)]
chk(any(near(c, (255, 255, 255), 20) for c in row), "OLT: белый текст на табличке")
# антенна: мачта белая по вертикали над домом
col = [px[100, y] for y in range(66, 92)]
chk(any(near(c, (255, 255, 255), 30) for c in col), "OLT: мачта антенны")
# ОРШ-1: центр — цвет зоны; цифра белая; цоколь тёмный; тень смещена
chk(near(px[260, 95], (25, 113, 194), 40), f"ОРШ1: корпус цвета зоны {px[260,95]}")
col = [px[280, y] for y in range(70, 95)]
chk(any(near(c, (255, 255, 255), 25) for c in col), "ОРШ1: белая цифра номера")
chk(near(px[280, 140], (28, 30, 36), 30), f"ОРШ1: тёмный цоколь {px[280,140]}")
chk(near(px[307, 130], (0, 0, 0), 70), f"ОРШ1: тень справа {px[307,130]}")
# ОРШ-2 (номер 12, оранжевая зона)
chk(near(px[85, 232], (240, 140, 0), 40), f"ОРШ2: оранжевый корпус {px[85,232]}")
print('\nИТОГ:', 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if ok else 'ЕСТЬ ЗАМЕЧАНИЯ')
sys.exit(0 if ok else 1)
