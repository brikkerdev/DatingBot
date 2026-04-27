# task_3 — Сравнение типов кеширования

Реализованы три стратегии кеширования (Cache-Aside, Write-Through, Write-Back) поверх
одного и того же стека PostgreSQL + Redis. Единый тест прогоняется на трёх профилях
нагрузки (read_heavy 80/20, balanced 50/50, write_heavy 20/80).

## Стек

- Python 3.12, `psycopg[binary]==3.2.3`, `redis==5.2.1`
- PostgreSQL 16 alpine, Redis 7.4 alpine
- Docker Compose v2

## Запуск

```bash
# полная матрица: 3 стратегии × 3 профиля = 9 ячеек, по 60 секунд
python scripts/run_matrix.py

# быстрый smoke (15 секунд на ячейку)
python scripts/run_matrix.py --quick

# одна ячейка
STRATEGY=write_back PROFILE=balanced READ_RATIO=0.5 RUN_ID=demo \
  docker compose up --build --abort-on-container-exit runner
```

Результаты:
- `results/raw/<strategy>_<profile>.json` — метрики ячейки
- `results/raw/<strategy>_<profile>_dirty.json` — таймсерия dirty_set (только для write_back)
- `results/summary.csv` — сводная таблица по всем ячейкам

## Метрики

`throughput_rps`, `avg_latency_ms`, `p50/p95/p99_ms`, `cache_hits`, `cache_misses`,
`hit_rate`, `db_reads`, `db_writes`. Для write-back дополнительно
`wb_flushed_during` (сколько фоном отправлено в БД во время теста) и
`wb_drained_at_end` (сколько добито при завершении).

Подробный отчёт — в `report/REPORT.md`.
