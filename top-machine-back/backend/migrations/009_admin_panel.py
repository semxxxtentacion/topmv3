async def up(conn):
    # 1. Enum для ролей админов
    await conn.execute("""
        DO $$ BEGIN
            CREATE TYPE admin_role AS ENUM ('superadmin', 'admin', 'manager');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 2. Таблица админ-пользователей
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id             SERIAL PRIMARY KEY,
            email          VARCHAR(255) UNIQUE NOT NULL,
            password_hash  VARCHAR(255) NOT NULL,
            name           VARCHAR(255) NOT NULL,
            role           admin_role NOT NULL DEFAULT 'manager',
            is_active      BOOLEAN DEFAULT TRUE,
            created_at     TIMESTAMP DEFAULT NOW()
        );
    """)

    # 3. Таблица приглашений
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_invites (
            id             SERIAL PRIMARY KEY,
            email          VARCHAR(255) NOT NULL,
            role           admin_role NOT NULL,
            token          VARCHAR(255) UNIQUE NOT NULL,
            invited_by     INT REFERENCES admin_users(id),
            expires_at     TIMESTAMP NOT NULL,
            used           BOOLEAN DEFAULT FALSE,
            created_at     TIMESTAMP DEFAULT NOW()
        );
    """)

    # 4. Привязка менеджера к заявке
    await conn.execute("""
        ALTER TABLE applications
            ADD COLUMN IF NOT EXISTS manager_id INT REFERENCES admin_users(id);
    """)

    # 5. Доп. поля клиента для идентификации
    await conn.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS phone VARCHAR(50),
            ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(255);
    """)
