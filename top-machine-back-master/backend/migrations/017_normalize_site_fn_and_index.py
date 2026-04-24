async def up(conn):
    # Нормализация сайта для дедупликации:
    # lowercase, убираем http(s)://, leading www., trailing /.
    await conn.execute("""
        CREATE OR REPLACE FUNCTION normalize_site(url text) RETURNS text
        LANGUAGE sql IMMUTABLE AS $$
          SELECT lower(regexp_replace(regexp_replace(regexp_replace(
            coalesce(url, ''), '^https?://', ''), '^www\\.', ''), '/+$', ''))
        $$;
    """)

    # Перегрузка для VARCHAR (колонка applications.site имеет тип varchar,
    # Postgres не делает implicit cast varchar→text в function lookup).
    await conn.execute("""
        CREATE OR REPLACE FUNCTION normalize_site(url varchar) RETURNS text
        LANGUAGE sql IMMUTABLE AS $$
          SELECT normalize_site(url::text)
        $$;
    """)

    # Партиал-индекс на нормализованный сайт для быстрого EXISTS/поиска дублей.
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_applications_normalized_site
          ON applications (normalize_site(site))
          WHERE site IS NOT NULL AND site != '';
    """)


async def down(conn):
    await conn.execute("DROP INDEX IF EXISTS idx_applications_normalized_site;")
    await conn.execute("DROP FUNCTION IF EXISTS normalize_site(varchar);")
    await conn.execute("DROP FUNCTION IF EXISTS normalize_site(text);")
