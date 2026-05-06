# SQL Isolation Anomalies Practice

Воспроизводит 4 аномалии изоляции в SQL-транзакциях:
- Dirty Read
- Non-Repeatable Read
- Phantom Read
- Lost Update

## Требования

- Python 3.12+
- PostgreSQL 14+
- Docker (опционально)

## Быстрый старт

```bash
# 1. Запустить PostgreSQL
docker compose up -d db

# 2. Собрать и запустить тесты
docker compose up --build runner
```

## Ручной запуск без Docker

```bash
# Установить зависимости
pip install -r requirements.txt

# Создать БД
createdb isolation_db -U postgres

# Запустить тесты
python -m src.isolated_tx
```

## Результаты

- `results/<anomaly>.json` - логи и результаты каждой аномалии
- `report/REPORT.md` - отчёт

## Аномалии

### Dirty Read
Чтение неподтверждённых данных другой транзакцией.

### Non-Repeatable Read  
Повторное чтение той же строки даёт разные результаты.

### Phantom Read
Повторный запрос возвращает разное количество строк.

### Lost Update
Одна из параллельных операций обновления теряется.