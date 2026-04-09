async def up(conn):
    # 1. Добавляем поля для email авторизации в users
    await conn.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE,
            ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
            ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
    """)

    # 2. Делаем telegram_id nullable (для пользователей без телеграма)
    await conn.execute("""
        ALTER TABLE users
            ALTER COLUMN telegram_id DROP NOT NULL;
    """)

    # 3. Добавляем user_id в applications (ссылка на users.id)
    await conn.execute("""
        ALTER TABLE applications
            ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);
    """)

    # 4. Заполняем user_id из существующих данных
    await conn.execute("""
        UPDATE applications a
        SET user_id = u.id
        FROM users u
        WHERE a.telegram_id = u.telegram_id
          AND a.user_id IS NULL;
    """)

    # 5. Добавляем user_id в payments
    await conn.execute("""
        ALTER TABLE payments
            ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);
    """)

    # 6. Заполняем user_id из существующих данных
    await conn.execute("""
        UPDATE payments p
        SET user_id = u.id
        FROM users u
        WHERE p.telegram_id = u.telegram_id
          AND p.user_id IS NULL;
    """)

    # 7. Создаём таблицу verification_tokens
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL REFERENCES users(id),
            token VARCHAR(255) UNIQUE NOT NULL,
            type VARCHAR(50) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
