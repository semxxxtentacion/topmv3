async def up(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS project_proxies (
            id SERIAL PRIMARY KEY,
            application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            proxy_url VARCHAR(1000) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_proxies_app_id
        ON project_proxies(application_id);
    """)

async def down(conn):
    await conn.execute("DROP TABLE IF EXISTS project_proxies CASCADE;")
