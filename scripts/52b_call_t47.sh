#!/bin/bash
# Task 47. Оркестратор порционной верификации (v2, минимальное давление на лимитер):
# одна проба в начале вызова; при успехе — валидация парного режима и/или прогон 52b;
# при неудаче — сон до конца вызова. Прогресс целиком в файлах (докачка).
cd /home/z/my-project/scripts
LOG=/home/z/my-project/work/hh2/vlm_run_t47.log
HH=/home/z/my-project/work/hh2
echo "=== вызов $(date '+%F %T') ===" >> "$LOG"
END=$((SECONDS+555))

probe_ok() { node 52b_quota_probe.mjs >> "$LOG" 2>&1; }

while [ $SECONDS -lt $((END-25)) ]; do
  if ! probe_ok; then
    sleep 265; continue
  fi
  echo "[run] квота есть $(date '+%T')" >> "$LOG"

  # --- фаза валидации (однократно) ---
  if [ ! -f "$HH/val_done.flag" ]; then
    echo "[val] прогон контрольных стеков" >> "$LOG"
    timeout $((END-SECONDS)) node 52h_run_val.mjs >> "$LOG" 2>&1
    DONE_N=$(python3 -c "import json,os; p='$HH/val_verdicts.json'; print(len(json.load(open(p))) if os.path.exists(p) else 0)")
    TOTAL_N=$(python3 -c "import json; print(len(json.load(open('$HH/val_stacks.json'))))")
    if [ "$DONE_N" -lt "$TOTAL_N" ]; then
      echo "[val] завершено $DONE_N/$TOTAL_N — продолжим в следующем вызове" >> "$LOG"
      continue
    fi
    python3 52i_compare_val.py >> "$LOG" 2>&1
    if python3 52i_compare_val.py >/dev/null 2>&1; then
      # код выхода 52i: 0 = допустим (grep по строке «ДОПУСТИМ» ошибочно
      # матчил и «НЕ ДОПУСТИМ» — из-за этого режим однажды был выбран неверно)
      echo STACK > "$HH/mode.txt"
    else
      echo SINGLE > "$HH/mode.txt"
    fi
    touch "$HH/val_done.flag"
    echo "[val] режим: $(cat $HH/mode.txt)" >> "$LOG"
  fi

  # --- основной прогон ---
  MODE=$(cat "$HH/mode.txt" 2>/dev/null || echo SINGLE)
  if [ "$MODE" = "STACK" ]; then
    VLM_STACK=2 timeout $((END-SECONDS)) node 52b_vlm_verify.mjs >> "$LOG" 2>&1
  else
    timeout $((END-SECONDS)) node 52b_vlm_verify.mjs >> "$LOG" 2>&1
  fi
  rc=$?
  echo "[run] 52b rc=$rc $(date '+%T')" >> "$LOG"
  python3 52f_remaining.py >> "$LOG" 2>&1
  if python3 52f_remaining.py 2>/dev/null | grep -q "^TOTAL 0"; then
    echo "VLM_DONE $(date '+%F %T')" >> "$LOG"; exit 0
  fi
done
python3 52f_remaining.py
exit 3
