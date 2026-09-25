#!/bin/bash
# 59_release_v9.sh — обновление релиза release-maps-vko до v9 (Task 59: altay3 — Пригородное bid 688327687 многоквартирный 1-эт дом, 2->4 ДХ).
# Использование: ./59_release_v9.sh <GITHUB_FINEGRAINED_TOKEN>
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
REL_ID=394331188
OLD_ASSET_ID=588202155          # Karty_zon_ORSH_shema_D_VKO_v8.zip
ZIP="download/Карты_зон_ОРШ_схема_D_ВКО.zip"
NEW_NAME="Karty_zon_ORSH_shema_D_VKO_v9.zip"
cd /home/z/my-project || exit 1

echo "== [1/4] Удаление старого актива v8 (id=$OLD_ASSET_ID) =="
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
"Обновление v9 (Task 59, 25.09.2026) — altay3.pdf: «Это многоквартирный дом»:\n"
"• Пригородное, здание OSM 688327687 (10,9 x 25,6 м, 1-этажное, двускатная крыша):\n"
"  2 -> 4 ДХ по формуле квартир (lv=1, S=279,5 м2, 1 подъезд).\n"
"• На карте — значок МЖД с числом «4» (дропы скрыты, расчёт сохранён):\n"
"  значков МЖД теперь 32 (Пригородное +1, всего 486 ДХ под значками).\n"
"• Итоги: Пригородное 286 -> 288 ДХ; ВКО 3087 -> 3089 ДХ · 36 зон · 42 ОРШ ·\n"
"  1498,3 вол-км · 6942 сварки. QA ALL PASS (84/84).\n"
"• Скриншот заказчика привязан к карте (та же муфта 108 и трасса дропа);\n"
"  отчёт: download/snp_vko/altay3_task59_result.jpg.\n\n"
"Обновление v8 (Task 58): МЖД одним значком (31 здание) + этап ручной корректировки оператора.\n"
"Обновление v7 (Task 57): южный карман +4 дома; 637127295 многоэтажка 1→8 ДХ. ВКО 3087 ДХ.\n"
"Обновление v6 (Tasks 54–55): критерий ТВ-антенн, altay2.pdf. ВКО 3076 ДХ.\n"
"Обновление v4 (Task 53): квартиры многоэтажек, дуплексы, фундамент.\n\n"
"Релизный zip — актив Release (лимит git-блоба 100 МБ). Содержимое идентично download/snp_vko/ "
"(карты обновлены в v9)."
)
print(json.dumps({"name": "Карты зон ОРШ схема D (ВКО) — релизный zip v9", "body": body}, ensure_ascii=False))
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
rl = json.load(sys.stdin)
for r in rl:
    print('release:', r['name'], '| tag:', r['tag_name'])
    for a in r.get('assets', []):
        print('   asset:', a['name'], a['size'], 'id', a['id'], a['state'])
        assert a['state'] == 'uploader' or a['state'] == 'uploaded', 'актив не загружен!'
print('OK')"
