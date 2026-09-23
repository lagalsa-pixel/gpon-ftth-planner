#!/bin/bash
# Task 48: скачать 6 референсных статей по проектированию PON через z-ai page_reader
OUT=/home/z/my-project/work/ref_materials
mkdir -p "$OUT"
cd "$OUT"

declare -A URLS=(
  [01_foxes_xpon]="https://foxes-com.ru/articles/xpon-m/tekhnologii-postroeniya-xpon"
  [02_netsol]="https://netsol.shop/index.php?route=blog/article&article_id=132"
  [03_donntu]="https://masters.donntu.ru/2019/fkita/muzhetsky/library/article4.htm#lib"
  [04_bibliofond]="https://www.bibliofond.ru/view.aspx?id=599313"
  [05_prorostelecom]="https://prorostelecom.ru/voprosy/gpon-kabel.html"
  [06_begemot]="https://begemot.ai/projects/5959905-proektirovanie-pon-setei-v-castnom-sektore"
)

ok=0; fail=0
for key in $(echo "${!URLS[@]}" | tr ' ' '\n' | sort); do
  url="${URLS[$key]}"
  f="$key.json"
  if [ -s "$f" ] && python3 -c "import json;d=json.load(open('$f'));assert d.get('title') or d.get('html')" 2>/dev/null; then
    echo "SKIP $key (уже скачан)"; ok=$((ok+1)); continue
  fi
  echo "=== $key : $url"
  for attempt in 1 2 3; do
    if timeout 90 z-ai function -n page_reader -a "{\"url\": \"$url\"}" -o "$f" >/dev/null 2>&1; then
      if python3 -c "import json;d=json.load(open('$f'));t=d.get('html') or '';assert len(t)>500" 2>/dev/null; then
        echo "OK $key ($(stat -c%s "$f") байт, попытка $attempt)"; ok=$((ok+1)); break
      fi
    fi
    echo "  попытка $attempt не удалась, ждём 5с..."; sleep 5
    [ "$attempt" = "3" ] && { echo "FAIL $key"; fail=$((fail+1)); mv "$f" "$f.bad" 2>/dev/null; }
  done
done
echo "===ИТОГ: ok=$ok fail=$fail==="
ls -la "$OUT"
