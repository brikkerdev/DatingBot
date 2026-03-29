# Описание сервисов

## Обзор

Dating Bot — Telegram-бот для знакомств. Пользователи заполняют анкету, просматривают других (лайк/пас), при взаимном лайке получают мэтч и чат.

Система состоит из 6 сервисов + шины событий:

```
Bot Service ──→ User / Profile / Interaction / Chat (прямые вызовы)
                    │
                    ▼ publish events
              RabbitMQ (dating_events)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Ranking Service      Notification Service
  (пересчёт рейтингов)  (уведомления о мэтчах)
```

---

## 1. Bot Service (`src/bot/`)

**Назначение:** Точка входа пользователя — Telegram Bot API.

**Реализация:** aiogram 3.x, polling mode (опционально webhook).

**Хэндлеры:**
| Файл | Функциональность |
|------|-----------------|
| `start.py` | `/start` — регистрация, обработка реферальных ссылок (`/start ref_<id>`) |
| `registration.py` | FSM: имя → возраст → пол → город → описание → фото → подтверждение |
| `browse.py` | «Смотреть анкеты» — показ из Redis-кэша, лайк/пас через inline-кнопки |
| `matches.py` | «Мэтчи» — список мэтчей с кнопками входа в чат |
| `chat.py` | Чат — FSM `ChatState.in_chat`, история сообщений, прямая пересылка партнёру |
| `menu.py` | «Моя анкета» — превью + действия (редактировать/удалить) |
| `edit_profile.py` | Редактирование полей анкеты, управление фото (добавить/удалить/порядок) |

**FSM-состояния:**
```
RegistrationState: waiting_for_name → age → gender → city → bio → photo → confirm
EditProfileState:  choosing_field → editing_name/age/gender/city/bio/photo
ChatState:         in_chat (match_id, partner_telegram_id, partner_name)
```

**Middlewares:**
- `DbSessionMiddleware` — инъекция AsyncSession + обновление `last_active_at`
- `RedisMiddleware` — инъекция Redis-клиента
- `MetricsMiddleware` — замер времени обработки (Prometheus histogram)

**Клавиатуры:**
- Reply: главное меню, подтверждение, выбор пола, действия с профилем
- Inline: лайк/пас (`like:{user_id}`, `pass:{user_id}`), список мэтчей, редактирование полей, управление фото

---

## 2. User Service (`src/services/user.py`)

**Назначение:** Регистрация и идентификация пользователей.

**Функции:**
- `get_or_create_user(telegram_id)` → `(User, is_new)` — идемпотентно, обработка race condition через `IntegrityError`
- `get_user_by_telegram_id(telegram_id)` → `User | None`

**Хранение:** Таблица `users` (id, telegram_id, created_at, last_active_at, is_active).

---

## 3. Profile Service (`src/services/profile.py`)

**Назначение:** CRUD анкет и управление фото.

**Функции:**
| Метод | Описание |
|-------|---------|
| `get_profile_by_user_id(user_id)` | Загрузка профиля с фото (selectinload) |
| `create_profile(...)` | Создание при регистрации |
| `update_profile(profile, **fields)` | Обновление полей + событие `profile.updated` + инвалидация кэша |
| `add_photo(profile_id, storage_path, sort_order)` | Добавление фото |
| `delete_photo(photo_id)` | Удаление одного фото |
| `swap_photo_order(photo_id_a, photo_id_b)` | Смена порядка |
| `delete_profile(profile_id, user_id)` | Удаление анкеты + событие `profile.deleted` + инвалидация кэша |

**Кэш-инвалидация:** При изменении профиля — прямой вызов `redis.delete("profile_queue:*")`. MQ не используется (дешёвая операция).

**Хранение:** `profiles`, `profile_photos`, Minio (S3).

---

## 4. Ranking Service (`src/services/ranking.py` + `src/worker/consumer.py`)

**Назначение:** 3-уровневая система рейтинга для ранжирования анкет.

### Уровень 1: Первичный рейтинг (0–100)
| Критерий | Баллы |
|---------|-------|
| Имя, дата рождения, пол | 5 + 5 + 5 |
| Город | 10 |
| Описание (bio) | 15 |
| Интересы (до 5) | 3 × шт |
| Фото (1 базовое + доп.) | 10 + 2.5 × шт |
| Предпочтения (возраст, пол, город) | 5 + 5 + 5 |

### Уровень 2: Поведенческий рейтинг (0–100)
| Критерий | Баллы (макс) |
|---------|-------------|
| Полученные лайки | 30 (×2 за лайк) |
| Соотношение лайков/пасов | 20 |
| Частота мэтчей | 20 (×5 за мэтч) |
| Инициирование диалогов (первое сообщение в мэтче) | 15 (×5 за диалог) |
| Активность (24ч/7д/30д) | 15 / 10 / 5 |

### Уровень 3: Комбинированный рейтинг
```
combined = 0.4 × primary + 0.5 × behavioral + 0.1 × referral_bonus
referral_bonus = min(count_referrals × 20, 100)
```

**Пересчёт:**
- Через MQ (event consumer) при каждом лайке/пасе/мэтче/сообщении/реферале — фоновый пересчёт (8+ SQL-запросов, тяжёлая операция)
- Через Celery beat каждые 10 минут — полный пересчёт всех пользователей

**Redis-кэш:** Очередь анкет `profile_queue:{user_id}`, 10 шт, TTL 600 сек. Заполняется из БД при первом просмотре, обновляется при исчерпании.

**Хранение:** `user_ratings`.

---

## 5. Interaction Service (`src/services/interaction.py`)

**Назначение:** Лайки, пасы, определение мэтчей.

**Функции:**
- `record_like(from_user_id, to_user_id)` → `Match | None` — записывает лайк, проверяет взаимность, создаёт мэтч. Публикует `like.created` и `match.created`.
- `record_pass(from_user_id, to_user_id)` — записывает пас. Публикует `pass.created`.
- `get_next_profiles(user_id, limit)` — исключает уже просмотренных, сортирует по `combined_score DESC`.
- `get_user_matches(user_id)` — список мэтчей.

**Консистентность:** `user1_id < user2_id` в matches, composite PK в likes/passes, `CHECK from != to`.

**Хранение:** `likes`, `passes`, `matches`.

---

## 6. Chat Service (`src/services/chat.py`)

**Назначение:** Обмен сообщениями между мэтчами.

**Функции:**
- `send_message(match_id, from_user_id, content)` — сохраняет в БД, публикует `message.created` для пересчёта рейтинга
- `get_messages(match_id, limit=50)` — история в хронологическом порядке
- `get_match_by_id(match_id)`, `is_user_in_match(match, user_id)` — проверки доступа

**Пересылка сообщений:** Напрямую через Bot API (мгновенно), не через MQ — чат должен быть быстрым.

**Хранение:** `messages`. Индекс `(match_id, created_at)`.

---

## 7. Event Service (`src/services/events.py`)

**Назначение:** Единая точка публикации событий в RabbitMQ.

**Функция:** `publish(event_type, payload)` — fire-and-forget через Celery task → RabbitMQ exchange `dating_events`.

**Типы событий:**
| Событие | Payload | Публикуется из |
|---------|---------|---------------|
| `like.created` | `{from_user_id, to_user_id}` | Interaction Service |
| `pass.created` | `{from_user_id, to_user_id}` | Interaction Service |
| `match.created` | `{match_id, user1_id, user2_id}` | Interaction Service |
| `message.created` | `{match_id, from_user_id}` | Chat Service |
| `profile.updated` | `{user_id}` | Profile Service |
| `profile.deleted` | `{user_id}` | Profile Service |
| `referral.created` | `{referrer_id, referred_id}` | Referral Service |

---

## 8. Referral Service (`src/services/referral.py`)

**Назначение:** Реферальная система.

**Функции:**
- `create_referral(referrer_id, referred_id)` — записывает реферала, публикует `referral.created`
- `get_referral_count(user_id)` — количество приглашённых

**Команда:** `/invite` — генерирует ссылку `https://t.me/bot?start=ref_<telegram_id>`.

**Бонус:** +20 к referral_bonus за каждого приглашённого (макс 100).

---

## Вспомогательные компоненты

| Компонент | Назначение |
|-----------|-----------|
| **Redis** | Кэш очереди анкет (10 шт/юзер, TTL 10 мин) + FSM storage (aiogram) |
| **Celery** | Периодический пересчёт рейтингов (beat 10 мин) + публикация событий в MQ |
| **RabbitMQ** | Шина событий: ranking_service (7 событий) + notification_service (1 событие) |
| **Minio (S3)** | Хранение фото (bucket `photos`, fallback на Telegram file_id) |
| **Prometheus** | Метрики: handler_duration, likes/passes/matches/messages, queue hits/misses |
| **Grafana** | Provisioned дашборд: rates, latency p50/p95, queue hit rate |
| **structlog** | Структурированное логирование |
