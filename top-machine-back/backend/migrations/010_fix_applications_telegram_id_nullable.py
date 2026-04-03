async def up(conn):
    await conn.execute("""
        ALTER TABLE applications
            ALTER COLUMN telegram_id DROP NOT NULL;
    """)
