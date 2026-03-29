# Dating Bot

Telegram-бот для знакомств с системой анкет, лайков, мэтчей и чата.

## Возможности

- Регистрация через Telegram (`/start`)
- Профиль: имя, возраст, пол, город, описание, до 6 фото
- Редактирование анкеты (каждое поле отдельно, управление фото с порядком)
- Удаление анкеты
- Просмотр анкет с лайками/пропусками, ранжирование по рейтингу
- Мэтчи при взаимных лайках + уведомления обоим пользователям
- Чат между мэтчами с историей сообщений
- 3-уровневая система рейтинга (первичный, поведенческий, комбинированный)
- Реферальная система (`/invite`)
- Кэширование очереди анкет в Redis (10 шт, подгрузка по мере просмотра)
- Событийная архитектура через RabbitMQ

## Технологический стек

| Технология | Назначение |
|---|---|
| **Python 3.12** + **aiogram 3** | Telegram Bot API, FSM |
| **SQLAlchemy 2** + **asyncpg** | Async ORM |
| **PostgreSQL 16** | Основная БД (9 таблиц) |
| **Redis 7** | Кэш очереди анкет + FSM storage |
| **RabbitMQ 3** | Событийная шина между сервисами |
| **Celery 5** | Периодический пересчёт рейтингов (beat каждые 10 мин) |
| **Minio** | S3-хранилище для фото |
| **Prometheus** + **Grafana** | Метрики и дашборды |
| **structlog** | Структурированное логирование |
| **Docker Compose** | Оркестрация всех 9 сервисов |

## Архитектура

```
docker-compose up -d  →  9 контейнеров:

┌─────────────────────────────────────────────────────────┐
│  Инфраструктура                                         │
│  postgres · redis · rabbitmq · minio                    │
├─────────────────────────────────────────────────────────┤
│  Приложение                                             │
│  bot · celery-worker · event-consumer                   │
├─────────────────────────────────────────────────────────┤
│  Мониторинг                                             │
│  prometheus · grafana                                   │
└─────────────────────────────────────────────────────────┘
```

Сервисы общаются через RabbitMQ (exchange `dating_events`, topic routing). Подробнее в [архитектуре](docs/02-architecture.md).

## Быстрый старт

```bash
# 1. Настроить токен
cp .env.example .env
# Вставить BOT_TOKEN от @BotFather

# 2. Запустить всё
docker-compose up -d

# 3. Готово — бот работает
```

## Документация

| Документ | Описание |
|----------|----------|
| [Сервисы](docs/01-services.md) | Bot, User, Profile, Ranking, Interaction, Chat, Events |
| [Архитектура](docs/02-architecture.md) | Потоки данных, события, обоснование MQ |
| [Схема БД](docs/03-database-schema.md) | 9 таблиц, ER-диаграмма |
| [DDL](docs/03-database-schema.sql) | SQL для создания таблиц |

## Мониторинг

| UI | URL | Логин |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9091 | — |
| RabbitMQ | http://localhost:15672 | guest / guest |
| Minio | http://localhost:9001 | minioadmin / minioadmin |

## Разработка (без Docker)

```bash
docker-compose up -d postgres redis rabbitmq minio   # только инфра
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m src.bot                                     # бот
celery -A src.worker.celery_app worker --beat -l info  # celery
python -m src.worker.consumer                          # event consumer
```

## Тестирование

```bash
pytest tests/ -v                                            # unit-тесты
locust -f tests/load/locustfile.py --headless -u 50 -t 60s  # нагрузка
```
