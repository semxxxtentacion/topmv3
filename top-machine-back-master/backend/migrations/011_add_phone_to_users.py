async def up(conn):
    await conn.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS phone VARCHAR(50);
    """)
