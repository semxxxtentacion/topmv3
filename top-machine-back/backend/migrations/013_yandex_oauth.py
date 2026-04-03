async def up(conn):
    await conn.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS yandex_id VARCHAR(50) UNIQUE,
            ADD COLUMN IF NOT EXISTS first_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS last_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS gender VARCHAR(10),
            ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);
    """)


async def down(conn):
    await conn.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS yandex_id,
            DROP COLUMN IF EXISTS first_name,
            DROP COLUMN IF EXISTS last_name,
            DROP COLUMN IF EXISTS gender,
            DROP COLUMN IF EXISTS avatar_url;
    """)
