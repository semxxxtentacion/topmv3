async def up(conn):
	await conn.execute("""
		ALTER TABLE applications ADD COLUMN region_id INTEGER DEFAULT NULL
	""")