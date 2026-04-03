import asyncpg
from bot.db.connection import get_pool


async def upsert_user(telegram_id: int, name: str, username: str, code: str) -> None:
    """Создаёт пользователя если не существует, обновляет code, name, username."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, name, username, code)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id)
            DO UPDATE SET code = EXCLUDED.code,
                          name = EXCLUDED.name,
                          username = EXCLUDED.username
            """,
            telegram_id, name, username, code
        )


async def get_next_app_number() -> int:
    """Атомарно получает следующий номер заявки через sequence."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT nextval('app_number_seq')")
    return val

async def get_user_applications(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch_all(
            """
            SELECT * FROM applications
            WHERE telegram_id = $1
            """,
            telegram_id
        )
        
async def update_application_status(request_id: int, status: str) -> None:
    """Обновляет статус заявки (accepted / rejected)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE applications
            SET status = $1::application_status
            WHERE id = $2
            """,
            status, request_id
        )

async def get_application(telegram_id: int, site: str) -> dict | None:
    """Получает данные заявки для передачи в yandex-bot."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT site, region, keywords, yandex, google
            FROM applications
            WHERE telegram_id = $1 AND site = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            telegram_id, site
        )
    return dict(row) if row else None