"""Playwright browser lifecycle — isolated per solve request."""
from __future__ import annotations

import logging
import random
import urllib.parse
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
]

_VIEWPORTS = [(1366, 768), (1536, 864), (1920, 1080)]

_ANTI_DETECT_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4]});
Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en']});
if (window.RTCPeerConnection) { window.RTCPeerConnection = undefined; }
if (window.webkitRTCPeerConnection) { window.webkitRTCPeerConnection = undefined; }
"""

_BLOCK_PATTERNS = [
    "**/*metrika*",
    "**/*mc.yandex*",
    "**/*an.yandex*",
    "**/*googletagmanager*",
    "**/*appsflyer*",
]

@asynccontextmanager
async def browser_page(
    *,
    headless: bool = True,
    proxy: str = "",
) -> AsyncIterator[Page]:
    """Yield a fresh Playwright Page with anti-detection and Yandex trackers blocked."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-webrtc",
            ],
        )
        try:
            context = await _new_context(browser, proxy=proxy)
            try:
                page = await context.new_page()
                yield page
            finally:
                await context.close()
        finally:
            await browser.close()

async def _new_context(browser, *, proxy: str) -> BrowserContext:
    width, height = random.choice(_VIEWPORTS)
    kwargs = dict(
        viewport={"width": width, "height": height},
        user_agent=random.choice(_USER_AGENTS),
        locale="ru-RU",
        timezone_id="Europe/Moscow",
    )
    
    if proxy:
        # ИСПРАВЛЕНИЕ: Правильный парсинг прокси с логином и паролем для Playwright
        parsed = urllib.parse.urlparse(proxy)
        if parsed.username and parsed.password:
            kwargs["proxy"] = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": parsed.username,
                "password": parsed.password,
            }
        else:
            kwargs["proxy"] = {"server": proxy}
            
    context = await browser.new_context(**kwargs)
    await context.add_init_script(_ANTI_DETECT_INIT)
    for pattern in _BLOCK_PATTERNS:
        await context.route(pattern, lambda route: route.abort())
    return context
