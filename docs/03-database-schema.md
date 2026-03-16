## ER-диаграмма (Mermaid)

```mermaid
erDiagram
    users ||--o| profiles : has
    users ||--o{ likes_from : "likes"
    users ||--o{ likes_to : "liked by"
    users ||--o{ passes_from : "passes"
    users ||--o{ passes_to : "passed by"
    users ||--o{ match_user1 : "match"
    users ||--o{ match_user2 : "match"
    profiles ||--o{ profile_photos : has
    matches ||--o{ messages : contains

    users {
        bigint id PK
        bigint telegram_id UK
        timestamp created_at
        timestamp last_active_at
        boolean is_active
    }

    profiles {
        bigint id PK
        bigint user_id FK,UK
        varchar name
        date birth_date
        varchar gender
        varchar city
        text bio
        jsonb interests
        int age_min_pref
        int age_max_pref
        varchar preferred_gender
        varchar preferred_city
        timestamp created_at
        timestamp updated_at
    }

    profile_photos {
        bigint id PK
        bigint profile_id FK
        varchar storage_path
        int sort_order
        timestamp created_at
    }

    likes {
        bigint from_user_id FK
        bigint to_user_id FK
        timestamp created_at
        PK from_user_id to_user_id
    }

    passes {
        bigint from_user_id FK
        bigint to_user_id FK
        timestamp created_at
        PK from_user_id to_user_id
    }

    matches {
        bigint id PK
        bigint user1_id FK
        bigint user2_id FK
        timestamp created_at
        UK user1_id user2_id
    }

    messages {
        bigint id PK
        bigint match_id FK
        bigint from_user_id FK
        text content
        timestamp created_at
    }

    user_ratings {
        bigint user_id PK,FK
        decimal primary_score
        decimal behavior_score
        decimal combined_score
        timestamp updated_at
    }
```

## Описание таблиц

| Таблица | Назначение |
|--------|------------|
| **users** | Пользователи системы; ключ входа — `telegram_id`. |
| **profiles** | Анкета: имя, возраст (из birth_date), пол, город, описание, интересы, предпочтения по возрасту/полу/городу. |
| **profile_photos** | Фото анкеты; `storage_path` — ключ в S3/Minio. |
| **likes** | Кто кого лайкнул (from → to). |
| **passes** | Кто кого пропустил (для поведенческого рейтинга). |
| **matches** | Пара пользователей при взаимном лайке. |
| **messages** | Сообщения в рамках мэтча. |
| **user_ratings** | Рейтинги для ранжирования: первичный, поведенческий, комбинированный. |

## Индексы (основные)

- `users.telegram_id` — UNIQUE, поиск при /start.
- `profiles.user_id` — UNIQUE (один профиль на пользователя).
- `likes (from_user_id, to_user_id)` — UNIQUE, проверка мэтча.
- `passes (from_user_id, to_user_id)` — UNIQUE.
- `matches (user1_id, user2_id)` — UNIQUE; порядок user1 < user2 для консистентности.
- `messages (match_id, created_at)` — выборка истории чата.
- `user_ratings` — пересчёт по расписанию (Celery).

Файл `03-database-schema.sql` содержит DDL для создания таблиц в PostgreSQL.
