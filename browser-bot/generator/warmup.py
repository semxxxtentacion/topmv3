"""
Auto-pilot module — two scheduled jobs:

1. Auto-generate: check profile count, top up to MAX_PROFILES if needed
2. Auto-warmup:   refresh cookies on stale profiles (light / deep)

Both run on APScheduler intervals. No manual intervention required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from generator import database as db
from generator.fingerprints import generate_profiles
from generator.farmer import farm_one_profile, FARM_SITES, SEARCH_QUERIES
from generator.config import (
    WARMUP_INTERVAL_HOURS, WARMUP_BATCH_SIZE, WARMUP_WORKERS,
    MAX_PROFILES,
)
from generator import proxy_manager

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# How often to check if we need more profiles (minutes)
GENERATE_CHECK_INTERVAL_MIN = int(
    __import__("os").getenv("GENERATE_CHECK_INTERVAL_MIN", "10")
)
# How many profiles to generate per batch
GENERATE_BATCH_SIZE = int(
    __import__("os").getenv("GENERATE_BATCH_SIZE", "20")
)
# Workers for farming new profiles
GENERATE_WORKERS = int(
    __import__("os").getenv("GENERATE_WORKERS", "3")
)


# ---------------------------------------------------------------------------
# Auto-generate: top up profiles to MAX_PROFILES
# ---------------------------------------------------------------------------

async def run_generate_cycle():
    """Check how many active profiles exist, generate more if below limit."""
    try:
        current = await db.count_active_profiles()
    except Exception as e:
        logger.error(f"[autogen] Failed to count profiles: {e}")
        return

    slots = MAX_PROFILES - current
    if slots <= 0:
        logger.info(f"[autogen] Pool full: {current}/{MAX_PROFILES} active profiles")
        return

    batch = min(slots, GENERATE_BATCH_SIZE)
    logger.info(
        f"[autogen] {current}/{MAX_PROFILES} profiles — generating {batch} more"
    )

    profiles = generate_profiles(count=batch, source="builtin")

    semaphore = asyncio.Semaphore(GENERATE_WORKERS)

    async def farm_and_save(profile: dict):
        proxy = proxy_manager.next_proxy()
        async with semaphore:
            result = await farm_one_profile(profile, proxy_cfg=proxy, headless=True)
            
        cookies_count = len(result.get("cookies", []))
        if cookies_count == 0:
            logger.warning(f"[autogen] Профиль {str(result.get('pid', ''))[:8]} собрал 0 кук. Игнорируем.")
            return

        try:
            await db.insert_profile(result)
        except Exception as e:
            logger.error(f"[autogen] DB insert error: {e}")

    tasks = [farm_and_save(p) for p in profiles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok = sum(1 for r in results if not isinstance(r, Exception))
    errors = len(results) - ok
    logger.info(f"[autogen] Batch done: {ok} saved, {errors} errors")


# ---------------------------------------------------------------------------
# Warmup logic
# ---------------------------------------------------------------------------

async def warmup_profile(
    profile: dict,
    warmup_type: str = "auto",
    headless: bool = True,
) -> dict:
    """
    Warm up a single profile by revisiting Yandex services.

    warmup_type:
      - "auto": light by default, deep every 4th warmup
      - "light": quick visit (ya.ru + 1 search)
      - "deep": thorough visit (ya.ru + 2 searches + 3-5 services)
    """
    profile_id = UUID(str(profile["id"])) if "id" in profile else UUID(profile["pid"])
    short = str(profile_id)[:8]

    warmup_count = profile.get("warmup_count", 0)
    if warmup_type == "auto":
        warmup_type = "deep" if warmup_count > 0 and warmup_count % 4 == 0 else "light"

    cookies_before = profile.get("cookies_count", len(profile.get("cookies", [])))
    start = time.monotonic()

    logger.info(f"[{short}] Starting {warmup_type} warmup (#{warmup_count + 1})")

    proxy = proxy_manager.next_proxy()
    result = await farm_one_profile(profile, proxy_cfg=proxy, headless=headless)

    duration = int(time.monotonic() - start)
    new_cookies = result.get("cookies", [])
    new_localstorage = result.get("localstorage", {})
    captcha = result.get("partial", False) or result.get("is_captcha", False)

    sites = []
    if warmup_type == "deep":
        sites = random.sample(FARM_SITES, min(5, len(FARM_SITES)))
    else:
        sites = random.sample(FARM_SITES, min(2, len(FARM_SITES)))

    try:
        await db.update_after_warmup(
            profile_id=profile_id,
            cookies=new_cookies,
            localstorage=new_localstorage,
            warmup_type=warmup_type,
            sites_visited=sites,
            cookies_before=cookies_before,
            captcha_hit=captcha,
            duration_sec=duration,
        )

        label = "WARM" if len(new_cookies) >= 10 and not captcha else f"PARTIAL({len(new_cookies)}ck)"
        logger.info(
            f"[{short}] Warmup done: {label}, "
            f"{cookies_before}→{len(new_cookies)} cookies, {duration}s"
        )
    except Exception as e:
        logger.error(f"[{short}] Failed to save warmup results: {e}")

    return result


async def run_warmup_cycle(
    batch_size: int = WARMUP_BATCH_SIZE,
    workers: int = WARMUP_WORKERS,
):
    """Run one warmup cycle: pick stale profiles and warm them up."""
    logger.info(f"[warmup] Cycle starting (batch={batch_size}, workers={workers})")

    try:
        profiles = await db.get_profiles_for_warmup(limit=batch_size)
    except Exception as e:
        logger.error(f"[warmup] Failed to fetch profiles: {e}")
        return

    if not profiles:
        logger.info("[warmup] No profiles need warming up")
        return

    logger.info(f"[warmup] Warming up {len(profiles)} profiles")

    semaphore = asyncio.Semaphore(workers)

    async def do_one(profile: dict):
        async with semaphore:
            try:
                await warmup_profile(profile)
            except Exception as e:
                logger.error(f"[warmup] Error for {str(profile.get('id', ''))[:8]}: {e}")

    tasks = [do_one(p) for p in profiles]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"[warmup] Cycle complete: {len(profiles)} profiles processed")


# ---------------------------------------------------------------------------
# Scheduler — two jobs: auto-generate + auto-warmup
# ---------------------------------------------------------------------------

def start_scheduler():
    """Start both auto-generate and auto-warmup cron jobs."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler()

    # Job 1: auto-generate — check every N minutes, top up if needed
    _scheduler.add_job(
        run_generate_cycle,
        trigger=IntervalTrigger(minutes=GENERATE_CHECK_INTERVAL_MIN),
        id="auto_generate",
        name="Auto-generate profiles",
        replace_existing=True,
    )

    # Job 2: auto-warmup — refresh cookies every N hours
    _scheduler.add_job(
        run_warmup_cycle,
        trigger=IntervalTrigger(hours=WARMUP_INTERVAL_HOURS),
        id="auto_warmup",
        name="Auto-warmup profiles",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        f"Scheduler started: "
        f"generate every {GENERATE_CHECK_INTERVAL_MIN}min (up to {MAX_PROFILES} profiles), "
        f"warmup every {WARMUP_INTERVAL_HOURS}h"
    )


def stop_scheduler():
    """Stop all scheduled jobs."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")