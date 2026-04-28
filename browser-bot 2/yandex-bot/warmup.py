from __future__ import annotations

"""
Profile warmup: visit random sites (without Yandex Metrika)
before doing the real PF action. Makes the profile look organic.
"""

import asyncio
import random
import logging
from pathlib import Path
from urllib.parse import urlparse

import human
from config import (
    WARMUP_SITES_FILE, WARMUP_MIN_SITES, WARMUP_MAX_SITES,
    WARMUP_MIN_TIME, WARMUP_MAX_TIME,
)

logger = logging.getLogger(__name__)

_sites_cache: list[str] | None = None

# Fallback sites known to have no Yandex Metrika (general-purpose, safe)
FALLBACK_SITES = [
    'https://yandex.ru/news',
    'https://yandex.ru/maps',
    'https://yandex.ru/pogoda',
    'https://yandex.ru/images',
    'https://yandex.ru/video',
    'https://yandex.ru/market',
    'https://yandex.ru/translate',
    'https://yandex.ru/afisha',
    'https://yandex.ru/tutor',
    'https://ya.ru/',
]


def _load_sites() -> list[str]:
    global _sites_cache
    if _sites_cache is not None:
        return _sites_cache

    path = Path(WARMUP_SITES_FILE)
    sites = []
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if not line.startswith('http'):
                line = 'https://' + line
            sites.append(line)
        logger.info(f"Loaded {len(sites)} warmup sites from {path.name}")

    if not sites:
        sites = FALLBACK_SITES.copy()
        logger.info(f"Using {len(sites)} fallback warmup sites")

    _sites_cache = sites
    return _sites_cache


async def _visit_one_site(page, url: str, time_on_site: float) -> bool:
    """Visit a single warmup site: load, scroll, spend time, leave. Returns True on success."""
    logger.debug(f"Warmup: visiting {url} for ~{time_on_site:.0f}s")

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
    except Exception as e:
        logger.warning(f"Warmup: failed to load {url}: {e}")
        return False

    await human.pause(1.0, 2.5)

    t0 = asyncio.get_event_loop().time()
    deadline = t0 + time_on_site

    for _ in range(random.randint(2, 5)):
        if asyncio.get_event_loop().time() >= deadline:
            break
        await human.scroll(page, 'down', random.randint(100, 400))
        await human.pause(1.5, 4.0)

        if random.random() < 0.3:
            await human.idle_mouse(page, random.uniform(0.5, 2.0))

    if random.random() < 0.4:
        await human.scroll(page, 'up', random.randint(100, 300))
        await human.pause(0.5, 1.5)

    # Click a random internal link ~30% of the time
    if random.random() < 0.3:
        current_host = urlparse(page.url).hostname
        links = await page.query_selector_all('a[href]')
        internal = []
        for a in links[:30]:
            try:
                href = await a.get_attribute('href')
                if href and not href.startswith('#') and 'javascript:' not in href:
                    parsed = urlparse(href)
                    if (parsed.hostname or current_host) == current_host and await a.is_visible():
                        internal.append(a)
            except Exception:
                continue

        if internal:
            chosen = random.choice(internal[:10])
            try:
                await chosen.scroll_into_view_if_needed()
                await human.pause(0.3, 0.7)
                await human.click_element(page, chosen)
                await page.wait_for_load_state('domcontentloaded')
                await human.pause(2.0, 5.0)
            except Exception:
                pass

    # Fill any remaining time
    remaining = deadline - asyncio.get_event_loop().time()
    if remaining > 1:
        await human.idle_mouse(page, min(remaining, 8.0))

    return True


async def run_warmup(page) -> int:
    """
    Visit several random warmup sites.
    Returns the number of sites successfully visited.
    """
    sites = _load_sites()
    count = random.randint(WARMUP_MIN_SITES, WARMUP_MAX_SITES)
    chosen_sites = random.sample(sites, min(count, len(sites)))

    logger.info(f"Warmup: visiting {len(chosen_sites)} sites")
    visited = 0

    for url in chosen_sites:
        time_on_site = random.uniform(WARMUP_MIN_TIME, WARMUP_MAX_TIME)
        try:
            ok = await _visit_one_site(page, url, time_on_site)
            if ok:
                visited += 1
        except Exception as e:
            logger.warning(f"Warmup site error ({url}): {e}")

    logger.info(f"Warmup done: visited {visited}/{len(chosen_sites)} sites")
    return visited
