#!/bin/bash
# 49b: синхронизация OSS-бэкапа (Task 49) + обновление /tmp-страховки
LOG=/tmp/backup_t49_oss.log
OSS=/home/sync/ftth_vko_backup
SRC=/home/z/my-project
echo "=== T49 OSS sync start $(date) ===" > "$LOG"

# 1. Git-bundle (полная клонируемая история, 474 МБ)
cp /tmp/t48_gitpack/git_backup_main_20260923.bundle "$OSS/git_backup_main_20260923.bundle" 2>>"$LOG"
echo "[1/4] bundle -> OSS: $(du -sh $OSS/git_backup_main_20260923.bundle 2>/dev/null | cut -f1) $(date)" >> "$LOG"

# 2. Свежий worklog
cp "$SRC/worklog.md" "$OSS/worklog_current.md" 2>>"$LOG"
echo "[2/4] worklog_current.md обновлён $(date)" >> "$LOG"

# 3. README_restore.md — дополнение разделом Task 49 (idempotent: только если ещё нет)
if ! grep -q "Task 49" "$OSS/README_restore.md" 2>/dev/null; then
cat >> "$OSS/README_restore.md" <<'EOF'

## Task 49 (23.09.2026): git-бэкап проекта + GitHub (ожидание токена)

- **git_backup_main_20260923.bundle** (474 МБ) — полная клонируемая копия:
  `git clone git_backup_main_20260923.bundle restored_project` — восстановит
  рабочее дерево целиком (9372 файла: код, work/, карты, upload, тайлы).
- Локальная ветка main = 5 слоёв (L1 core → L5 ops); релизный zip 118 МБ
  лежит рядом (в git не входит — лимит 100 МБ).
- Пуш на GitHub (lagalsa-pixel/gpon-ftth-planner) подготовлен, но заблокирован
  правами токена (read-only): нужен Contents:Read+write + scope репо.
  Скрипт отправки: scripts/49_github_push.sh <TOKEN>.
- /tmp-страховка: work+docs+scripts(без тайлов) + .git-тарболл (598 МБ).
EOF
fi
echo "[3/4] README_restore.md дополнен $(date)" >> "$LOG"

# 4. Обновление /tmp-страховки (новые скрипты 49_*, worklog, .git c L5)
bash "$SRC/scripts/49_tmp_safety_copy.sh" >>"$LOG" 2>&1
echo "[4/4] /tmp refreshed $(date)" >> "$LOG"

echo "=== T49 OSS sync FINISH $(date) ===" >> "$LOG"
