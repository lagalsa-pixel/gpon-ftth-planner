#!/bin/bash
# 60_release_v10.sh — обновление релиза release-maps-vko до v10
# (Task 60: altay3 — ИСПРАВЛЕНИЕ: здание в селе Алтайский, вне-OSM барак
#  у муфты M24, 2->4 ДХ; правка Task 59 по Пригородному отменена).
# Использование: ./60_release_v10.sh <GITHUB_FINEGRAINED_TOKEN>
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
REL_ID=394331188
OLD_ASSET_ID=588306744          # Karty_zon_ORSH_shema_D_VKO_v9.zip
ZIP="download/Карты_зон_ОРШ_схема_D_ВКО.zip"
NEW_NAME="Karty_zon_ORSH_shema_D_VKO_v10.zip"
cd /home/z/my-project || exit 1

echo "== [1/4] Удаление старого актива v9 (id=$OLD_ASSET_ID) =="
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
"Обновление v10 (Task 60, 25.09.2026) — altay3.pdf: «Это многоквартирный дом», ИСПРАВЛЕНИЕ v9:\n"
"• Заказчик уточнил: здание со скриншота — из села АЛТАЙСКИЙ (не Пригородное).\n"
"• Идентификация: цветовой маск-матчинг символики по карте v4 — кабель, муфта M24,\n"
"  жёлтый дроп, квадрат ДХ и даже обрезанные фрагменты слева совпали с точностью 1-2 px.\n"
"• Здание: вне-OSM барак 29,8 x 14,5 м (тёмная двускатная крыша, 3 крыльца, 1 этаж —\n"
"  3 VLM-прохода, в т.ч. калибровка по известному 2-эт бараку рядом); это же здание\n"
"  заказчик показывал в altay2 (img_12, «дуплекс», Task 55).\n"
"• 2 -> 4 ДХ по формуле квартир (lv=1, S=432 м2, 1 подъезд); значок МЖД «4»;\n"
"  здание добавлено в OSM-слой (полигон по спутнику).\n"
"• Правка Task 59 по Пригородному ОТМЕНЕНА (288 -> 286 ДХ) — ложная идентификация\n"
"  (цвет квадрата сэмплировался без сдвига шапки карты +300 px).\n"
"• Легенда карты 06 больше не накрывает значки МЖД (вес в выборе позиции поднят):\n"
"  именно из-за легенды BR значок был не виден и заказчик смотрел старую карту v4.\n"
"• Итоги: Алтайский 650 -> 652 ДХ; ВКО 3089 ДХ (без изменений) · 36 зон · 42 ОРШ ·\n"
"  1499,2 вол-км (+0,9) · 6942 сварки. QA ALL PASS.\n"
"• Отчёт: download/snp_vko/altay3_task60_result.jpg.\n\n"
"Обновление v9 (Task 59, отменено Task 60): ложная привязка к Пригородному.\n"
"Обновление v8 (Task 58): МЖД одним значком (31 здание) + этап ручной корректировки оператора.\n"
"Обновление v7 (Task 57): южный карман +4 дома; 637127295 многоэтажка 1→8 ДХ. ВКО 3087 ДХ.\n"
"Обновление v6 (Tasks 54–55): критерий ТВ-антенн, altay2.pdf. ВКО 3076 ДХ.\n"
"Обновление v4 (Task 53): квартиры многоэтажек, дуплексы, фундамент.\n\n"
"Релизный zip — актив Release (лимит git-блоба 100 МБ). Содержимое идентично download/snp_vko/ "
"(карты 05 и 06 обновлены в v10)."
)
print(json.dumps({"name": "Карты зон ОРШ схема D (ВКО) — релизный zip v10", "body": body}, ensure_ascii=False))
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
