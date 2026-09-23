#!/bin/bash
# Task 47. Фоновая доверия VLM-верификации: ждём квоту, гоним 52b, контролируем остаток.
# Идемпотентно: 52b докачивает verdicts.json, скрипт можно перезапускать.
cd /home/z/my-project/scripts
LOG=/home/z/my-project/work/hh2/vlm_run_t47.log
echo "=== старт цикла $(date '+%F %T') ===" >> "$LOG"
for i in $(seq 1 120); do
  # 0) остаток
  python3 52f_remaining.py >> "$LOG" 2>&1
  if [ $? -eq 0 ]; then
    echo "[cycle $i] ВЕРИФИКАЦИЯ ЗАВЕРШЕНА $(date '+%F %T')" >> "$LOG"
    echo "VLM_DONE" > /home/z/my-project/work/hh2/vlm_t47_done.flag
    exit 0
  fi
  # 1) проба квоты
  if node 52b_quota_probe.mjs >> "$LOG" 2>&1; then
    echo "[cycle $i] квота есть, запуск 52b $(date '+%F %T')" >> "$LOG"
    timeout 5400 node 52b_vlm_verify.mjs >> "$LOG" 2>&1
    echo "[cycle $i] 52b завершился (код $?) $(date '+%F %T')" >> "$LOG"
    sleep 30
  else
    echo "[cycle $i] квота исчерпана, пауза 600 с $(date '+%F %T')" >> "$LOG"
    sleep 600
  fi
done
echo "=== лимит циклов исчерпан $(date '+%F %T') ===" >> "$LOG"
exit 1
