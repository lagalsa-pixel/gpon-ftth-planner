#!/bin/bash
# 51_topolnoe_vlm_resume.sh [MAX_WAIT_MIN] — Task 50, открытый пункт:
# VLM-верификация кандидатов A/B Топольного + перегон цепочки до qa.
#
# Возобновляемый и идемпотентный:
#  - перед стадиями ждёт квоту VLM (проба; при 429 — повтор каждые 10 мин
#    до MAX_WAIT_MIN, по умолчанию 0 = одна проба и выход с кодом 3);
#  - вердикты VLM кэшируются в work/topolnoe_test/work/topolnoe/
#    vlm_verdicts.json (переживают обрывы квоты/процесса: при обрыве
#    повторный запуск докладывает только недостающие вызовы);
#  - все стадии детерминированы, перезапуск безопасен.
#
# Цепочка: fetch → households(+VLM) → anchor → network → crop(кадр
# заказчика north-up) → boq → map → xlsx → qa; deliverables копируются
# в download/Топольное_тест/.
#
# Коды выхода: 0 успех; 3 квота недоступна; 2 сбой стадии; 1 прочее.

set -u
BASE=/home/z/my-project
PIPE=$BASE/download/ftth_pipeline
WORKDL=$BASE/work/topolnoe_test/download
DLTEST=$BASE/download/Топольное_тест
MAXWAIT=${1:-0}
PROBE_EVERY=600

probe() { bun "$BASE/scripts/51_vlm_probe.mjs" 2>/dev/null; }

echo "=== $(date '+%H:%M:%S') проба квоты VLM ==="
probe
rc=$?
if [ "$rc" -ne 0 ]; then
  if [ "$rc" -ne 3 ]; then echo "PROBE_ERROR ($rc)"; exit 1; fi
  echo "QUOTA_DOWN (429)"
  [ "$MAXWAIT" -le 0 ] && exit 3
  deadline=$(( $(date +%s) + MAXWAIT * 60 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    sleep $PROBE_EVERY
    echo "=== $(date '+%H:%M:%S') повторная проба квоты ==="
    probe && break
    [ "$?" -ne 3 ] && exit 1
  done
  probe || { echo "QUOTA_STILL_DOWN"; exit 3; }
fi
echo "QUOTA_OK — запускаю цепочку"

cd "$PIPE" || exit 1
for st in fetch households anchor network crop boq map xlsx; do
  echo; echo "===== STAGE $st ====="
  python3 ftth_pipeline.py --config config_topolnoe.json --stage "$st" --village topolnoe \
    || { echo "STAGE $st FAILED (rc=$?)"; exit 2; }
done
echo; echo "===== STAGE qa ====="
python3 ftth_pipeline.py --config config_topolnoe.json --stage qa --village topolnoe || true

cp -f "$WORKDL/07_Топольное_зоны_ОРШ.jpg" "$DLTEST/" 2>/dev/null
cp -f "$WORKDL/BoQ_FTTH_Топольное_тест_генерализации.xlsx" "$DLTEST/" 2>/dev/null

echo; echo "===== ИТОГ ====="
python3 - << 'PY'
import json, os
W = '/home/z/my-project/work/topolnoe_test/work/topolnoe'
h = json.load(open(f'{W}/households.json'))
n2 = json.load(open(f'{W}/network_v2.json'))
st = n2.get('stats', {})
vp = f'{W}/vlm_verdicts.json'
vc = json.load(open(vp)) if os.path.exists(vp) else {}
b = json.load(open(f'{W}/boq.json'))
print(f"ДХ на мозаике: {len(h)} (было 397 до VLM)")
print(f"сеть в кадре: {st.get('served', '?')}/{st.get('households', st.get('households_in_crop', '?'))} ДХ,"
      f" муфт: {len(n2.get('couplers', []))}")
print(f"VLM-вердиктов в кэше: {len(vc)} (было 0)")
print(f"BoQ схема D: {b.get('dhx_served', '?')} ДХ, волокно {b.get('fiber_km', '?')} вол-км,"
      f" кабель {b.get('cable_km', '?')} км")
PY
echo "OK $(date '+%H:%M:%S')"
