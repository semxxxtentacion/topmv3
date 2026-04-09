async def up(conn):
    await conn.execute("""
        ALTER TABLE applications ADD COLUMN IF NOT EXISTS total_visits INTEGER;
    """)

async def down(conn):
    await conn.execute("""
        ALTER TABLE applications DROP COLUMN IF EXISTS total_visits;
    """)