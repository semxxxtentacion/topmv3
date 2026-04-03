-- Тип для статуса заявки
CREATE TYPE application_status AS ENUM ('accepted', 'rejected');

-- Sequence для номеров заявок

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    telegram_id          BIGINT UNIQUE NOT NULL,
    name                 VARCHAR(255),
    username             VARCHAR(255),
    code                 VARCHAR(20),
    applications_balance INT DEFAULT 0,
    created_at           TIMESTAMP DEFAULT NOW()
);

-- Заявки
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
