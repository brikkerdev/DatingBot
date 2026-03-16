## Диаграмма потоков данных (Mermaid)

```mermaid
flowchart TB
    subgraph External
        TG[Telegram API]
    end

    subgraph BotLayer
        Bot[Bot Service<br/>aiogram 3.x]
    end

    subgraph CoreServices
        User[User Service]
        Profile[Profile Service]
        Rank[Ranking Service]
        Interact[Interaction Service]
        Chat[Chat Service]
    end

    subgraph Data
        DB[(PostgreSQL)]
        Redis[(Redis)]
        S3[(S3 Storage)]
    end

    subgraph Async
        MQ[RabbitMQ]
        Celery[Celery Workers]
    end

    TG <-->|Webhook| Bot
    Bot -->|HTTP/gRPC| User
    Bot -->|HTTP/gRPC| Profile
    Bot -->|HTTP/gRPC| Rank
    Bot -->|HTTP/gRPC| Interact
    Bot -->|HTTP/gRPC| Chat

    User --> DB
    Profile --> DB
    Profile --> S3
    Rank --> DB
    Rank --> Redis
    Interact --> DB
    Interact -->|publish| MQ
    MQ -->|consume| Celery
    Celery --> Rank
    Chat --> DB
```

## Сценарии использования

### 1. Регистрация и создание анкеты

```
User → Telegram /start → Bot → User Service (create/get by telegram_id)
     → Bot → Profile Service (create/update profile, upload photos)
     → Profile Service → S3 (загрузка фото)
     → Сохранение метаданных в PostgreSQL
```

**Детали:**
- User Service генерирует внутренний `user_id` (UUID v4)
- Profile Service валидирует: возраст ≥18, bio ≤500 символов, 1-6 фото
- Фото загружаются в S3 по пути: `profiles/{user_id}/{photo_id}.{ext}`
- В БД сохраняются метаданные: `storage_path`, `sort_order`, `content_type`

---

### 2. Просмотр анкет (лайк/пас)

```
User → "Смотреть анкеты" → Bot → Ranking Service (get next profiles)
     → Ranking Service проверяет Redis кэш (ranking:queue:{user_id})
     → Если кэш пуст: загрузка 10 анкет из PostgreSQL
     → Bot → Profile Service (get profile details + photos URLs)
     → Показ анкеты пользователю

User → Лайк → Bot → Interaction Service (like(from_user, to_user))
     → Interaction Service → PostgreSQL (запись в likes)
     → Проверка на взаимный лайк (exists like where from=B, to=A)
     → Если мэтч: создание записи в matches → Chat Service (init chat)
     → Публикация события в RabbitMQ (event: user_liked, event: match_created)
     → RabbitMQ → Celery → Ranking Service (обновление поведенческого рейтинга)
```

**Детали:**
- Redis ключ: `ranking:queue:{user_id}` — список profile_id (LIFO)
- Размер очереди: 10 анкет (фиксированное значение)
- При достижении конца очереди — новая выборка из БД
- Исключаются: уже лайкнутые, пропущенные, собственный профиль
- RabbitMQ exchange: `dating_events`, routing keys: `user.liked`, `user.passed`, `match.created`
- Celery задача: `update_behavioral_rating(event_type, from_user, to_user)`

---

### 3. Чат после мэтча

```
User → Выбор мэтча → Bot → Chat Service (get_dialogs(user_id))
     → Chat Service → PostgreSQL (SELECT FROM matches JOIN profiles)
     → Возврат списка диалогов с последним сообщением

User → Сообщение → Bot → Chat Service (send(match_id, from_user, text))
     → Валидация: from_user ∈ (user1_id, user2_id) для match
     → Валидация: длина текста ≤2000 символов
     → Chat Service → PostgreSQL (INSERT INTO messages)
     → Публикация события в RabbitMQ (event: message_sent)
     → RabbitMQ → Bot Service (уведомление получателю)
```

**Детали:**
- Индекс в БД: `(match_id, created_at)` для быстрого получения истории
- Лимит истории: 50 последних сообщений (настраиваемо)
- Статус прочтения: `mark_read(match_id, user_id)` обновляет `read_at`

---

## Технические детали компонентов

### Bot Service

| Параметр | Значение |
|----------|----------|
| Фреймворк | aiogram 3.x |
| Язык | Python 3.11+ |
| Режим получения | Webhook (HTTPS endpoint) |
| FSM Storage | Redis (key: `fsm:{telegram_id}`) |
| Таймаут запросов | 30 секунд |
| Лимит сообщений | 60 в минуту на пользователя |

**Структура состояний FSM:**
```python
class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_city = State()
    waiting_for_bio = State()
    waiting_for_interests = State()
    waiting_for_photos = State()
```

---

### User Service

**Таблица `users`:**
```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_users_telegram ON users(telegram_id);
CREATE INDEX idx_users_active ON users(is_active) WHERE is_active = FALSE;
```

**API методы:**
| Метод | Endpoint | Метод | Тело |
|-------|----------|-------|------|
| `get_or_create` | `POST /users/get-or-create` | POST | `{telegram_id: number}` |
| `get` | `GET /users/{user_id}` | GET | — |
| `update_last_active` | `PATCH /users/{user_id}/active` | PATCH | — |

---

### Profile Service

**Таблицы:**
```sql
CREATE TABLE profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(user_id),
    name VARCHAR(100) NOT NULL,
    age INTEGER NOT NULL CHECK (age >= 18),
    gender VARCHAR(20) NOT NULL,
    city VARCHAR(100) NOT NULL,
    bio VARCHAR(500),
    interests TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE profile_photos (
    photo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID REFERENCES profiles(profile_id),
    storage_path VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL,
    content_type VARCHAR(50) DEFAULT 'image/jpeg',
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_photos_profile ON profile_photos(profile_id, sort_order);
```

**S3 структура:**
```
s3://dating-bot-profiles/
└── profiles/
    └── {user_id}/
        ├── {photo_id}.jpg
        ├── {photo_id}.png
        └── {photo_id}.webp
```

---

### Ranking Service

**Таблица `user_ratings`:**
```sql
CREATE TABLE user_ratings (
    user_id UUID PRIMARY KEY REFERENCES users(user_id),
    primary_score DECIMAL(5,2) DEFAULT 0,
    behavior_score DECIMAL(5,2) DEFAULT 0,
    combined_score DECIMAL(5,2) DEFAULT 0,
    last_calculated TIMESTAMPTZ DEFAULT NOW()
);
```

**Формула комбинированного рейтинга:**
```
combined_score = (primary_score × 0.4) + (behavior_score × 0.5) + (referral_bonus × 0.1)

primary_score = (profile_completeness × 30) + (photo_count × 5) + (interests_count × 3)
behavior_score = (likes_received × 2) + (matches × 5) + (messages_sent × 1) - (passes_received × 1)
referral_bonus = referred_users_active × 10
```

**Redis структура:**
```
Key: ranking:queue:{user_id}
Type: List
Values: [profile_id_1, profile_id_2, ..., profile_id_10]
TTL: 1 час (обновляется при активности)
```

---

### Interaction Service

**Таблицы:**
```sql
CREATE TABLE likes (
    from_user_id UUID REFERENCES users(user_id),
    to_user_id UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (from_user_id, to_user_id)
);

CREATE TABLE passes (
    from_user_id UUID REFERENCES users(user_id),
    to_user_id UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (from_user_id, to_user_id)
);

CREATE TABLE matches (
    match_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user1_id UUID REFERENCES users(user_id),
    user2_id UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    CONSTRAINT unique_match UNIQUE (user1_id, user2_id),
    CONSTRAINT check_user_order CHECK (user1_id < user2_id)
);
CREATE INDEX idx_matches_user1 ON matches(user1_id);
CREATE INDEX idx_matches_user2 ON matches(user2_id);
```

---

### Chat Service

**Таблица `messages`:**
```sql
CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID REFERENCES matches(match_id),
    from_user_id UUID REFERENCES users(user_id),
    content TEXT NOT NULL CHECK (length(content) <= 2000),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ
);
CREATE INDEX idx_messages_match ON messages(match_id, created_at DESC);
CREATE INDEX idx_messages_unread ON messages(match_id, read_at) WHERE read_at IS NULL;
```

---

## RabbitMQ конфигурация

**Exchanges:**
```
Name: dating_events
Type: topic
Durable: true
```

**Queues:**
| Queue | Routing Key | Consumer |
|-------|-------------|----------|
| `ranking.events` | `user.liked`, `user.passed` | Ranking Service (Celery) |
| `ranking.matches` | `match.created` | Ranking Service (Celery) |
| `notifications` | `message.sent` | Bot Service |

**Формат сообщения:**
```json
{
  "event_type": "user.liked",
  "timestamp": "2026-03-16T10:30:00Z",
  "payload": {
    "from_user_id": "uuid-1",
    "to_user_id": "uuid-2"
  }
}
```

---

## Celery конфигурация

**Задачи:**
| Задача | Расписание | Описание |
|--------|------------|----------|
| `recalculate_user_ratings` | Раз в час | Пересчёт primary, behavior, combined scores |
| `cleanup_expired_sessions` | Раз в сутки | Очистка старых FSM сессий в Redis |
| `aggregate_daily_metrics` | Раз в сутки | Агрегация метрик за день |

**Конфигурация:**
```python
CELERY_CONFIG = {
    'broker_url': 'amqp://guest:guest@rabbitmq:5672//',
    'result_backend': 'redis://redis:6379/1',
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json'],
    'timezone': 'UTC',
    'enable_utc': True,
    'task_track_started': True,
    'task_time_limit': 300,  # 5 минут максимум на задачу
    'worker_prefetch_multiplier': 1,
}
```

---

## Масштабирование

| Компонент | Стратегия | Примечание |
|-----------|-----------|------------|
| **Bot Service** | Горизонтальное (N инстансов) | FSM в Redis, webhook через load balancer |
| **Сервисы** | Горизонтальное (контейнеры) | Stateless, общение через HTTP/gRPC |
| **PostgreSQL** | Репликация (1 мастер, N реплик) | Реплики для чтения (Ranking, Profile) |
| **Redis** | Кластер (3 мастера, 3 реплики) | Шардирование по ключам |
| **RabbitMQ** | Кластер (3 узла) | Queue mirroring для отказоустойчивости |
| **Celery** | Горизонтальное (N воркеров) | Автокейлинг по длине очереди |
| **S3** | Автоматическое | Объектное хранилище масштабируется само |

---

## Безопасность

| Аспект | Реализация |
|--------|------------|
| **Аутентификация** | Telegram ID (верифицируется Telegram API) |
| **Авторизация** | Проверка владения профилем/мэтчем |
| **Валидация** | Возраст ≥18, bio ≤500, сообщение ≤2000 |
| **Rate Limiting** | 60 запросов/мин на пользователя (Redis) |
| **Шифрование** | HTTPS для webhook, TLS для БД |
| **Изоляция** | Контейнеризация (Docker) |

---

## Мониторинг и логирование

| Компонент | Инструмент | Назначение |
|-----------|------------|------------|
| **Логи** | Structured logging (JSON) | Консоли → Loki/ELK |
| **Метрики** | Prometheus | Счётчики запросов, ошибок, latency |
| **Трейсинг** | OpenTelemetry | Распределённая трассировка |
| **Дашборды** | Grafana | Визуализация метрик |
| **Алерты** | Alertmanager | Уведомления при ошибках |

**Ключевые метрики:**
- `bot_webhook_requests_total` — всего webhook запросов
- `bot_fsm_transitions_total` — переходов FSM
- `service_requests_duration_seconds` — latency сервисов
- `ranking_cache_hit_ratio` — попаданий в Redis кэш
- `interaction_matches_total` — всего мэтчей
- `celery_tasks_status` — статус задач Celery
