# Dating Bot

Телеграм-бот для знакомств: анкеты, лайки/пасы, мэтчи и чат.

## Возможности

- Регистрация через Telegram
- Анкета: имя, возраст, пол, город, описание, интересы, фото
- Просмотр анкет с лайком/пасом
- Мэтч при взаимном лайке и чат
- Ранжирование анкет (первичный, поведенческий и комбинированный рейтинг)

## Документация

| Документ | Описание |
|----------|----------|
| [Сервисы](docs/01-services.md) | Bot, User, Profile, Ranking, Interaction, Chat |
| [Архитектура](docs/02-architecture.md) | Схема системы, потоки данных, сценарии |
| [Схема БД](docs/03-database-schema.md) | Таблицы и связи |
| [DDL (PostgreSQL)](docs/03-database-schema.sql) | SQL для создания таблиц |

## Стек

- Python, Telegram Bot API (aiogram / python-telegram-bot)
- PostgreSQL
- Redis (кэш анкет)
- S3/Minio (фото)
- Celery, очереди сообщений (опционально)

## Настройка БД

Создание таблиц в PostgreSQL:

```bash
psql -U user -d dating_bot -f docs/03-database-schema.sql
```

## Лицензия

[LICENSE](LICENSE)
