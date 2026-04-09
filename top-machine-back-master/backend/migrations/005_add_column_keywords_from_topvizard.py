async def up(conn):
	await conn.execute('''
		CREATE TABLE IF NOT EXISTS keywords_applications (
			id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			keyword_id  INTEGER,
			name        TEXT NOT NULL,
			project_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
			created_at  TIMESTAMP DEFAULT NOW()
		)
	''')
