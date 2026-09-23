#!/bin/bash
# Фоновое страхующее копирование критичных данных в /tmp (Task 48)
# /tmp переживал платформенные сбросы в прошлом, но был вычищен — восстанавливаем.
LOG=/tmp/backup_t48.log
SRC=/home/z/my-project
DST=/tmp/my-project
echo "=== T48 backup start $(date) ===" > "$LOG"

mkdir -p "$DST"
# 1. Малые критичные данные (быстро)
rsync -a "$SRC/work" "$SRC/worklog.md" "$SRC/README.md" "$SRC/.gitignore" "$DST/" 2>>"$LOG"
echo "[1/3] work+docs done $(date)" >> "$LOG"

# 2. Код скриптов без кэша тайлов
rsync -a --exclude 'tiles_cache' "$SRC/scripts" "$DST/" 2>>"$LOG"
echo "[2/3] scripts(no tiles) done $(date)" >> "$LOG"

# 3. Полный .git (главный носитель бэкапа, ~600МБ) — тарболл одним файлом
mkdir -p /tmp/t48_gitpack
tar -C "$SRC" -cf /tmp/t48_gitpack/myproject_dotgit.tar .git 2>>"$LOG"
echo "[3/3] .git tarball done $(date), size: $(du -sh /tmp/t48_gitpack/myproject_dotgit.tar | cut -f1)" >> "$LOG"

echo "=== T48 backup FINISH $(date) ===" >> "$LOG"
