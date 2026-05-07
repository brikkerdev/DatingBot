# SQL Isolation Anomalies Practice

Воспроизводит 4 аномалии изоляции в SQL-транзакциях:
- Dirty Read
- Non-Repeatable Read
- Phantom Read
- Lost Update

## Стек

- Python 3.12+
- MySQL 8
- Docker Compose
- aiomysql

## Быстрый старт

```bash
# Запустить БД и тесты
docker compose up --build
```

После прогона runner завершится, БД продолжит работать. Остановить:

```bash
docker compose down
```

## Ручной запуск без Docker

```bash
# Установить зависимости
pip install -r requirements.txt

# Поднять MySQL 8 локально и создать БД isolation_db
# с пользователем isolation_user / isolation_pass

# Запустить тесты
python scripts/run_all.py
```

## Результаты

- `results/<anomaly>.json` — итог по каждой аномалии
- `results/run.log` — общий лог
- `report/REPORT.md` — отчёт со скриншотами

## Аномалии

### Dirty Read
Чтение неподтверждённых данных другой транзакцией.

### Non-Repeatable Read
Повторное чтение той же строки даёт разные результаты.

### Phantom Read
Повторный запрос возвращает разное количество строк.

### Lost Update
Одна из параллельных операций обновления теряется.
