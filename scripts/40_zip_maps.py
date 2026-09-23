# -*- coding: utf-8 -*-
"""Task 40: Собрать последний комплект карт (зоны ОРШ, схема D) в zip-архив.

Шаги:
  1. Проверка целостности 6 JPG (PIL: verify + размеры).
  2. Манифест README.txt (рус.): состав комплекта, параметры карт, краткая справка по схеме D.
  3. Zip (ZIP_DEFLATED, UTF-8 имена) с 6 картами пол. разрешения + манифест.
  4. Контрольная проверка архива: testzip + сверка CRC/размеров + итоговый отчёт.
"""
import json
import os
import sys
import zipfile
from datetime import date
from io import BytesIO

from PIL import Image

BASE = "/home/z/my-project"
MAP_DIR = os.path.join(BASE, "download", "snp_vko")
OUT_ZIP = os.path.join(BASE, "download", "Карты_зон_ОРШ_схема_D_ВКО.zip")
DATA = json.load(open(os.path.join(BASE, "work", "boq_decentral_data_v4.json"), encoding="utf-8"))

# сметы по решению заказчика (Task 46) в комплект не входят — упоминаний в манифесте нет

RAION = {"01": "Глубоковский р-н", "02": "Глубоковский р-н", "03": "Глубоковский р-н",
         "04": "Глубоковский р-н", "05": "Риддер г.а.", "06": "Глубоковский р-н"}

files = sorted(f for f in os.listdir(MAP_DIR) if f.endswith("_зоны_ОРШ_схема_D.jpg"))
assert len(files) == 6, f"ожидалось 6 карт, найдено {len(files)}: {files}"

# --- 1. Целостность и параметры карт -------------------------------------
entries = []
for fn in files:
    path = os.path.join(MAP_DIR, fn)
    with Image.open(path) as im:
        im.verify()                     # декодирование контрольных данных JPEG
    with Image.open(path) as im:        # verify() инвалидирует объект — открыть заново
        w, h = im.size
        dpi = im.info.get("dpi", ("-", "-"))
    num = fn[:2]
    v = next(v for v in DATA["villages"] if v["num"] == num)
    entries.append(dict(fn=fn, path=path, w=w, h=h, dpi=dpi,
                        mb=os.path.getsize(path) / 1e6, village=v))
    print(f"OK  {fn}  {w}x{h}px  {entries[-1]['mb']:.1f} МБ  зон ОРШ: {v['n_zones']}  ДХ: {v['dhx_served']}")

t = DATA["totals"]

# --- 2. Манифест -----------------------------------------------------------
def mp(v):
    n = v["n_zones"]
    if n == 0:
        return "зонные ОРШ не образуются (компактное село) — сплиттеры 1:64 в ЦУ"
    pl = "зонный ОРШ" if n % 10 == 1 and n % 100 != 11 else "зонных ОРШ"
    return f"{n} {pl} + ЦУ"

rows = []
for e in entries:
    rows.append(f"  {e['fn']}\n"
                f"      {e['village']['name']} ({RAION[e['fn'][:2]]}) — {e['w']}\u00d7{e['h']} px, "
                f"{e['mb']:.1f} МБ, JPEG q90\n"
                f"      {e['village']['dhx_served']} обслуживаемых ДХ; {mp(e['village'])}")

manifest = f"""КОМПЛЕКТ КАРТ ЗОН ОРШ — СХЕМА D (децентрализованная)
Проект FTTH: 6 сельских населённых пунктов ВКО (Глубоковский р-н и г. Риддер)
Дата сборки: {date.today().strftime('%d.%m.%Y')}

Состав комплекта — 6 карт зон обслуживания ОРШ (полноразмерные оригиналы, без сжатия):
{chr(10).join(rows)}

Схема D (краткая справка):
  * децентрализованная структура (v3-топология, уточнённая детекция ДХ): {t['n_zones']} зонных ОРШ со сплиттерами 1:64 в центрах секторов + 6 ЦУ (узел OLT), всего {t['orsh']} ОРШ;
  * обслуживаемые домохозяйства: {t['dhx_served']} ДХ (из {t['dhx_excel']} учтённых статистикой);
  * волокно всего {str(t['fiber_km']).replace('.', ',')} км; магистральный кабель {str(t['cable_km_raw']).replace('.', ',')} км
    (закупка с запасом +10%); дроп-кабель {str(t['drop_cable_km']).replace('.', ',')} км (закупка, +5%);
  * муфты {t['mufty']}, сварные соединения {t['splices']}, порты абонентские {t['orsh_ports']}.

Условные обозначения на картах: цвет зоны = оболочка обслуживаемых ДХ и сеть зоны;
пунктирная линия = фидер ЦУ -> зонный ОРШ; красная точка = ЦУ (узел OLT).
Верхнеберезовка — базовый спутниковый кадр Google z18 (перешит); остальные карты —
на обрезанных кадрах пользователя.

Примечание: для пересылки/печати A3 удобно использовать PDF-версию альбома
«Альбом_карт_зон_ОРШ_схема_D_ВКО.pdf» (те же 6 карт + титульный лист) —
передаётся отдельным файлом.
"""

# --- 3. Сборка zip ---------------------------------------------------------
if os.path.exists(OUT_ZIP):
    os.remove(OUT_ZIP)
with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    z.writestr("README.txt", manifest)
    for e in entries:
        z.write(e["path"], arcname=e["fn"])

# --- 4. Проверка архива ----------------------------------------------------
with zipfile.ZipFile(OUT_ZIP) as z:
    bad = z.testzip()
    assert bad is None, f"повреждён файл в архиве: {bad}"
    infos = z.infolist()
    assert len(infos) == 7, f"в архиве {len(infos)} записей, ожидалось 7"
    # сверка байтов архивных копий с оригиналами
    for e in entries:
        with open(e["path"], "rb") as f:
            orig = f.read()
        arc = z.read(e["fn"])
        assert arc == orig, f"несовпадение содержимого: {e['fn']}"
    zip_mb = os.path.getsize(OUT_ZIP) / 1e6
    src_mb = sum(e["mb"] for e in entries)
    print(f"\nАрхив: {os.path.basename(OUT_ZIP)}")
    print(f"  записей: {len(infos)} (6 карт + README.txt)")
    print(f"  исходные карты: {src_mb:.1f} МБ -> архив: {zip_mb:.1f} МБ")
    for i in infos:
        print(f"    {i.filename}  {i.file_size/1e6:8.2f} МБ -> {i.compress_size/1e6:8.2f} МБ")
print("\nПроверки пройдены: testzip OK, побайтовое сравнение OK.")
