async def up(conn):
	await conn.execute("""ALTER TABLE keywords_applications ADD COLUMN group_id INTEGER DEFAULT NULL""")