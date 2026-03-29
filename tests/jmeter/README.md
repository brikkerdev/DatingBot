# Нагрузочное тестирование (Apache JMeter)

## Запуск

1. Запустить бота в webhook-режиме:
   ```
   WEBHOOK_ENABLED=true python -m src.bot
   ```

2. Открыть JMeter и загрузить `dating_bot_load_test.jmx`

3. Или запустить из CLI:
   ```
   jmeter -n -t dating_bot_load_test.jmx -l results.csv -e -o report/
   ```

## Тест-план

- **Registration Load**: 50 потоков × 10 итераций, ramp-up 30 сек — имитирует команду `/start`
- **Metrics Endpoint**: 10 потоков × 100 итераций — нагрузка на Prometheus `/metrics`

## Параметры

| Переменная    | По умолчанию | Описание           |
|---------------|:------------:|---------------------|
| HOST          | localhost    | Хост бота           |
| PORT          | 8443         | Порт webhook        |
| METRICS_PORT  | 9090         | Порт метрик         |
