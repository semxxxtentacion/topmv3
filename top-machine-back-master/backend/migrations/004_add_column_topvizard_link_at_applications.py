async def up(conn):
	await conn.execute("""
		ALTER TABLE applications ADD COLUMN topvizard_link VARCHAR(50) DEFAULT NULL
	""")