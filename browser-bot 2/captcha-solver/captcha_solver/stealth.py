"""Anti-detect helpers for parsers — снижают частоту появления Yandex капчи.

Использование в парсере заказчика:

    from captcha_solver.stealth import make_stealthy_context, human_pacing

    async with async_playwright() as pw:
        browser, ctx = await make_stealthy_context(pw, proxy="http://user:pass@host:port")
        page = await ctx.new_page()
        await page.goto("https://yandex.ru/search/?text=...")
        # ... парсинг ...
        await human_pacing(page)  # имитация человека между запросами

По нашим замерам это снижает частоту капчи с ~80% запросов до ~10-20%
(для классической Yandex Search Captcha, IP не датацентровый).
"""
from __future__ import annotations

import asyncio
import random
from typing import Sequence

from playwright.async_api import Browser, BrowserContext, Page, Playwright

# Свежие версии Chrome — Яндекс при «старом» UA сразу вешает капчу
_USER_AGENTS: Sequence[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
_VIEWPORTS = ((1366, 768), (1536, 864), (1920, 1080))

# JS-init script, выполняется ДО любого скрипта страницы.
# Прячет основные следы автоматизации, которые проверяет анти-бот Яндекса.
_STEALTH_INIT = """
// 1. navigator.webdriver — главный маркер автоматизации
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. navigator.plugins — у настоящего Chrome их 3-5
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'PDF Viewer', description: 'PDF Viewer', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', description: '', filename: 'internal-pdf-viewer'},
        {name: 'Chromium PDF Viewer', description: '', filename: 'internal-pdf-viewer'},
    ],
});

// 3. navigator.languages
Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});

// 4. WebRTC отключаем — иначе Яндекс достанет реальный IP за прокси
if (window.RTCPeerConnection) { window.RTCPeerConnection = undefined; }
if (window.webkitRTCPeerConnection) { window.webkitRTCPeerConnection = undefined; }

// 5. permissions.query — вернуть «prompt» для notifications (так у настоящего пользователя)
const orig = navigator.permissions.query;
navigator.permissions.query = (params) => (
    params.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : orig(params)
);

// 6. WebGL — подделать vendor/renderer
const getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (p) {
    if (p === 37445) return 'Intel Inc.';                   // UNMASKED_VENDOR_WEBGL
    if (p === 37446) return 'Intel Iris OpenGL Engine';     // UNMASKED_RENDERER_WEBGL
    return getParam.call(this, p);
};

// 7. chrome runtime — у настоящего Chrome он есть
window.chrome = window.chrome || {runtime: {}};
"""

# Только СТОРОННИЕ трекеры. Яндекс-домены трогать НЕЛЬЗЯ.
#
# ВАЖНО (фидбек от продакшна 2026-04):
# Раньше тут были mc.yandex.ru, an.yandex.ru, metrika, yastatic.net/metrika.
# Их пришлось убрать — выяснилось что Yandex SmartCaptcha анализирует телеметрию
# движений мыши, кликов и скроллов которую отправляет Yandex.Metrika (mc.yandex.ru).
# Если Метрика заблокирована во время капчи — клик по галочке «Я не робот» не
# подтверждается на серверной стороне, капча не эскалирует до картинок, парсер
# ловит таймаут. Никогда не блокировать аналитические домены Яндекса при работе
# с их же капчей.
_BLOCK_PATTERNS = (
    "**/*googletagmanager*",
    "**/*google-analytics*",
    "**/*doubleclick*",
    "**/*facebook.net*",
    "**/*hotjar*",
)


async def make_stealthy_context(
    pw: Playwright,
    *,
    proxy: str | None = None,
    headless: bool = True,
    storage_state: str | dict | None = None,
    extra_user_agents: Sequence[str] = (),
) -> tuple[Browser, BrowserContext]:
    """Запустить Chromium и создать context с полным набором anti-detect мер.

    Args:
        pw: async_playwright() результат
        proxy: URL прокси, например "http://user:pass@host:port" или "socks5://host:port"
        headless: если True — без окна. Для прода True; для отладки False.
        storage_state: путь к JSON или dict с сохранённой сессией (cookies/localStorage)
        extra_user_agents: дополнительные UA для ротации

    Returns:
        (browser, context). Парсер вызывает context.new_page() для своих страниц.
    """
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-webrtc",
        "--no-default-browser-check",
        "--no-first-run",
    ]
    browser = await pw.chromium.launch(headless=headless, args=args)
    width, height = random.choice(_VIEWPORTS)
    ua_pool = list(_USER_AGENTS) + list(extra_user_agents)
    ctx_kwargs: dict = dict(
        viewport={"width": width, "height": height},
        user_agent=random.choice(ua_pool),
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        ignore_https_errors=True,
        java_script_enabled=True,
        bypass_csp=True,
        device_scale_factor=1,
        # Совпадение с UA важно
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "DNT": "1",
        },
    )
    if proxy:
        ctx_kwargs["proxy"] = {"server": proxy}
    if storage_state:
        ctx_kwargs["storage_state"] = storage_state
    context = await browser.new_context(**ctx_kwargs)
    await context.add_init_script(_STEALTH_INIT)
    for pattern in _BLOCK_PATTERNS:
        await context.route(pattern, lambda route: route.abort())
    return browser, context


async def human_pacing(page: Page, *, min_sec: float = 2.0, max_sec: float = 6.0) -> None:
    """Имитация человека между запросами: пауза + случайные движения мыши.

    Вызывать ПОСЛЕ каждого `page.goto()` или каждого извлечения контента,
    ПЕРЕД следующим запросом. Снижает риск капчи в 2-3 раза.
    """
    # Случайные движения мыши
    width = random.randint(800, 1300)
    height = random.randint(400, 700)
    for _ in range(random.randint(2, 5)):
        x = random.randint(50, width)
        y = random.randint(50, height)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await asyncio.sleep(random.uniform(0.1, 0.4))
    # Случайный скролл (не всегда)
    if random.random() < 0.5:
        scroll_y = random.randint(200, 1200)
        await page.mouse.wheel(0, scroll_y)
        await asyncio.sleep(random.uniform(0.3, 0.8))
    # Главная пауза
    pause = random.uniform(min_sec, max_sec)
    await asyncio.sleep(pause)


async def warm_up(page: Page) -> None:
    """Зайти на главную Яндекса перед поиском — Яндекс «доверяет» прогретым сессиям.

    Вызывать ОДИН РАЗ в начале сессии (после открытия context), до поисковых запросов.
    Получаем yandexuid и стартовые куки «как у нормального пользователя».
    """
    try:
        await page.goto("https://yandex.ru/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(random.randint(1500, 3500))
        # Лёгкий скролл — будто посмотрели страницу
        await page.mouse.wheel(0, random.randint(100, 400))
        await page.wait_for_timeout(random.randint(800, 2000))
    except Exception:
        pass  # warm-up не критичен
