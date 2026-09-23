#!/bin/bash
# 48_github_push.sh — отправка бэкапа FTTH-проекта ВКО на GitHub (Task 48)
# Использование:  ./48_github_push.sh <GITHUB_FINEGRAINED_TOKEN>
# Требования к токену:
#   Repository access: lagalsa-pixel/gpon-ftth-planner (или "All repositories")
#   Permissions -> Repository permissions -> Contents: Read and write
# Слои пушатся поштучно (L1..L5) — устойчивость к обрывам: повторный запуск
# продолжает с места остановки (уже запушенное пропускается).
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
URL="https://x-access-token:${TOKEN}@github.com/${OWNER}/${REPO}.git"
cd /home/z/my-project || exit 1
FAIL=0

echo "== [0/4] Проверка токена =="
LOGIN=$(curl -s -m 20 -H "Authorization: Bearer $TOKEN" https://api.github.com/user | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('login',''))" 2>/dev/null)
[ -n "$LOGIN" ] || { echo "ОТКАЗ: токен невалиден"; exit 1; }
echo "Токен пользователя: $LOGIN"

echo "== [1/4] Послойный git-push =="
for CMT in $(git rev-list --reverse main); do
  MSG=$(git log -1 --format=%s "$CMT" | head -c 60)
  # пропуск уже запушенного: сравнить с remote main
  REM=$(git ls-remote "$URL" refs/heads/main 2>/dev/null | cut -f1)
  if [ "$REM" = "$CMT" ] || git merge-base --is-ancestor "$CMT" "$REM" 2>/dev/null; then
    echo "  [skip] $CMT ($MSG) — уже на GitHub"
    continue
  fi
  echo "  [push] $CMT ($MSG) ..."
  if git push "$URL" "$CMT:refs/heads/main" 2>&1 | tail -2; then :; else
    echo "  !! Слой $CMT не запушен (прервано?) — перезапустите скрипт"; FAIL=1; break
  fi
done
[ $FAIL -eq 0 ] && echo "git-push завершён: $(git -c core.quotepath=false ls-files | wc -l) файлов в репо"

echo "== [2/4] Создание Release =="
ZIPNAME="Карты_зон_ОРШ_схема_D_ВКО.zip"
REL=$(curl -s -m 30 -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${REPO}/releases" \
  -d "{\"tag_name\":\"release-maps-vko\",\"target_commitish\":\"main\",\"name\":\"Карты зон ОРШ схема D (ВКО) — релизный zip\",\"body\":\"Релизный zip 118 МБ — превышает лимит git-блоба GitHub (100 МБ), поэтому приложен как актив Release. Содержимое идентично каталогу download/snp_vko/ репозитория.\"}")
REL_ID=$(echo "$REL" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('id',''))" 2>/dev/null)
if [ -z "$REL_ID" ]; then echo "Release не создан:"; echo "$REL" | head -5; exit 2; fi
echo "Release id=$REL_ID"

echo "== [3/4] Загрузка zip-актива (118 МБ) =="
ENC=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$ZIPNAME'))")
UP=$(curl -s -m 900 -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/zip" \
  --data-binary @"download/$ZIPNAME" \
  "https://uploads.github.com/repos/${OWNER}/${REPO}/releases/${REL_ID}/assets?name=${ENC}")
echo "$UP" | python3 -c "import json,sys;d=json.load(sys.stdin);print('Актив:',d.get('name'),'| размер:',d.get('size'),'| state:',d.get('state')) if d.get('name') else print('ОШИБКА:',d.get('message'))" 2>/dev/null || echo "$UP" | head -3

echo "== [4/4] Верификация =="
curl -s -m 20 -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/${OWNER}/${REPO}" | python3 -c "import json,sys;d=json.load(sys.stdin);print('Размер репо: %.0f МБ | default_branch: %s'%(d.get('size',0)/1024,d.get('default_branch')))"
curl -s -m 20 -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/${OWNER}/${REPO}/commits?per_page=10" | python3 -c "import json,sys;[print(' commit:',c['sha'][:7],c['commit']['message'].split(chr(10))[0][:70]) for c in json.load(sys.stdin)]"
echo "=== ГОТОВО ==="
