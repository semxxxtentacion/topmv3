-- ============================================================
-- acc-generator: PostgreSQL schema
-- ============================================================

-- Статусы профилей
DO $$ BEGIN
    CREATE TYPE profile_status AS ENUM ('new', 'warm', 'partial', 'dead');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Источник отпечатков
DO $$ BEGIN
    CREATE TYPE fingerprint_source AS ENUM ('builtin', 'external');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- -----------------------------------------------------------
-- Основная таблица профилей
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
    id              UUID PRIMARY KEY,
    party           fingerprint_source NOT NULL DEFAULT 'builtin',

    -- Устройство
    device_model    TEXT NOT NULL,
    device_name     TEXT NOT NULL,
    device_chipset  TEXT,
    platform        TEXT NOT NULL DEFAULT 'Android',
    platform_version TEXT NOT NULL,
    browser         TEXT NOT NULL DEFAULT 'Chrome',
    browser_version TEXT NOT NULL,

    -- Отпечатки (полный JSON: navigator, screen, webgl, audio, canvas, etc.)
    fingerprints    JSONB NOT NULL,

    -- Viewport
    viewport        JSONB NOT NULL,

    -- Поведение мыши / тач
    mouse_config    JSONB NOT NULL,

    -- Геолокация
    geo             JSONB NOT NULL,

    -- Прокси, через который фармился
    proxy_used      TEXT,

    -- Состояние
    status          profile_status NOT NULL DEFAULT 'new',
    cookies_count   INTEGER NOT NULL DEFAULT 0,
    is_captcha      BOOLEAN NOT NULL DEFAULT FALSE,

    -- Счётчики прогрева
    warmup_count    INTEGER NOT NULL DEFAULT 0,
    last_warmup_at  TIMESTAMPTZ,

    -- Временные метки
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для типичных запросов
CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles (status);
CREATE INDEX IF NOT EXISTS idx_profiles_created ON profiles (created_at);
CREATE INDEX IF NOT EXISTS idx_profiles_last_warmup ON profiles (last_warmup_at);
CREATE INDEX IF NOT EXISTS idx_profiles_party ON profiles (party);

-- -----------------------------------------------------------
-- Куки и localStorage профиля
-- Отдельная таблица — при прогреве куки обновляются,
-- а старые версии можно хранить как историю
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_cookies (
    id              BIGSERIAL PRIMARY KEY,
    profile_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    cookies         JSONB NOT NULL DEFAULT '[]',
    localstorage    JSONB NOT NULL DEFAULT '{}',

    -- Откуда эти куки: initial (первый фарм) или warmup (прогрев)
    source          TEXT NOT NULL DEFAULT 'initial',

    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cookies_profile ON profile_cookies (profile_id);
CREATE INDEX IF NOT EXISTS idx_cookies_collected ON profile_cookies (collected_at);

-- -----------------------------------------------------------
-- История прогревов
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS warmup_history (
    id              BIGSERIAL PRIMARY KEY,
    profile_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    -- Тип прогрева: light (1-2 сайта) или deep (3-5+ сайтов)
    warmup_type     TEXT NOT NULL DEFAULT 'light',

    -- Какие сайты посещались
    sites_visited   JSONB NOT NULL DEFAULT '[]',

    -- Метрики
    cookies_before  INTEGER NOT NULL DEFAULT 0,
    cookies_after   INTEGER NOT NULL DEFAULT 0,
    captcha_hit     BOOLEAN NOT NULL DEFAULT FALSE,
    duration_sec    INTEGER,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_warmup_profile ON warmup_history (profile_id);
CREATE INDEX IF NOT EXISTS idx_warmup_created ON warmup_history (created_at);

-- -----------------------------------------------------------
-- Вьюха: актуальные куки профиля (последняя запись)
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW profile_latest_cookies AS
SELECT DISTINCT ON (profile_id)
    profile_id,
    cookies,
    localstorage,
    source,
    collected_at
FROM profile_cookies
ORDER BY profile_id, collected_at DESC;

-- -----------------------------------------------------------
-- Вьюха: профили, требующие прогрева
-- (не прогревались > 2 дней, статус не dead)
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW profiles_needing_warmup AS
SELECT
    p.id,
    p.device_name,
    p.status,
    p.warmup_count,
    p.last_warmup_at,
    p.cookies_count,
    NOW() - COALESCE(p.last_warmup_at, p.created_at) AS time_since_warmup
FROM profiles p
WHERE p.status != 'dead'
  AND (
    p.last_warmup_at IS NULL
    OR p.last_warmup_at < NOW() - INTERVAL '2 days'
  )
ORDER BY COALESCE(p.last_warmup_at, p.created_at) ASC;
