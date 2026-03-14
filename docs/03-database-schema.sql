-- Dating Bot: схема БД (PostgreSQL)
-- Этап 1: Планирование и проектирование

-- Расширение для генерации ID (опционально)
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------
-- Пользователи (регистрация по Telegram)
-- -----------------------------------------------
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_users_telegram_id ON users (telegram_id);
CREATE INDEX idx_users_last_active ON users (last_active_at);

-- -----------------------------------------------
-- Анкеты
-- -----------------------------------------------
CREATE TABLE profiles (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    name                VARCHAR(100) NOT NULL,
    birth_date          DATE NOT NULL,
    gender              VARCHAR(20) NOT NULL,
    city                VARCHAR(100),
    bio                 TEXT,
    interests           JSONB DEFAULT '[]',
    -- предпочтения для подбора
    age_min_pref        INT,
    age_max_pref        INT,
    preferred_gender    VARCHAR(20),
    preferred_city      VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_user_id ON profiles (user_id);
CREATE INDEX idx_profiles_gender ON profiles (gender);
CREATE INDEX idx_profiles_city ON profiles (city);
CREATE INDEX idx_profiles_birth_date ON profiles (birth_date);

-- -----------------------------------------------
-- Фотографии анкеты (путь в S3/Minio)
-- -----------------------------------------------
CREATE TABLE profile_photos (
    id           BIGSERIAL PRIMARY KEY,
    profile_id   BIGINT NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    storage_path VARCHAR(512) NOT NULL,
    sort_order   INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profile_photos_profile_id ON profile_photos (profile_id);

-- -----------------------------------------------
-- Лайки
-- -----------------------------------------------
CREATE TABLE likes (
    from_user_id  BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    to_user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (from_user_id, to_user_id),
    CHECK (from_user_id != to_user_id)
);

CREATE INDEX idx_likes_to_user ON likes (to_user_id);
CREATE INDEX idx_likes_created ON likes (created_at);

-- -----------------------------------------------
-- Пропуски (для поведенческого рейтинга)
-- -----------------------------------------------
CREATE TABLE passes (
    from_user_id  BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    to_user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (from_user_id, to_user_id),
    CHECK (from_user_id != to_user_id)
);

CREATE INDEX idx_passes_to_user ON passes (to_user_id);

-- -----------------------------------------------
-- Мэтчи (взаимный лайк)
-- -----------------------------------------------
CREATE TABLE matches (
    id         BIGSERIAL PRIMARY KEY,
    user1_id   BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    user2_id   BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user1_id, user2_id),
    CHECK (user1_id < user2_id)
);

CREATE INDEX idx_matches_user1 ON matches (user1_id);
CREATE INDEX idx_matches_user2 ON matches (user2_id);

-- -----------------------------------------------
-- Сообщения в чате мэтча
-- -----------------------------------------------
CREATE TABLE messages (
    id           BIGSERIAL PRIMARY KEY,
    match_id     BIGINT NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    from_user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_match_created ON messages (match_id, created_at);

-- -----------------------------------------------
-- Рейтинги (для ранжирования, пересчёт через Celery)
-- -----------------------------------------------
CREATE TABLE user_ratings (
    user_id         BIGINT NOT NULL PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    primary_score   NUMERIC(10, 4) NOT NULL DEFAULT 0,
    behavior_score  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    combined_score  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------
-- Триггер: обновление updated_at у profiles
-- -----------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE PROCEDURE set_updated_at();
