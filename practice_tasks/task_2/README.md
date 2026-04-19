# Task 2 — Сравнение RabbitMQ и Redis

Стенд из трёх частей: `producer` → `broker` → `consumer`. Общий Python-образ для
producer/consumer, переключение брокера через env. Измеряются throughput,
latency (avg / p95 / p99 / max), потери и пиковый backlog.

## Структура

```
Dockerfile                       общий образ producer+consumer
docker-compose.rabbit.yml        стек с RabbitMQ
docker-compose.redis.yml         стек с Redis (LIST)
src/
  main.py                        dispatch по ROLE
  broker.py                      ABC Broker + фабрика
  rabbit_client.py               pika BlockingConnection
  redis_client.py                RPUSH / BLPOP
  producer.py                    генератор с pacer-ом
  consumer.py                    приёмник с latency-статистикой и depth-семплером
  payload.py                     формат сообщения (seq + send_ts_ns + padding)
  rate_limiter.py                deadline-based pacer
  wait_for.py                    ретраи на connect
  metrics.py                     агрегация raw/*.json -> summary.csv
scripts/
  run_matrix.py                  прогон всей матрицы
  single_run.sh                  одиночный прогон для отладки
results/
  raw/                           JSON producer/consumer для каждого прогона
  summary.csv                    агрегированная таблица
  screenshots/                   скриншоты для отчёта
report/
  REPORT.md                      отчёт
```

## Одиночный прогон

```bash
# broker: rabbit | redis
./scripts/single_run.sh rabbit 1024 1000 30
./scripts/single_run.sh redis 1024 1000 30
```

Результат: `results/raw/smoke_<broker>_<size>_<rate>_{producer,consumer}.json`.

## Полная матрица

```bash
python scripts/run_matrix.py               # 24 прогона, ~15 минут
python scripts/run_matrix.py --quick       # сокращённая матрица для дыма
python scripts/run_matrix.py --only rabbit # только один брокер
```

В конце создаётся `results/summary.csv` с колонками:
`run_id, broker, msg_size, target_rate, duration, sent, received, lost,
send_errors, consume_errors, actual_rate_in, actual_rate_out,
avg_latency_ms, p50_ms, p95_ms, p99_ms, max_ms, peak_backlog`.

## Агрегация без повторного прогона

```bash
python src/metrics.py results/raw results/summary.csv
```

## Матрица экспериментов

- брокеры: `rabbit`, `redis`;
- размер сообщения: 128 B, 1 KB, 10 KB, 100 KB;
- интенсивность: 1 000, 5 000, 10 000 msg/s;
- длительность: 30 s на ячейку;
- лимиты брокера: `cpus=1.0`, `memory=512M`.

## Зависимости

- Docker Desktop / Docker Engine с `docker compose` v2.
- На Windows `single_run.sh` запускать через Git Bash.
