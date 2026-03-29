# Архитектура

## Диаграмма системы

```mermaid
flowchart TB
    TG[Telegram API] <-->|polling| Bot

    subgraph bot_layer ["Bot Service (aiogram 3.x)"]
        Bot[Handlers + FSM + Middlewares]
        User[User Service]
        Profile[Profile Service]
        Interaction[Interaction Service]
        ChatSvc[Chat Service]
        Referral[Referral Service]
        Ranking[Ranking Service]
        Queue[Profile Queue]
        Storage[Storage Service]
        Events[Event Publisher]

        Bot --> User & Profile & Interaction & ChatSvc & Referral
        Bot --> Queue
        Interaction & ChatSvc & Profile & Referral --> Events
        Queue --> Ranking
    end

    subgraph consumer_layer ["Event Consumer"]
        RS[Ranking Service —пересчёт рейтингов]
        NS[Notification Service —уведомления о мэтчах]
    end

    subgraph celery_layer ["Celery Worker"]
        Beat[Beat: пересчёт всех —рейтингов каждые 10 мин]
        Publish[Task: publish_event]
    end

    subgraph infra ["Инфраструктура"]
        DB[(PostgreSQL —9 таблиц)]
        Redis[(Redis —кэш + FSM)]
        MQ[[RabbitMQ —dating_events]]
        S3[(Minio S3 —фото)]
    end

    subgraph monitoring ["Мониторинг"]
        Prom[Prometheus] --> Graf[Grafana]
    end

    User & Profile & Interaction & ChatSvc & Ranking --> DB
    Queue --> Redis
    Storage --> S3
    Events --> Publish --> MQ

    MQ -->|ranking_service queue| RS
    MQ -->|notification_service queue| NS
    RS --> DB
    NS -->|Telegram Bot API| TG
    Beat --> DB

    Bot -->|metrics :9090| Prom
```

## Потоки данных

### 1. Регистрация

```
/start → Bot → User Service: get_or_create_user(telegram_id)
       → FSM: имя → возраст → пол → город → описание → фото → подтверждение
       → Profile Service: create_profile() + add_photo()
       → Фото: Telegram → download → Minio upload (fallback: file_id)
```

При переходе по реферальной ссылке (`/start ref_<telegram_id>`):
```
→ Referral Service: create_referral(referrer, referred)
→ Event: referral.created → MQ → Ranking Service: пересчёт рейтинга referrer'а
```

### 2. Просмотр анкет (лайк/пас)

```
«Смотреть анкеты» → Bot → Redis: pop_profile(user_id)
                         ├─ cache hit → показать анкету
                         └─ cache miss → DB: get_next_profiles(user_id)
                                        → Redis: fill_queue(10 анкет)
                                        → показать первую

Лайк → Interaction Service: record_like(from, to)
     → DB: INSERT INTO likes
     → Event: like.created → MQ → Ranking Service (фоновый пересчёт рейтинга)
     → Проверка взаимности → если мэтч:
       → DB: INSERT INTO matches
       → Event: match.created → MQ → Ranking Service (пересчёт обоих)
                                   → Notification Service (уведомление обоим через Telegram)

Пас → Interaction Service: record_pass(from, to)
    → Event: pass.created → MQ → Ranking Service (пересчёт)
```

### 3. Чат

```
«Мэтчи» → список мэтчей → inline-кнопки → выбор → FSM: ChatState.in_chat
         → Chat Service: get_messages(match_id, limit=20)

Сообщение → Chat Service: send_message(match_id, from_user, content)
          → DB: INSERT INTO messages
          → Event: message.created → MQ → Ranking Service (dialog initiation score)
          → Bot: send_message(partner_telegram_id) — НАПРЯМУЮ (мгновенно)
```

---

## Событийная архитектура (RabbitMQ)

### Обоснование

| Что через MQ | Почему |
|---|---|
| Пересчёт рейтинга | Тяжёлая операция (8+ SQL-запросов). Синхронно замедлило бы свайп на 200-500ms |
| Уведомление партнёра о мэтче | Fire-and-forget, партнёр не в текущем контексте |

| Что напрямую | Почему |
|---|---|
| Пересылка сообщений в чате | Чат должен быть мгновенным, MQ добавляет латентность |
| Инвалидация Redis-кэша | 1 вызов `redis.delete()`, дешевле чем MQ overhead |

### Exchange и очереди

```
Exchange: dating_events (topic, durable)

Queue: ranking_service (durable)
  Bindings: like.created, pass.created, match.created,
            message.created, referral.created,
            profile.updated, profile.deleted
  Action: _recalc_rating(user_id) — полный пересчёт рейтинга

Queue: notification_service (durable)
  Bindings: match.created
  Action: Telegram Bot API → отправка «Мэтч!» обоим пользователям
```

### Формат событий

```json
{
  "routing_key": "like.created",
  "body": {"from_user_id": 1, "to_user_id": 2}
}
```

Путь события: Сервис → `events.publish()` → Celery task `publish_event.delay()` → RabbitMQ → Consumer callback.

---

## Celery

| Задача | Расписание | Описание |
|--------|-----------|---------|
| `recalculate_ratings` | Каждые 10 мин (beat) | Полный пересчёт рейтингов всех активных пользователей |
| `publish_event` | По вызову | Публикация события в RabbitMQ exchange |

Брокер: RabbitMQ (`amqp://guest:guest@rabbitmq:5672/`).
Бэкенд результатов: Redis (`redis://redis:6379/1`).

---

## Redis

| Ключ | Тип | Назначение | TTL |
|------|-----|-----------|-----|
| `profile_queue:{user_id}` | List | Очередь из 10 предзагруженных анкет (JSON) | 600 сек |
| `fsm:*` | Hash | FSM-состояния aiogram | — |

---

## Мониторинг

### Prometheus метрики (`:9090/metrics`)

| Метрика | Тип | Описание |
|---------|-----|---------|
| `bot_handler_duration_seconds` | Histogram | Время обработки хэндлера (по имени) |
| `bot_likes_total` | Counter | Всего лайков |
| `bot_passes_total` | Counter | Всего пасов |
| `bot_matches_total` | Counter | Всего мэтчей |
| `bot_messages_total` | Counter | Всего сообщений в чатах |
| `bot_queue_fills_total` | Counter | Заполнений Redis-очереди из БД |
| `bot_queue_hits_total` | Counter | Анкет выдано из кэша |
| `bot_queue_misses_total` | Counter | Промахов кэша |

### Grafana дашборд

Provisioned автоматически при запуске (`infra/grafana/dashboards/dating_bot.json`):
- Rates: лайки/пасы/мэтчи в секунду
- Handler latency: p50, p95
- Queue hit rate
- Rating recalculation duration

---

## Docker Compose

| Контейнер | Образ | Порты | Зависимости |
|-----------|-------|-------|-------------|
| `postgres` | postgres:16-alpine | 5433:5432 | — |
| `redis` | redis:7-alpine | 6379 | — |
| `rabbitmq` | rabbitmq:3-management-alpine | 5672, 15672 | — |
| `minio` | minio/minio | 9000, 9001 | — |
| `bot` | Dockerfile | 9090 (metrics) | postgres, redis, rabbitmq (healthy) |
| `celery-worker` | Dockerfile | — | postgres, redis, rabbitmq (healthy) |
| `event-consumer` | Dockerfile | — | postgres, redis, rabbitmq (healthy) |
| `prometheus` | prom/prometheus | 9091:9090 | bot |
| `grafana` | grafana/grafana | 3000 | prometheus |

Healthcheck на всех инфра-контейнерах. App-контейнеры ждут готовности через `wait-for-services.py`.

Запуск: `docker-compose up -d` — одна команда поднимает всё.
