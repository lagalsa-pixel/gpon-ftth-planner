#!/bin/bash
# Task 47. Финальная пересборка комплекта после полной VLM-верификации.
# Сметы НЕ генерируются (решение заказчика, Task 46).
# Порядок: 52c -> 53 -> 54 (override) -> 47_sync -> 48b (override) -> 30 -> 34 -> 38 -> 40 -> 49b
set -e
cd /home/z/my-project/scripts
echo "== 1/9 сборка детекции 52c =="
python3 52c_build_v2.py
echo "== 2/9 сети 53 =="
python3 53_network_hh2.py
echo "== 3/9 топология 54 (FTTH_NET_OVERRIDE) =="
FTTH_NET_OVERRIDE=network_hh2.json python3 54_topology_v4.py | tail -22
echo "== 4/9 синхронизация констант 47 =="
python3 47_sync_consts.py
echo "== 5/9 карты 48b (FTTH_NET_OVERRIDE) =="
FTTH_NET_OVERRIDE=network_hh2.json python3 48b_zone_maps_v4.py all | tail -8
echo "== 6/9 книга: лист Децентрализация (30) =="
python3 30_decentral_xlsx.py | tail -4
echo "== 7/9 книга: лист Сводная схема D (34) — ПОСЛЕ 30 =="
python3 34_svod_d_xlsx.py | tail -4
echo "== 8/9 PDF-альбом (38) + zip (40) =="
python3 38_pdf_album.py | tail -3
python3 40_zip_maps.py | tail -5
echo "== 9/9 числовой QA 49b =="
python3 49b_qa_v4.py | tail -14
echo "== ЦЕПОЧКА ЗАВЕРШЕНА =="
