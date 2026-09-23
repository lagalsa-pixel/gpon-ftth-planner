# -*- coding: utf-8 -*-
"""Поиск фактических границ Пригородное vs Верхняя Хариузовка через Nominatim."""
import requests, sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import HDRS

for q in ["Пригородное Риддер Казахстан", "Верхняя Хариузовка Казахстан"]:
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={'q': q, 'format': 'json', 'limit': 3, 'accept-language': 'ru',
                             'viewbox': '83.44,50.28,83.60,50.38', 'bounded': 1},
                     headers=HDRS, timeout=25)
    print(q, "->", r.status_code)
    for it in r.json():
        print(f"   {it.get('display_name','')[:80]} | {it.get('lat')},{it.get('lon')} | type={it.get('type')} class={it.get('class')}")
        bb = it.get('boundingbox')
        if bb:
            print(f"   bbox: {bb}")
