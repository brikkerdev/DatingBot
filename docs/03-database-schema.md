# Схема базы данных

9 таблиц в PostgreSQL 16. DDL: [`03-database-schema.sql`](03-database-schema.sql).

## ER-диаграмма

```mermaid
erDiagram
    users ||--o| profiles : has
    users ||--o{ likes : "from/to"
    users ||--o{ passes : "from/to"
    users ||--o{ matches : "user1/user2"
    users ||--o| user_ratings : has
    users ||--o{ referrals : "referrer/referred"
    profiles ||--o{ profile_photos : has
    matches ||--o{ messages : contains

    users {
        bigint id PK
        bigint telegram_id UK
        timestamptz created_at
        timestamptz last_active_at
        boolean is_active
    }

    profiles {
        bigint id PK
        bigint user_id FK_UK
        varchar_100 name
        date birth_date
        varchar_20 gender
        varchar_100 city
        text bio
        jsonb interests
        int age_min_pref
        int age_max_pref
        varchar_20 preferred_gender
        varchar_100 preferred_city
        timestamptz created_at
        timestamptz updated_at
    }

    profile_photos {
        bigint id PK
        bigint profile_id FK
        varchar_512 storage_path
        int sort_order
        timestamptz created_at
    }

    likes {
        bigint from_user_id PK_FK
        bigint to_user_id PK_FK
        timestamptz created_at
    }

    passes {
        bigint from_user_id PK_FK
        bigint to_user_id PK_FK
        timestamptz created_at
    }

    matches {
        bigint id PK
        bigint user1_id FK
        bigint user2_id FK
        timestamptz created_at
    }

    messages {
        bigint id PK
        bigint match_id FK
        bigint from_user_id FK
        text content
        timestamptz created_at
    }

    user_ratings {
        bigint user_id PK_FK
        numeric_10_4 primary_score
        numeric_10_4 behavior_score
        numeric_10_4 combined_score
        timestamptz updated_at
    }

    referrals {
        bigint id PK
        bigint referrer_id FK
        bigint referred_id FK_UK
        timestamptz created_at
    }
```

## Описание таблиц

| Таблица | Назначение | Ключевые constraints |
|---------|-----------|---------------------|
| **users** | Пользователи; ключ входа — `telegram_id` | `telegram_id UNIQUE` |
| **profiles** | Анкета: имя, возраст, пол, город, описание, интересы, предпочтения | `user_id UNIQUE`, CASCADE от users |
| **profile_photos** | Фото; `storage_path` — ключ в Minio или Telegram file_id | CASCADE от profiles |
| **likes** | Лайки (from → to) | Composite PK, `CHECK from != to` |
| **passes** | Пропуски (from → to) | Composite PK, `CHECK from != to` |
| **matches** | Взаимные лайки | `UNIQUE(user1, user2)`, `CHECK user1 < user2` |
| **messages** | Сообщения в чате мэтча | CASCADE от matches |
| **user_ratings** | Рейтинги: первичный, поведенческий, комбинированный | PK = user_id |
| **referrals** | Реферальная система | `referred_id UNIQUE`, `CHECK referrer != referred` |

## Индексы

| Таблица | Индекс | Назначение |
|---------|--------|-----------|
| users | `telegram_id` (UNIQUE) | Поиск при `/start` |
| users | `last_active_at` | Поведенческий рейтинг (активность) |
| profiles | `user_id` (UNIQUE) | Один профиль на юзера |
| profiles | `gender`, `city`, `birth_date` | Фильтрация при подборе |
| profile_photos | `profile_id` | Загрузка фото профиля |
| likes | `to_user_id` | Подсчёт полученных лайков |
| likes | `created_at` | Временные выборки |
| passes | `to_user_id` | Подсчёт пропусков |
| matches | `user1_id`, `user2_id` | Поиск мэтчей пользователя |
| messages | `(match_id, created_at)` | История чата |
| referrals | `referrer_id` | Подсчёт рефералов |

## Триггеры

| Триггер | Таблица | Описание |
|---------|---------|---------|
| `profiles_updated_at` | profiles | Автоматическое обновление `updated_at` при UPDATE |
