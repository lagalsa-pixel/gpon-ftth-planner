#!/usr/bin/env python3
"""Анализ выгрузки: площади зданий, различия нумерованных/ненумерованных,
сравнение с официальными ДХ, оценка порогов для критерия «домохозяйство»."""
import json, os, statistics

DIR = "/home/z/my-project/scripts/households"
NON_RES = {"garage", "garages", "shed", "barn", "roof", "carport", "greenhouse",
           "industrial", "warehouse", "commercial", "retail", "school", "kindergarten",
           "hospital", "kiosk", "service", "construction", "ruins", "wall", "hut",
           "public", "civic", "offices", "hotel", "train_station", "tower"}

files = ["verhneberezevka", "solnechnoe", "perevalnoe", "vinnoe", "prigorodnoe", "altaisky"]
official = {"verhneberezevka": 940, "solnechnoe": 366, "perevalnoe": 339,
            "vinnoe": 490, "prigorodnoe": 365, "altaisky": 716}

for key in files:
    with open(os.path.join(DIR, f"{key}.geojson"), encoding="utf-8") as f:
        fc = json.load(f)
    feats = fc["features"]
    res = [ft for ft in feats if ft["properties"]["building"] not in NON_RES]
    hn = [ft for ft in res if ft["properties"]["housenumber"]]
    nohn = [ft for ft in res if not ft["properties"]["housenumber"]]

    def stats(arr, label):
        if not arr:
            print(f"    {label}: нет")
            return
        a = sorted(ft["properties"]["area_m2"] for ft in arr)
        n = len(a)
        print(f"    {label}: n={n}, площадь м2: p5={a[int(0.05*(n-1))]:.0f} p25={a[int(0.25*(n-1))]:.0f} "
              f"med={a[n//2]:.0f} p75={a[int(0.75*(n-1))]:.0f} p95={a[int(0.95*(n-1))]:.0f} max={a[-1]:.0f}")

    print(f"\n=== {fc['village']} (официально {official[key]} ДХ) ===")
    print(f"  всего зданий: {len(feats)}; кандидатов-жилых (по тегу): {len(res)}")
    stats(hn, "с номером дома (точно жилые)")
    stats(nohn, "без номера")
    # порог 30 м2
    for thr in (20, 25, 30, 35, 40):
        k = sum(1 for ft in nohn if ft["properties"]["area_m2"] >= thr)
        print(f"    без номера и >= {thr} м2: {k}")
    # распределение мелких
    tiny = sorted(ft["properties"]["area_m2"] for ft in nohn)[:0]
    if nohn:
        a = sorted(ft["properties"]["area_m2"] for ft in nohn)
        hist = {}
        for lo in range(0, 200, 20):
            hist[f"{lo}-{lo+20}"] = sum(1 for x in a if lo <= x < lo + 20)
        hist["200+"] = sum(1 for x in a if x >= 200)
        print(f"    гистограмма площадей без номера: {hist}")
