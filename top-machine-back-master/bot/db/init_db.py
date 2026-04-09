import logging

from bot.db.connection import get_pool

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TYPE IF NOT EXISTS application_status AS ENUM ('accepted', 'rejected');

CREATE SEQUENCE IF NOT EXISTS app_number_seq START 1;

CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    telegram_id          BIGINT UNIQUE NOT NULL,
    name                 VARCHAR(255),
    username             VARCHAR(255),
    code                 VARCHAR(20),
    applications_balance INT DEFAULT 0,
    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS applications (
    id                  SERIAL PRIMARY KEY,
    telegram_id         BIGINT NOT NULL REFERENCES users(telegram_id),
    site                VARCHAR(255) NOT NULL,
    region              VARCHAR(255),
    audit               BOOLEAN DEFAULT FALSE,
    keywords_selection  BOOLEAN DEFAULT FALSE,
    google              BOOLEAN DEFAULT FALSE,
    yandex              BOOLEAN DEFAULT FALSE,
    keywords            TEXT,
    status              application_status DEFAULT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);
"""


async def init_db() -> None:
    """Создать таблицы и типы если их нет. Вызывается при старте бота."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # CREATE TYPE IF NOT EXISTS не поддерживается напрямую в PostgreSQL
        # поэтому создаём тип через DO блок
        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE application_status AS ENUM ('accepted', 'rejected');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """)

        await conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS app_number_seq START 1;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                   SERIAL PRIMARY KEY,
                telegram_id          BIGINT UNIQUE NOT NULL,
                name                 VARCHAR(255),
                username             VARCHAR(255),
                code                 VARCHAR(20),
                applications_balance INT DEFAULT 0,
                created_at           TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id                  SERIAL PRIMARY KEY,
                telegram_id         BIGINT NOT NULL REFERENCES users(telegram_id),
                site                VARCHAR(255) NOT NULL,
                region              VARCHAR(255),
                audit               BOOLEAN DEFAULT FALSE,
                keywords_selection  BOOLEAN DEFAULT FALSE,
                google              BOOLEAN DEFAULT FALSE,
                yandex              BOOLEAN DEFAULT FALSE,
                keywords            TEXT,
                status              application_status DEFAULT NULL,
                created_at          TIMESTAMP DEFAULT NOW()
            );
        """)

    logger.info("✅ БД инициализирована")
