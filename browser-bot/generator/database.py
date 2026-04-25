"""
Database layer — async PostgreSQL via asyncpg + raw SQL.
No ORM, keeps it simple and fast.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from generator.config import DATABASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    """Convert SQLAlchemy-style URL to plain DSN for asyncpg."""
    url = DATABASE_URL
    # asyncpg wants postgresql://, not postgresql+asyncpg://
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(_dsn(), min_size=2, max_size=10)
        logger.info("Database pool created")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

async def count_active_profiles() -> int:
    """Count profiles that are not dead (new + warm + partial)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM profiles WHERE status != 'dead'"
        )
        return row["cnt"]


async def insert_profile(profile: dict) -> UUID:
    """Insert a generated profile into the DB. Returns profile UUID."""
    pool = await get_pool()

    pid = UUID(profile["pid"])
    status = "new"
    if profile.get("warm"):
        status = "warm"
    elif profile.get("partial"):
        status = "partial"

    cookies = profile.get("cookies", [])
    localstorage = profile.get("localstorage", {})

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO profiles (
                    id, party, device_model, device_name, device_chipset,
                    platform, platform_version, browser, browser_version,
                    fingerprints, viewport, mouse_config, geo,
                    proxy_used, status, cookies_count, is_captcha
                ) VALUES (
                    $1, $2::fingerprint_source, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb,
                    $14, $15::profile_status, $16, $17
                )
                """,
                pid,
                profile.get("party", "builtin"),
                profile.get("device_model", ""),
                profile.get("device_name", ""),
                profile.get("device_chipset", ""),
                profile.get("platform", "Android"),
                profile.get("platform_version", "14"),
                profile.get("browser", "Chrome"),
                profile.get("browser_version", ""),
                json.dumps(profile.get("fingerprints", {}), ensure_ascii=False),
                json.dumps(profile.get("viewport", {})),
                json.dumps(profile.get("mouse_config", {})),
                json.dumps(profile.get("geo", {}), ensure_ascii=False),
                profile.get("proxy"),
                status,
                len(cookies),
                profile.get("is_captcha", False),
            )

            # Save initial cookies if we have any
            if cookies or localstorage:
                await conn.execute(
                    """
                    INSERT INTO profile_cookies (profile_id, cookies, localstorage, source)
                    VALUES ($1, $2::jsonb, $3::jsonb, 'initial')
                    """,
                    pid,
                    json.dumps(cookies, ensure_ascii=False, default=str),
                    json.dumps(localstorage, ensure_ascii=False),
                )

    return pid


async def insert_profiles_batch(profiles: list[dict]) -> list[UUID]:
    """Insert multiple profiles in a single transaction."""
    pids = []
    for p in profiles:
        pid = await insert_profile(p)
        pids.append(pid)
    return pids


async def get_profile(profile_id: UUID) -> dict | None:
    """Get a profile with its latest cookies."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM profiles WHERE id = $1", profile_id
        )
        if not row:
            return None

        profile = dict(row)
        # Convert JSONB fields from strings
        for field in ("fingerprints", "viewport", "mouse_config", "geo"):
            if isinstance(profile[field], str):
                profile[field] = json.loads(profile[field])

        # Get latest cookies
        cookies_row = await conn.fetchrow(
            """
            SELECT cookies, localstorage, collected_at
            FROM profile_cookies
            WHERE profile_id = $1
            ORDER BY collected_at DESC
            LIMIT 1
            """,
            profile_id,
        )
        if cookies_row:
            profile["cookies"] = (
                json.loads(cookies_row["cookies"])
                if isinstance(cookies_row["cookies"], str)
                else cookies_row["cookies"]
            )
            profile["localstorage"] = (
                json.loads(cookies_row["localstorage"])
                if isinstance(cookies_row["localstorage"], str)
                else cookies_row["localstorage"]
            )
            profile["cookies_collected_at"] = cookies_row["collected_at"]
        else:
            profile["cookies"] = []
            profile["localstorage"] = {}

        return profile


async def list_profiles(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List profiles with optional status filter."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT id, party, device_name, status, cookies_count,
                       warmup_count, last_warmup_at, created_at
                FROM profiles
                WHERE status = $1::profile_status
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status, limit, offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, party, device_name, status, cookies_count,
                       warmup_count, last_warmup_at, created_at
                FROM profiles
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )
        return [dict(r) for r in rows]


async def get_stats() -> dict:
    """Get profile statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'warm') AS warm,
                COUNT(*) FILTER (WHERE status = 'partial') AS partial,
                COUNT(*) FILTER (WHERE status = 'new') AS new,
                COUNT(*) FILTER (WHERE status = 'dead') AS dead,
                COALESCE(SUM(cookies_count), 0) AS total_cookies,
                COALESCE(AVG(cookies_count), 0) AS avg_cookies,
                COUNT(*) FILTER (
                    WHERE status != 'dead'
                    AND (last_warmup_at IS NULL OR last_warmup_at < NOW() - INTERVAL '2 days')
                ) AS needing_warmup
            FROM profiles
            """
        )
        return dict(row)


async def take_random_profile(status: str = "warm") -> dict | None:
    """Pick a random profile with given status, return it with cookies, then delete."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM profiles
            WHERE status = $1::profile_status
            ORDER BY RANDOM()
            LIMIT 1
            """,
            status,
        )
        if not row:
            return None

        profile_id = row["id"]

    # Get full profile with cookies
    profile = await get_profile(profile_id)
    if not profile:
        return None

    return profile


async def delete_profile(profile_id: UUID) -> bool:
    """Delete a profile and all related data (CASCADE)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM profiles WHERE id = $1", profile_id
        )
        return result == "DELETE 1"


async def get_profiles_for_warmup(limit: int = 20) -> list[dict]:
    """Get profiles that need warming up, oldest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.*, pc.cookies, pc.localstorage
            FROM profiles p
            LEFT JOIN LATERAL (
                SELECT cookies, localstorage
                FROM profile_cookies
                WHERE profile_id = p.id
                ORDER BY collected_at DESC
                LIMIT 1
            ) pc ON TRUE
            WHERE p.status != 'dead'
              AND (
                p.last_warmup_at IS NULL
                OR p.last_warmup_at < NOW() - INTERVAL '2 days'
              )
            ORDER BY COALESCE(p.last_warmup_at, p.created_at) ASC
            LIMIT $1
            """,
            limit,
        )

        profiles = []
        for row in rows:
            p = dict(row)
            for field in ("fingerprints", "viewport", "mouse_config", "geo"):
                if isinstance(p[field], str):
                    p[field] = json.loads(p[field])
            if isinstance(p.get("cookies"), str):
                p["cookies"] = json.loads(p["cookies"])
            if isinstance(p.get("localstorage"), str):
                p["localstorage"] = json.loads(p["localstorage"])
            p["cookies"] = p.get("cookies") or []
            p["localstorage"] = p.get("localstorage") or {}
            # Reconstruct pid for farmer compatibility
            p["pid"] = str(p["id"])
            profiles.append(p)

        return profiles


async def update_after_warmup(
    profile_id: UUID,
    cookies: list,
    localstorage: dict,
    warmup_type: str,
    sites_visited: list[str],
    cookies_before: int,
    captcha_hit: bool,
    duration_sec: int,
):
    """Update profile after a warmup session."""
    pool = await get_pool()
    cookies_after = len(cookies)

    status = "warm" if cookies_after >= 10 and not captcha_hit else "partial"
    # If captcha 3 times in a row → dead
    # (checked via warmup_history, not here — here we just record)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE profiles SET
                    status = $2::profile_status,
                    cookies_count = $3,
                    is_captcha = $4,
                    warmup_count = warmup_count + 1,
                    last_warmup_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                profile_id, status, cookies_after, captcha_hit,
            )

            await conn.execute(
                """
                INSERT INTO profile_cookies (profile_id, cookies, localstorage, source)
                VALUES ($1, $2::jsonb, $3::jsonb, 'warmup')
                """,
                profile_id,
                json.dumps(cookies, ensure_ascii=False, default=str),
                json.dumps(localstorage, ensure_ascii=False),
            )

            await conn.execute(
                """
                INSERT INTO warmup_history (
                    profile_id, warmup_type, sites_visited,
                    cookies_before, cookies_after, captcha_hit, duration_sec
                ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                """,
                profile_id, warmup_type,
                json.dumps(sites_visited),
                cookies_before, cookies_after, captcha_hit, duration_sec,
            )

            # Check if profile should be marked dead (3 captchas in a row)
            recent = await conn.fetch(
                """
                SELECT captcha_hit FROM warmup_history
                WHERE profile_id = $1
                ORDER BY created_at DESC
                LIMIT 3
                """,
                profile_id,
            )
            if len(recent) >= 3 and all(r["captcha_hit"] for r in recent):
                await conn.execute(
                    "UPDATE profiles SET status = 'dead'::profile_status WHERE id = $1",
                    profile_id,
                )
                logger.warning(f"Profile {profile_id} marked as DEAD (3 consecutive captchas)")
