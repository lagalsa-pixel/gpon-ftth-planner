# FTTH ВКО — резервные копии (OSS, персистентно)

Каталог: `/home/sync/ftth_vko_backup/` (ossfs — выживает при сбросе окружения)

## Состав

| Артефакт | Содержимое | Назначение |
|---|---|---|
| `ftth_vko_essentials_<дата>.tar` | worklog.md, scripts/ (211), work/*.json (книги BoQ v1–v4, сводки, геопривязка), work/hh2/ (кандидаты + ВЕРДИКТЫ VLM + стеки, 157 МБ), work/<село>/*.json (сети, домохозяйства, якоря, OSM), work/<село>/mosaic.jpg (6 мозаик), work/tiles/ (кэш тайлов Google z18), .env | Полное возобновление проекта |
| `ftth_pipeline/` | Переиспользуемый конвейер FTTH (v2.3) + README методологии + демо Бобровки | Поставка заказчику |

## Восстановление после сброса окружения

```bash
# 1. распаковать в /home/z/my-project (создать, если пуст)
cd /home/z/my-project
tar -xf /home/sync/ftth_vko_backup/ftth_vko_essentials_<дата>.tar
mv tmp/my-project/.env . 2>/dev/null; rm -rf tmp   # .env из архива

# 2. проверить целостность
ls scripts | wc -l          # ожидается 211
find work -type f | wc -l   # ожидается ~15000
python3 scripts/52f_remaining.py   # остаток VLM-верификации

# 3. продолжение Task 47 (если верификация не завершена)
cd scripts && VLM_INT=20000 VLM_CONC=1 bash 52b_call_t47.sh   # раунды до TOTAL 0
bash 47_final_chain.sh                                          # финальная пересборка (БЕЗ смет)

# 4. deliverables появляются в download/ (карты snp_vko, zip, PDF, xlsx)
```

## Примечания

- Квота VLM: ~200–240 вызовов/сутки (разделяемая); при 429 — ждать, оркестратор сам ждёт и докачивает
- Сметы ИСКЛЮЧЕНЫ из комплекта (решение заказчика, Task 46)
- Порядок книг: строго 30 → 34; 48b и 54 требуют `FTTH_NET_OVERRIDE=network_hh2.json`
- Вердикты VLM (work/hh2/*/verdicts.json) — невосполнимы без повторного расхода квоты: беречь
