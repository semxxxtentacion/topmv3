"""
Cookie farmer: launches real Chromium with a generated fingerprint,
visits Yandex services, collects cookies and localStorage.

Without proxies Yandex will captcha after ~10 fast requests from one IP.
The farmer handles this via:
  - collecting cookies even on captcha pages (partial harvest)
  - configurable delay between profiles (--delay flag)
  - automatic cooldown after consecutive captchas
"""

from __future__ import annotations

import asyncio
import random
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from generator.stealth import build_stealth_js
from generator import human

logger = logging.getLogger(__name__)

# Shared captcha rate tracker (across workers within one process)
_captcha_window: list[float] = []
_captcha_lock = asyncio.Lock()

CAPTCHA_COOLDOWN = 60
CAPTCHA_THRESHOLD = 3
CAPTCHA_WINDOW_SEC = 30


async def _captcha_backoff():
    """If too many captchas recently, sleep to let Yandex cool down."""
    async with _captcha_lock:
        now = time.monotonic()
        _captcha_window[:] = [t for t in _captcha_window if now - t < CAPTCHA_WINDOW_SEC]
        if len(_captcha_window) >= CAPTCHA_THRESHOLD:
            wait = CAPTCHA_COOLDOWN + random.uniform(5, 20)
            logger.warning(
                f"Captcha rate high ({len(_captcha_window)} in {CAPTCHA_WINDOW_SEC}s), "
                f"cooling down {wait:.0f}s"
            )
            _captcha_window.clear()
            await asyncio.sleep(wait)


async def _record_captcha():
    async with _captcha_lock:
        _captcha_window.append(time.monotonic())


# Sites to visit during farming (Yandex ecosystem)
FARM_SITES = [
    "https://yandex.ru/news",
    "https://yandex.ru/pogoda",
    "https://yandex.ru/images",
    "https://yandex.ru/video",
    "https://yandex.ru/maps",
    "https://yandex.ru/market",
    "https://yandex.ru/translate",
    "https://dzen.ru",
]

SEARCH_QUERIES = [
    "погода москва", "курс доллара", "новости сегодня",
    "рецепт борща", "расписание электричек", "афиша кино",
    "купить телефон", "авиабилеты дешево",
    "вакансии москва", "калькулятор онлайн",
    "гороскоп на сегодня", "рецепты на ужин",
    "смотреть фильмы онлайн", "погода на неделю",
    "карта метро москвы", "доставка еды",
    "расписание поездов", "онлайн переводчик",
    "сколько время", "пробки на дорогах",
    "скачать музыку", "новые фильмы 2025",
    "спорт новости", "рецепты пирогов",
    "где купить ноутбук", "как почистить компьютер",
]

SEARCH_INPUT_SELECTORS = [
    'input[name="text"]',
    'textarea[name="text"]',
    '.mini-suggest__input',
    'input.input__control',
    '.search3__input input',
]

CAPTCHA_SELECTORS = [
    '.CheckboxCaptcha',
    '.AdvancedCaptcha',
    'form[action*="captcha"]',
    '.SmartCaptcha',
]


async def _has_captcha(page) -> bool:
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            continue
    return False


async def _find_search_input(page) -> str | None:
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el:
                return sel
        except Exception:
            continue
    return None


async def _do_search(page, query: str):
    """Type a search query and browse results briefly."""
    input_sel = await _find_search_input(page)
    if not input_sel:
        return

    await human.click(page, input_sel)
    await human.pause(0.3, 0.7)
    await human.type_text(page, input_sel, query)
    await human.pause(0.5, 1.0)
    await page.keyboard.press("Enter")

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        return

    await human.pause(2.0, 4.0)

    if await _has_captcha(page):
        return

    for _ in range(random.randint(2, 4)):
        await human.scroll(page, "down", random.randint(200, 500))
        await human.pause(1.0, 3.0)


async def _visit_site(page, url: str):
    """Visit a Yandex service page and scroll around."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        return

    await human.pause(1.5, 3.0)

    if await _has_captcha(page):
        return

    for _ in range(random.randint(1, 3)):
        await human.scroll(page, "down", random.randint(150, 400))
        await human.pause(1.0, 2.5)

    if random.random() < 0.3:
        await human.scroll(page, "up", random.randint(100, 200))
        await human.pause(0.5, 1.0)


async def _collect_localstorage(page) -> dict:
    try:
        return await page.evaluate("""() => {
            const items = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                items[key] = localStorage.getItem(key);
            }
            return items;
        }""")
    except Exception:
        return {}


async def farm_one_profile(
    profile: dict,
    proxy_cfg: dict | None = None,
    headless: bool = True,
) -> dict:
    """
    Full farming cycle for one profile.
    Collects whatever cookies are available even if captcha appears.
    """
    pid = profile["pid"]
    short = pid[:8]
    fp = profile["fingerprints"]
    nav = fp.get("navigator", {})
    viewport = profile.get("viewport", {"width": 412, "height": 915, "dpr": 2.625})
    got_captcha = False

    await _captcha_backoff()

    async with async_playwright() as pw:
        launch_args = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }

        if proxy_cfg:
            launch_args["proxy"] = proxy_cfg
            profile["proxy"] = proxy_cfg.get("server", "")

        browser = None
        try:
            try:
                browser = await pw.chromium.launch(**launch_args)
            except Exception as e:
                if "headless_shell" in str(e) and headless:
                    launch_args["headless"] = False
                    launch_args["args"].insert(0, "--headless")
                    browser = await pw.chromium.launch(**launch_args)
                else:
                    raise

            ctx_opts = {
                "user_agent": nav.get("userAgent", ""),
                "viewport": {"width": viewport["width"], "height": viewport["height"]},
                "locale": "ru-RU",
                "timezone_id": fp.get("timezone", {}).get("id", "Europe/Moscow"),
                "is_mobile": False,
                "has_touch": False,
                "device_scale_factor": viewport.get("dpr", 1.0), # Десктопный масштаб
            }

            geo = fp.get("geolocation")
            if geo:
                ctx_opts["geolocation"] = {
                    "latitude": geo["latitude"],
                    "longitude": geo["longitude"],
                }
                ctx_opts["permissions"] = ["geolocation"]

            context = await browser.new_context(**ctx_opts)
            await context.add_init_script(build_stealth_js(profile))

            page = await context.new_page()
            human.set_mouse_config(profile.get("mouse_config"))

            # --- Step 1: ya.ru ---
            logger.info(f"[{short}] Opening ya.ru")
            await page.goto("https://ya.ru", wait_until="domcontentloaded", timeout=30000)
            await human.pause(2.0, 4.0)

            if await _has_captcha(page):
                logger.warning(f"[{short}] Captcha on ya.ru — collecting partial cookies")
                got_captcha = True
                await _record_captcha()
            else:
                # --- Step 2: search ---
                query = random.choice(SEARCH_QUERIES)
                logger.info(f"[{short}] Searching: {query}")
                await _do_search(page, query)

                # --- Step 3: visit Yandex services ---
                sites = random.sample(FARM_SITES, random.randint(2, 4))
                for url in sites:
                    logger.debug(f"[{short}] Visiting {url}")
                    await _visit_site(page, url)
                    if await _has_captcha(page):
                        got_captcha = True
                        await _record_captcha()
                        break

            # --- Step 4: always collect whatever we got ---
            cookies = await context.cookies()

            localstorage = {}
            if not got_captcha:
                try:
                    await page.goto(
                        "https://yandex.ru",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    await human.pause(1.0, 2.0)
                    localstorage = await _collect_localstorage(page)
                except Exception as e:
                    logger.debug(f"[{short}] localStorage collection failed: {e}")

            profile["cookies"] = cookies
            profile["localstorage"] = localstorage
            profile["warm"] = len(cookies) >= 10 and not got_captcha
            if got_captcha:
                profile["partial"] = True
            profile.pop("error", None)

            label = "WARM" if profile["warm"] else f"PARTIAL({len(cookies)} cookies)"
            logger.info(f"[{short}] {label}: {len(cookies)} cookies, {len(localstorage)} ls")

        except Exception as e:
            logger.error(f"[{short}] Farm error: {e}", exc_info=True)
            profile["cookies"] = []
            profile["localstorage"] = {}
            profile["warm"] = False
            profile["error"] = str(e)

        finally:
            if browser:
                await browser.close()

    return profile
