from backend.db.bot_db import get_bot_pool


async def get_profiles_stats() -> dict:
    pool = await get_bot_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE cookies_count > 0) AS with_cookies,
                COUNT(*) FILTER (WHERE cookies_count = 0) AS without_cookies
            FROM profiles
        """)
        return {
            "total": row["total"],
            "with_cookies": row["with_cookies"],
            "without_cookies": row["without_cookies"],
        }
