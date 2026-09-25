#!/bin/bash
# 56_release_v6.sh — обновление релиза release-maps-vko до v6 (Tasks 54-55).
# Использование: ./56_release_v6.sh <GITHUB_FINEGRAINED_TOKEN>
# Процедура (по прецеденту Task 53): удалить актив v4 -> загрузить v6 ->
# переименовать релиз в v6 -> обновить описание.
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
REL_ID=394331188
OLD_ASSET_ID=587640558          # Karty_zon_ORSH_shema_D_VKO_v4.zip
ZIP="download/Карты_зон_ОРШ_схема_D_ВКО.zip"
NEW_NAME="Karty_zon_ORSH_shema_D_VKO_v6.zip"
cd /home/z/my-project || exit 1

echo "== [1/4] Удаление старого актива v4 (id=$OLD_ASSET_ID) =="
curl -s -m 60 -X DELETE -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/${OWNER}/${REPO}/releases/assets/${OLD_ASSET_ID}" \
  -w "HTTP %{http_code}\n" -o /dev/null

echo "== [2/4] Загрузка актива ${NEW_NAME} (124,6 МБ) =="
ENC=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$NEW_NAME'))")
UP=$(curl -s -m 900 -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/zip" --data-binary @"$ZIP" \
  "https://uploads.github.com/repos/${OWNER}/${REPO}/releases/${REL_ID}/assets?name=${ENC}")
echo "$UP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('name'):
    print('Актив:', d['name'], '| размер:', d['size'], '| state:', d['state'], '| id:', d['id'])
else:
    print('ОШИБКА загрузки:', d.get('message')); sys.exit(2)"

echo "== [3/4] Переименование релиза и обновление описания =="
BODY=$(python3 - <<'PYEOF'
import json
body = (
"Обновление v6 (Tasks 54–55, 25.09.2026):\n"
"• Task 55 (altay2.pdf «Эти здания жилые»): бараки 637127289/290/291 подтверждены заказчиком; "
"барак 637127283 — жилой (lv=1, 1→4 ДХ); cv-дуплекс без OSM-полигона (1→2 ДХ). "
"Алтайский 635→639 ДХ.\n"
"• Task 54 (критерий «ТВ-антенны на крыше»): полный аудит 297 зданий Алтайского (VLM, 4 прохода); "
"+3 пропущенных барака × 8 квартирных ДХ; −1 ложный дроп в руинах. Алтайский 615→635 ДХ.\n"
"• Итог по ВКО: 3076 ДХ, 36 зон, 42 ОРШ, 1497,1 вол-км, 1103 муфты, 65 сплиттеров, "
"5184 порта, 6914 сварок. QA ALL PASS.\n\n"
"Обновление v4 (Task 53): правки по замечаниям заказчика по Алтайскому — многоэтажные дома "
"получили квартиры (302 ДХ), добавлены неидентифицированные дома, фундамент будущего дома, "
"двухквартирные дома.\n\n"
"Релизный zip 124,6 МБ — превышает лимит git-блоба GitHub (100 МБ), поэтому приложен как актив "
"Release. Содержимое идентично каталогу download/snp_vko/ репозитория (карта 06 обновлена в v6)."
)
print(json.dumps({"name": "Карты зон ОРШ схема D (ВКО) — релизный zip v6", "body": body}, ensure_ascii=False))
PYEOF
)
curl -s -m 60 -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${REPO}/releases/${REL_ID}" \
  -d "$BODY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('Релиз:', d.get('name'), '| tag:', d.get('tag_name')) if d.get('name') else print('ОШИБКА:', d.get('message'))"

echo "== [4/4] Верификация =="
curl -s -m 30 -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/${OWNER}/${REPO}/releases" | python3 -c "
import json,sys
for r in json.load(sys.stdin):
    print('release:', r['name'], '| id:', r['id'])
    for a in r.get('assets', []):
        print('  ASSET:', a['name'], '| размер:', a['size'], '| state:', a['state'], '| downloads:', a['download_count'])"
echo "=== ГОТОВО ==="
