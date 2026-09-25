#!/bin/bash
# 57_release_v7.sh — обновление релиза release-maps-vko до v7 (Task 57).
# Использование: ./57_release_v7.sh <GITHUB_FINEGRAINED_TOKEN>
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
REL_ID=394331188
OLD_ASSET_ID=587994687          # Karty_zon_ORSH_shema_D_VKO_v6.zip
ZIP="download/Карты_зон_ОРШ_схема_D_ВКО.zip"
NEW_NAME="Karty_zon_ORSH_shema_D_VKO_v7.zip"
cd /home/z/my-project || exit 1

echo "== [1/4] Удаление старого актива v6 (id=$OLD_ASSET_ID) =="
curl -s -m 60 -X DELETE -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/${OWNER}/${REPO}/releases/assets/${OLD_ASSET_ID}" \
  -w "HTTP %{http_code}\n" -o /dev/null

echo "== [2/4] Загрузка актива ${NEW_NAME} =="
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
"Обновление v7 (Task 57, 25.09.2026): ответы заказчика на вопросы v6 —\n"
"• Южный карман Алтайского: 4 частных дома подключены (+4 ДХ, дропы от муфт M7/M27/M25).\n"
"• Здание 637127295 — многоэтажка (подтверждение заказчика): 1→8 ДХ по формуле пайплайна (lv=2).\n"
"• Итог: Алтайский 650 ДХ; ВКО 3087 ДХ, 36 зон, 42 ОРШ, 1498,3 вол-км, 1103 муфты, 6938 сварок. QA ALL PASS.\n\n"
"Обновление v6 (Tasks 54–55): критерий «ТВ-антенны на крыше» (+3 барака × 8 ДХ), altay2.pdf "
"(283 — жилой барак 1→4 ДХ, cv-дуплекс 1→2). ВКО 3076 ДХ / 1497,1 вол-км.\n"
"Обновление v4 (Task 53): многоэтажки Алтайского получили квартиры (302 ДХ), фундамент, дуплексы.\n\n"
"Релизный zip — актив Release (лимит git-блоба 100 МБ). Содержимое идентично download/snp_vko/ "
"(карта 06 обновлена в v7)."
)
print(json.dumps({"name": "Карты зон ОРШ схема D (ВКО) — релизный zip v7", "body": body}, ensure_ascii=False))
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
        print('  ASSET:', a['name'], '| размер:', a['size'], '| state:', a['state'])"
echo "=== ГОТОВО ==="
