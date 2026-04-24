ENVYBOX_FULL_DESCRIPTION = (
    "Envybox – мультисервис для роста показателей бизнеса.\n\n"
    "✅ Для лидогенерации\n"
    "Обратный звонок, Онлайн-чат, Квиз и Генератор клиентов, чтобы конвертировать "
    "трафик в целевые заявки.\n\n"
    "✅ Для управления вниманием\n"
    "Мультикнопка, Видеовиджет, Стадный инстинкт, Захватчик клиенток, "
    "Персонализатор форм, чтобы направить посетителя к целевому действию.\n\n"
    "✅ Для роста продаж\n"
    "EnvyCRM – соберет лиды со всех каналов, напомнит о повторных продажах, "
    "сохранит все нюансы коммуникации. Превратит посетителей в активных "
    "покупателей.\n\n"
    "Дарим 1000₽ на бонусный счет по промокоду «7we4j» при регистрации на сайте "
    "+ 8 дней бесплатного доступа. Оплачивайте ими до 50% стоимости всех сервисов."
)


async def up(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id                  SERIAL PRIMARY KEY,
            slug                VARCHAR(255) UNIQUE NOT NULL,
            name                VARCHAR(255) NOT NULL,
            logo_url            VARCHAR(1000) NOT NULL,
            short_description   TEXT NOT NULL,
            full_description    TEXT NOT NULL,
            website_url         VARCHAR(1000),
            sort_order          INTEGER NOT NULL DEFAULT 0,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_partners_active_sort
        ON partners(is_active, sort_order);
    """)

    # Trigger-free auto updated_at: we rely on the query layer to set updated_at = NOW()
    # on UPDATE. Keeping migration DB-engine-agnostic / simple.

    # Seed Envybox (idempotent on slug).
    await conn.execute(
        """
        INSERT INTO partners (
            slug, name, logo_url, short_description, full_description,
            website_url, sort_order, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (slug) DO NOTHING
        """,
        "envybox",
        "Envybox",
        "/static/partners/envybox-placeholder.png",
        "Мультисервис для роста показателей бизнеса",
        ENVYBOX_FULL_DESCRIPTION,
        None,
        0,
        True,
    )


async def down(conn):
    await conn.execute("DROP INDEX IF EXISTS idx_partners_active_sort;")
    await conn.execute("DROP TABLE IF EXISTS partners CASCADE;")
