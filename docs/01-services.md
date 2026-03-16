## Обзор системы

Dating Bot — телеграм-бот для знакомств. Пользователи заполняют анкету, просматривают других пользователей (лайк/пас), при взаимном лайке получают мэтч и возможность общения.

---

## 1. Сервис бота (Bot Service)

**Назначение:** Единственная точка входа пользователя в систему.

**Функции:**
- Интеграция с Telegram Bot API (получение обновлений, отправка сообщений)
- Обработка команд: `/start`, `/help`, навигация по меню
- Оркестрация сценариев: регистрация, заполнение анкеты, редактирование анкеты, просмотр анкет (свайпы), чат после мэтча
- Отправка уведомлений (новый мэтч, новое сообщение)
- Валидация ввода и перевод пользователя между состояниями (FSM)

**FSM (основные состояния):**
| Состояние | Триггер | Следующее |
|-----------|---------|-----------|
| `Registration` | `/start` | `ProfileCreation` |
| `ProfileCreation` | Пошаговый ввод (имя, возраст, пол, город, bio, интересы, фото) | `MainMenu` |
| `ProfileEdit` | Редактирование полей | `MainMenu` |
| `Browsing` | Просмотр анкет, лайк/пас | `Browsing` |
| `ChatSelect` | Выбор мэтча для чата | `Chatting` |
| `Chatting` | Отправка сообщения | `Chatting` |

**Вызовы к другим сервисам:**
- `UserService.get_or_create(telegram_id)` → user_id, is_new
- `ProfileService.get(user_id)`, `ProfileService.create/update(...)`, `ProfileService.upload_photo(...)`
- `RankingService.get_next(user_id, count)` → список profile_id
- `InteractionService.like(from_user, to_user)`, `InteractionService.pass(from_user, to_user)` → match_created
- `ChatService.get_matches(user_id)`, `ChatService.get_messages(match_id)`, `ChatService.send(user_id, match_id, text)`

**Входы:** Webhook от Telegram.
**Выходы:** Запросы к User, Profile, Ranking, Interaction, Chat.

**Конфигурация:** `BOT_TOKEN`, `WEBHOOK_URL`, `REDIS_URL` (FSM storage), URL сервисов.

**Технологии:** Python (aiogram 3.x), асинхронная обработка.

---

## 2. Сервис пользователей (User Service)

**Назначение:** Учёт пользователей и аутентификация.

**Функции:**
- Регистрация по Telegram ID (при первом `/start`)
- Хранение привязки Telegram ID ↔ внутренний user_id
- Базовые данные: дата регистрации, последняя активность, статус (активен/заблокирован)
- Предоставление данных пользователя другим сервисам по user_id

**API (внутренние вызовы):**
| Метод | Вход | Выход | Примечание |
|-------|------|-------|------------|
| `get_or_create(telegram_id)` | telegram_id | `{user_id, is_new}` | Идемпотентно |
| `get(user_id)` | user_id | `{user_id, telegram_id, last_active_at, is_active}` | — |
| `update_last_active(user_id)` | user_id | — | Вызывать при каждом действии |

**Обработка ошибок:** `UserNotFound` — при отсутствии user_id; `UserBlocked` — при is_active=false.

**Входы:** Запросы от Bot Service.  
**Выходы:** user_id, флаги (новый/существующий).

**Хранение:** Таблица `users`.

---

## 3. Сервис анкет (Profile Service)

**Назначение:** CRUD анкет и медиа.

**Функции:**
- Создание, чтение, обновление анкеты пользователя (имя, возраст, пол, город, описание, интересы)
- Загрузка и привязка фотографий к анкете (хранение метаданных; файлы — в S3)
- Проверка полноты анкеты (для первичного рейтинга)
- Выдача анкеты по ID для отображения в боте

**API:**
| Метод | Вход | Выход |
|-------|------|-------|
| `get(profile_id)` | profile_id | `{name, age, gender, city, bio, interests, photos[], preferences}` |
| `get_by_user(user_id)` | user_id | то же |
| `create(user_id, data)` | user_id, поля анкеты | profile_id |
| `update(profile_id, data)` | profile_id, частичные данные | — |
| `upload_photo(profile_id, file)` | profile_id, file | photo_id, storage_path |
| `is_complete(profile_id)` | profile_id | bool (имя, возраст, пол, город, ≥1 фото) |

**Формат хранения фото:** `profiles/{user_id}/{photo_id}.{ext}` в S3; в БД — `storage_path`, `sort_order`.

**Ограничения:** Минимум 1 фото, максимум 6. Валидация: возраст 18+, bio ≤ 500 символов.

**Входы:** Bot Service, Ranking Service.
**Выходы:** Объект анкеты с полями и списком photo URLs.

**Хранение:** `profiles`, `profile_photos`; S3.

---

## 4. Сервис ранжирования (Ranking Service)

**Назначение:** Выдача пользователю подходящих анкет в нужном порядке.

**Функции:**
- **Первичный рейтинг:** учёт данных анкеты (возраст, пол, интересы, город), полноты анкеты, количества фото, предпочтений по возрасту/полу/городу
- **Поведенческий рейтинг:** учёт лайков/пасов, мэтчей, инициаций диалогов, активности по времени
- **Комбинированный рейтинг:** весовая модель первичный + поведенческий + рефералы
- Формирование и обновление очереди анкет для пользователя
- Интеграция с кэшем (Redis): предзагрузка 10 анкет в кэш при старте сессии, пополнение по мере просмотра

**API:**
| Метод | Вход | Выход | Примечание |
|-------|------|-------|------------|
| `get_next(user_id, count=1)` | user_id, count | `[profile_id, ...]` | — |
| `on_like(from_user, to_user)` | event | — | Обновление поведенческого рейтинга |
| `on_pass(from_user, to_user)` | event | — | То же |
| `on_match(user1, user2)` | event | — | То же |

**Логика кэша (Redis):**
- Ключ: `ranking:queue:{user_id}` — список profile_id (очередь на показ)
- Размер очереди: 10 анкет (фиксированное значение)
- При `get_next`: если очередь пуста — пересчёт из БД (user_ratings + фильтры), загрузка 10 анкет, возврат первых count
- Исключать: уже лайкнутые, пропущенные, самого пользователя
- При достижении конца очереди — повторный цикл с новой выборкой

**Celery-задачи:** Периодический пересчёт `user_ratings` (primary_score, behavior_score, combined_score) по расписанию (раз в час).

**Входы:** user_id, события от Bot/Interaction через RabbitMQ.
**Выходы:** Список profile_id для показа.

**Хранение:** `user_ratings`, Redis.

---

## 5. Сервис взаимодействий (Interaction Service)

**Назначение:** Лайки, пасы, мэтчи.

**Функции:**
- Фиксация лайка/паса (кто → кого)
- Определение мэтча (взаимный лайк)
- Создание записи мэтча и открытие чата
- Предоставление истории действий для сервиса ранжирования и для отображения в боте

**API:**
| Метод | Вход | Выход |
|-------|------|-------|
| `like(from_user_id, to_user_id)` | user_id, user_id | `{match_created: bool}` |
| `pass(from_user_id, to_user_id)` | user_id, user_id | — |
| `get_matches(user_id)` | user_id | `[{match_id, partner_profile, last_message_at}]` |
| `has_liked(from_user, to_user)` | user_id, user_id | bool |
| `has_passed(from_user, to_user)` | user_id, user_id | bool |

**Логика мэтча:** При `like(A, B)` — проверить `likes` на наличие B→A; если есть — создать `matches` (user1_id < user2_id), вернуть `match_created=true`. Идемпотентность: повторный like — тот же результат.

**Входы:** Bot Service.  
**Выходы:** match_created, список мэтчей.

**Хранение:** `likes`, `passes`, `matches`. UNIQUE (from_user_id, to_user_id) для likes/passes.

---

## 6. Сервис чатов (Chat Service)

**Назначение:** Сообщения между пользователями после мэтча.

**Функции:**
- Отправка сообщения в рамках мэтча
- История переписки по паре пользователей
- Уведомление о новом сообщении (для Bot Service)

**API:**
| Метод | Вход | Выход |
|-------|------|-------|
| `send(match_id, from_user_id, content)` | match_id, user_id, text | message_id |
| `get_history(match_id, limit, offset)` | match_id | `[{from_user_id, content, created_at}]` |
| `get_dialogs(user_id)` | user_id | `[{match_id, partner, last_message, unread_count}]` |
| `mark_read(match_id, user_id)` | match_id, user_id | — |

**Ограничения:** Только участники мэтча могут отправлять сообщения. Проверка: `from_user_id IN (user1_id, user2_id)` для match. Лимит длины сообщения 2000 символов.

**Уведомления:** При `send` — возврат `recipient_user_id`; Bot Service отправляет push в Telegram. Событие в RabbitMQ для асинхронной доставки.

**Входы:** Bot Service.  
**Выходы:** Сохранённые сообщения, список диалогов.

**Хранение:** `matches`, `messages`. Индекс `(match_id, created_at)` для истории.

---

## Вспомогательные компоненты

| Компонент   | Назначение                                      |
|------------|--------------------------------------------------|
| **Redis**  | Кэш предранжированных анкет, сессии FSM, очереди |
| **Celery** | Отложенные задачи: пересчёт рейтингов по расписанию |
| **RabbitMQ** | Поток событий: лайки, пасы, мэтчи — для ранжирования и аналитики |
| **S3** | Хранение фотографий анкет                      |