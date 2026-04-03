import asyncpg
from backend.config import settings

_pool: asyncpg.Pool | None = None


async def get_bot_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.bot_database_url)
    return _pool


async def close_bot_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
