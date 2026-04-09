async def up(conn):
	await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,

                payment_id BIGINT UNIQUE NOT NULL,
                telegram_id BIGINT NOT NULL,

                tariff TEXT NOT NULL,

                amount INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'NEW',

                created_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
            """
        )