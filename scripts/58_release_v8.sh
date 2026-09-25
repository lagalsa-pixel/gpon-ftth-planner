#!/bin/bash
# 58_release_v8.sh — обновление релиза release-maps-vko до v8 (Task 58).
# Использование: ./58_release_v8.sh <GITHUB_FINEGRAINED_TOKEN>
set -u
TOKEN="${1:?Укажите токен: $0 <token>}"
OWNER=lagalsa-pixel
REPO=gpon-ftth-planner
REL_ID=394331188
OLD_ASSET_ID=588118282          # Karty_zon_ORSH_shema_D_VKO_v7.zip
ZIP="download/Карты_зон_ОРШ_схема_D_ВКО.zip"
NEW_NAME="Karty_zon_ORSH_shema_D_VKO_v8.zip"
cd /home/z/my-project || exit 1

echo "== [1/4] Удаление старого актива v7 (id=$OLD_ASSET_ID) =="
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
"Обновление v8 (Task 58, 25.09.2026) — отображение МЖД и этап ручной корректировки:\n"
"• Многоэтажные дома (МЖД) на картах — ОДИН значок с числом квартир вместо группы абонентов:\n"
"  дропы и этажные распределительные коробки не прорисованы, РАСЧЁТ ПОЛНОСТЬЮ СОХРАНЁН.\n"
"• 31 значок: Алтайский 24 здания (338 ДХ), Верхнеберезовка 7 зданий (144 ДХ).\n"
"  Дуплексы (2 ДХ) и дворовые дома (3 ДХ) — с отдельными дропами, как раньше.\n"
"• Итоги без изменений: ВКО 3087 ДХ · 36 зон · 42 ОРШ · 1498,3 вол-км · 6938 сварок. QA ALL PASS.\n"
"• Легенда карт: добавлена строка МЖД (заодно исправлено переполнение строк фидер/ОРШ/ЦУ из v7).\n"
"• Новый этап конвейера — ручная корректировка оператора: HTML-страницы контроля ДХ\n"
"  (download/snp_vko/operator_review/<село>/index.html, без сервера), правки выгружаются\n"
"  в corrections.json и применяются идемпотентно (58c_apply_corrections.py) — правки\n"
"  не теряются при перегенерации. Отчёт: download/snp_vko/task58_mzd_operator.jpg.\n\n"
"Обновление v7 (Task 57): южный карман +4 дома; 637127295 многоэтажка 1→8 ДХ. ВКО 3087 ДХ.\n"
"Обновление v6 (Tasks 54–55): критерий ТВ-антенн, altay2.pdf. ВКО 3076 ДХ.\n"
"Обновление v4 (Task 53): квартиры многоэтажек, дуплексы, фундамент.\n\n"
"Релизный zip — актив Release (лимит git-блоба 100 МБ). Содержимое идентично download/snp_vko/ "
"(карты обновлены в v8)."
)
print(json.dumps({"name": "Карты зон ОРШ схема D (ВКО) — релизный zip v8", "body": body}, ensure_ascii=False))
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
