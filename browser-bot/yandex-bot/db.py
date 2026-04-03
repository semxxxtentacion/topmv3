from __future__ import annotations

"""
Profile loader — reads profiles from acc-generator's PostgreSQL database.
Maps acc_generator schema (profiles + profile_cookies) to the dict format
expected by worker.py.
"""

import asyncpg
import json
import logging
import random

from config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        logger.info(f"DB pool created: {DATABASE_URL.split('@')[-1]}")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _parse_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
    return value


def _row_to_profile(row: dict) -> dict:
    """Convert a DB row (acc_generator schema) to the dict format worker.py expects."""
    fingerprints = _parse_json(row.get('fingerprints', {}))
    viewport = _parse_json(row.get('viewport', {}))
    mouse_config = _parse_json(row.get('mouse_config', {}))
    geo = _parse_json(row.get('geo', {}))
    cookies = _parse_json(row.get('cookies')) or []
    localstorage = _parse_json(row.get('localstorage')) or {}

    return {
        'pid': str(row['id']),
        'ismobiledevice': row.get('platform', '').lower() == 'android',
        'platform': row.get('platform', 'Android'),
        'platform_version': row.get('platform_version', '14'),
        'browser': row.get('browser', 'Chrome'),
        'browser_version': row.get('browser_version', '120.0.0.0'),
        'device_model': row.get('device_model', ''),
        'device_name': row.get('device_name', ''),
        'fingerprints': fingerprints,
        'viewport': viewport,
        'mouse_config': mouse_config,
        'geo': geo,
        'cookies': cookies,
        'localstorage': localstorage,
        'proxy': row.get('proxy_used', ''),
        'status': row.get('status', 'new'),
        'cookies_count': row.get('cookies_count', 0),
    }


async def get_profiles(pool: asyncpg.Pool, limit: int = 50, status: str = 'warm') -> list[dict]:
    """
    Load profiles from acc_generator DB.
    Prefers warm profiles; falls back to any non-dead.
    Joins latest cookies from profile_cookies table.
    """
    query = """
        SELECT
            p.id, p.device_model, p.device_name,
            p.platform, p.platform_version,
            p.browser, p.browser_version,
            p.fingerprints, p.viewport, p.mouse_config, p.geo,
            p.proxy_used, p.status, p.cookies_count,
            pc.cookies, pc.localstorage
        FROM profiles p
        LEFT JOIN LATERAL (
            SELECT cookies, localstorage
            FROM profile_cookies
            WHERE profile_id = p.id
            ORDER BY collected_at DESC
            LIMIT 1
        ) pc ON TRUE
        WHERE p.status = $1::profile_status
        ORDER BY
            (CASE WHEN p.cookies_count > 0 THEN 0 ELSE 1 END),
            random()
        LIMIT $2
    """
    rows = await pool.fetch(query, status, limit)

    # If not enough warm profiles, also grab partial/new
    if len(rows) < limit:
        extra_query = """
            SELECT
                p.id, p.device_model, p.device_name,
                p.platform, p.platform_version,
                p.browser, p.browser_version,
                p.fingerprints, p.viewport, p.mouse_config, p.geo,
                p.proxy_used, p.status, p.cookies_count,
                pc.cookies, pc.localstorage
            FROM profiles p
            LEFT JOIN LATERAL (
                SELECT cookies, localstorage
                FROM profile_cookies
                WHERE profile_id = p.id
                ORDER BY collected_at DESC
                LIMIT 1
            ) pc ON TRUE
            WHERE p.status != 'dead'::profile_status AND p.status != $1::profile_status
            ORDER BY random()
            LIMIT $2
        """
        extra_rows = await pool.fetch(extra_query, status, limit - len(rows))
        rows = list(rows) + list(extra_rows)

    profiles = [_row_to_profile(dict(row)) for row in rows]
    logger.info(f"Loaded {len(profiles)} profiles from DB (requested status={status})")

    if profiles:
        sample = profiles[0]
        logger.info(
            f"Sample: pid={sample['pid']}, "
            f"device={sample['device_name']}, "
            f"browser={sample['browser']}/{sample['browser_version']}, "
            f"cookies={len(sample.get('cookies', []))}, "
            f"status={sample['status']}"
        )

    return profiles
