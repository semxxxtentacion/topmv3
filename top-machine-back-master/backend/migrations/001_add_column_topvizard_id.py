async def up(conn):
    await conn.execute('''ALTER TABLE applications ADD COLUMN topvizard_id VARCHAR(20) DEFAULT NULL''')