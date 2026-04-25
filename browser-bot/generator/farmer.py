"""
Cookie farmer: launches real Chromium with a generated fingerprint,
visits Yandex services, collects cookies and localStorage.
"""

from __future__ import annotations

import asyncio
import random
import logging
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from generator.stealth import build_stealth_js
from generator import human
from generator.chrome_versions import get_chrome_versions

logger = logging.getLogger(__name__)

# Ваша ссылка для смены IP
CHANGE_IP_LINK = "https://changeip.mobileproxy.space/?proxy_key=d8432adacb8716438427ff7ddfacb28c"

# СЕМАФОР: Жесткое ограничение - создавать профили СТРОГО ПО ОДНОМУ
_browser_semaphore = asyncio.Semaphore(1)

_captcha_window: list[float] = []
_captcha_lock = asyncio.Lock()

CAPTCHA_COOLDOWN = 60
CAPTCHA_THRESHOLD = 3
CAPTCHA_WINDOW_SEC = 30

async def _captcha_backoff():
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

# --- ФУНКЦИЯ СМЕНЫ IP ---
async def _change_ip():
    logger.info("🔄 [Генератор] Отправляем команду на смену IP...")
    try:
        loop = asyncio.get_event_loop()
        def fetch():
            # Дергаем ссылку без внешних библиотек, чтобы не было ошибок
            req = urllib.request.Request(CHANGE_IP_LINK, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status
        
        status = await loop.run_in_executor(None, fetch)
        if status == 200:
            logger.info("✅ [Генератор] Команда принята. Ждем 12 секунд (смена IP)...")
        else:
            logger.warning(f"⚠️ [Генератор] Ошибка смены IP: код {status}")
    except Exception as e:
        logger.error(f"⚠️ [Генератор] Ошибка при смене IP: {e}")
    
    # Обязательная пауза на перезагрузку модема
    await asyncio.sleep(12)


FARM_SITES = [
    "https://yandex.ru/news", "https://yandex.ru/pogoda", "https://yandex.ru/images",
    "https://yandex.ru/video", "https://yandex.ru/maps", "https://yandex.ru/market",
    "https://yandex.ru/translate", "https://dzen.ru",
]

SEARCH_QUERIES = [
    "погода москва", "курс доллара", "новости сегодня", "рецепт борща",
    "расписание электричек", "афиша кино", "купить телефон", "авиабилеты дешево",
    "вакансии москва", "калькулятор онлайн", "гороскоп на сегодня", "рецепты на ужин",
    "смотреть фильмы онлайн", "погода на неделю", "карта метро москвы", "доставка еды",
    "расписание поездов", "онлайн переводчик", "сколько время", "пробки на дорогах",
    "скачать музыку", "новые фильмы 2025", "спорт новости", "рецепты пирогов",
    "где купить ноутбук", "как почистить компьютер",
]

SEARCH_INPUT_SELECTORS = [
    'input[name="text"]', 'textarea[name="text"]', '.mini-suggest__input',
    'input.input__control', '.search3__input input',
]

CAPTCHA_SELECTORS = ['.CheckboxCaptcha', '.AdvancedCaptcha', 'form[action*="captcha"]', '.SmartCaptcha']

def _is_mobile(profile: dict) -> bool:
    val = profile.get('ismobiledevice')
    if val is None: return False
    if isinstance(val, bool): return val
    if isinstance(val, list): return any(str(v).lower().strip() in ('true', 't', '1') for v in val)
    return str(val).lower().strip('{}[] ') in ('true', 't', '1')

def _build_client_hints(profile: dict) -> dict:
    platform = str(profile.get('platform', 'Windows'))
    is_mob = _is_mobile(profile)
    
    ch_platform = '"Windows"'
    if 'Android' in platform or is_mob: ch_platform = '"Android"'
    elif 'Mac' in platform: ch_platform = '"macOS"'
    elif 'Linux' in platform: ch_platform = '"Linux"'
        
    _versions = get_chrome_versions()
    _default_bv = _versions[0] if _versions else '120.0.0.0'
    bv = str(profile.get('browser_version', _default_bv))
    major_version = bv.split('.')[0]
    
    return {
        'sec-ch-ua': f'"Not_A Brand";v="8", "Chromium";v="{major_version}", "Google Chrome";v="{major_version}"',
        'sec-ch-ua-mobile': '?1' if is_mob else '?0',
        'sec-ch-ua-platform': ch_platform,
    }

async def _has_captcha(page) -> bool:
    if 'showcaptcha' in page.url or 'captcha' in page.url: return True
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.query_selector(sel): return True
        except Exception: continue
    return False

async def _find_search_input(page) -> str | None:
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el: return sel
        except Exception: continue
    return None

async def _do_search(page, query: str):
    input_sel = await _find_search_input(page)
    if not input_sel: return
    await human.click(page, input_sel)
    await human.pause(0.3, 0.7)
    await human.type_text(page, input_sel, query)
    await human.pause(0.5, 1.0)
    await page.keyboard.press("Enter")
    try: await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception: return
    await human.pause(2.0, 4.0)
    if await _has_captcha(page): return
    for _ in range(random.randint(2, 4)):
        await human.scroll(page, "down", random.randint(200, 500))
        await human.pause(1.0, 3.0)

async def _visit_site(page, url: str):
    try: await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception: return
    await human.pause(1.5, 3.0)
    if await _has_captcha(page): return
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
    except Exception: return {}

# --- ОСНОВНАЯ ФУНКЦИЯ СОЗДАНИЯ ПРОФИЛЯ ---
async def farm_one_profile(profile: dict, proxy_cfg: dict | None = None, headless: bool = True) -> dict:
    # Семафор гарантирует, что процессы не наложатся друг на друга
    async with _browser_semaphore:
        
        # 1. Меняем IP перед каждым профилем
        await _change_ip()
        
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
                    "--force-webrtc-ip-handling-policy=disable-non-proxied-udp"
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
                    else: raise

                ctx_opts = {
                    "user_agent": nav.get("userAgent", ""),
                    "viewport": {"width": viewport["width"], "height": viewport["height"]},
                    "locale": "ru-RU",
                    "timezone_id": fp.get("timezone", {}).get("id", "Europe/Moscow"),
                    "is_mobile": False,
                    "has_touch": False,
                    "device_scale_factor": viewport.get("dpr", 1.0),
                    "extra_http_headers": _build_client_hints(profile)
                }

                geo = fp.get("geolocation")
                if geo:
                    ctx_opts["geolocation"] = {"latitude": geo["latitude"], "longitude": geo["longitude"]}
                    ctx_opts["permissions"] = ["geolocation"]

                context = await browser.new_context(**ctx_opts)
                await context.add_init_script(build_stealth_js(profile))

                page = await context.new_page()
                human.set_mouse_config(profile.get("mouse_config"))

                logger.info(f"[{short}] Opening ya.ru")
                await page.goto("https://ya.ru", wait_until="domcontentloaded", timeout=30000)
                await human.pause(2.0, 4.0)

                if await _has_captcha(page):
                    logger.warning(f"[{short}] Captcha on ya.ru — collecting partial cookies")
                    got_captcha = True
                    await _record_captcha()
                else:
                    query = random.choice(SEARCH_QUERIES)
                    logger.info(f"[{short}] Searching: {query}")
                    await _do_search(page, query)

                    sites = random.sample(FARM_SITES, random.randint(2, 4))
                    for url in sites:
                        logger.debug(f"[{short}] Visiting {url}")
                        await _visit_site(page, url)
                        if await _has_captcha(page):
                            got_captcha = True
                            await _record_captcha()
                            break

                cookies = await context.cookies()
                localstorage = {}
                
                if not got_captcha:
                    try:
                        await page.goto("https://yandex.ru", wait_until="domcontentloaded", timeout=15000)
                        await human.pause(1.0, 2.0)
                        localstorage = await _collect_localstorage(page)
                    except Exception as e:
                        logger.debug(f"[{short}] localStorage collection failed: {e}")

                profile["cookies"] = cookies
                profile["localstorage"] = localstorage
                profile["warm"] = len(cookies) >= 10 and not got_captcha
                if got_captcha: profile["partial"] = True
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
                if browser: await browser.close()
                
                # 2. Охлаждаем систему, чтобы избежать падений Docker
                logger.info("⏳ [Генератор] Охлаждаем систему 5 секунд перед завершением...")
                await asyncio.sleep(5)

        return profile
