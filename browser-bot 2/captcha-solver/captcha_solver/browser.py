"""Playwright browser lifecycle — isolated per solve request.

Why a fresh context per request: Yandex correlates sessions across Yandex ID
services. A long-lived browser would accumulate a fingerprint that SmartCaptcha
uses to decide whether to show the coordinate (hard) variant. Ephemeral contexts
keep each solve independent.
"""
from __future__ import annotations

import logging
import random
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
    disable_stealth: bool = False,
) -> AsyncIterator[Page]:
    """Yield a fresh Playwright Page with anti-detection and Yandex trackers blocked.

    `disable_stealth=True` switches off all evasion — useful for testing the solver
    against Yandex captcha (with full stealth Yandex often skips the captcha).
    """
    args = [] if disable_stealth else [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-webrtc",
    ]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, args=args)
        try:
            context = await _new_context(browser, proxy=proxy, disable_stealth=disable_stealth)
            try:
                page = await context.new_page()
                yield page
            finally:
                await context.close()
        finally:
            await browser.close()


async def _new_context(browser, *, proxy: str, disable_stealth: bool = False) -> BrowserContext:
    width, height = random.choice(_VIEWPORTS)
    kwargs = dict(
        viewport={"width": width, "height": height},
        user_agent=random.choice(_USER_AGENTS),
        locale="ru-RU",
        timezone_id="Europe/Moscow",
    )
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    context = await browser.new_context(**kwargs)
    if not disable_stealth:
        await context.add_init_script(_ANTI_DETECT_INIT)
        for pattern in _BLOCK_PATTERNS:
            await context.route(pattern, lambda route: route.abort())
    return context
