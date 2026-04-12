from __future__ import annotations

"""
Yandex search scenario: search query → find target site in SERP → click → browse.
"""

import asyncio
import random
import logging
import json
from urllib.parse import urlparse

import human
from config import (
    YANDEX_MAX_SERP_PAGES,
    MIN_TIME_ON_SITE, MAX_TIME_ON_SITE,
    MIN_PAGES_ON_SITE, MAX_PAGES_ON_SITE,
    CAPMONSTER_API_KEY,
)

# Интегрируем наш решатель капчи по картинкам
from solcap import solve_coordinate_captcha

logger = logging.getLogger(__name__)

CAPTCHA_MAX_ATTEMPTS = 3

YANDEX_HOME = 'https://ya.ru'

SEARCH_INPUT_SELECTORS = [
    'input[name="text"]',
    '#search-input',
    '.mini-suggest__input',
    '.search3__input input',
    'input.input__control',
    'textarea[name="text"]',
    '.search2__input input',
]

NEXT_PAGE_SELECTORS = [
    'a:has-text("Дальше")',
    'a:has-text("Следующая страница")',
    'button:has-text("Показать ещё")',
    'div[role="button"]:has-text("Дальше")',
    '.pager__item_kind_next',
    '.pager__item_type_next',
    'a[aria-label="Следующая страница"]',
    'a.Pager-Item_type_next',
    '[data-log-node="next"]',
    'button.SerpMore-Button',
    '.SerpMore-Button',
    'button[class*="More"]',
    'div.more button',
    'button.more__button',
]

SERP_RESULT_SELECTORS = '.serp-item, [data-cid], .Organic, .OrganicM'

CAPTCHA_SELECTORS = [
    '.CheckboxCaptcha',
    '.AdvancedCaptcha',
    'form[action*="captcha"]',
    '.captcha__image',
    '.SmartCaptcha',
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _detect_captcha(page) -> str | None:
    """Return matched selector if captcha found, else None."""
    for sel in CAPTCHA_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                logger.info(f"Captcha detected: {sel} | URL: {page.url}")
                return sel
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# CapMonster Cloud integration
# ---------------------------------------------------------------------------

CAPMONSTER_CREATE = 'https://api.capmonster.cloud/createTask'
CAPMONSTER_RESULT = 'https://api.capmonster.cloud/getTaskResult'
CAPMONSTER_POLL_INTERVAL = 3
CAPMONSTER_TIMEOUT = 120

async def _capmonster_request(url: str, payload: dict) -> dict:
    import urllib.request
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=30))
    return json.loads(resp.read().decode())

async def _extract_sitekey(page) -> str | None:
    await asyncio.sleep(1.5)
    sitekey = await page.evaluate("""() => {
        const el = document.querySelector('[data-sitekey]');
        if (el) return el.getAttribute('data-sitekey');
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            const src = f.src || f.getAttribute('src') || '';
            const m = src.match(/sitekey=([^&]+)/);
            if (m) return m[1];
        }
        const scripts = document.querySelectorAll('script[src]');
        for (const s of scripts) {
            const m = s.src.match(/sitekey=([^&]+)/);
            if (m) return m[1];
        }
        const inlines = document.querySelectorAll('script:not([src])');
        for (const s of inlines) {
            const t = s.textContent || '';
            const m = t.match(/sitekey["']?\\s*[:=]\\s*["']([^"']+)["']/);
            if (m) return m[1];
        }
        const html = document.documentElement.innerHTML;
        const patterns = [
            /["']sitekey["']\\s*:\\s*["']([^"']+)["']/,
            /data-sitekey=["']([^"']+)["']/,
            /sitekey=([A-Za-z0-9_-]{20,})/,
        ];
        for (const p of patterns) {
            const m = html.match(p);
            if (m) return m[1];
        }
        return null;
    }""")
    if sitekey: return sitekey

    import re
    for frame in page.frames:
        try:
            url = frame.url
            if 'captcha-api.yandex' in url or 'smartcaptcha.yandexcloud' in url:
                m = re.search(r'sitekey=([^&]+)', url)
                if m: return m[1]
        except Exception: continue
    return None

async def _dump_captcha_debug(page):
    try:
        info = await page.evaluate("""() => {
            const iframes = [...document.querySelectorAll('iframe')].map(f => f.src || '').filter(Boolean);
            const scripts = [...document.querySelectorAll('script[src]')].map(s => s.src).filter(Boolean);
            const captchaDivs = [...document.querySelectorAll('[class*="aptcha"], [class*="smart-captcha"], [id*="captcha"]')]
                .map(el => ({ tag: el.tagName, id: el.id, cls: el.className }));
            return { iframes, scripts, captchaDivs };
        }""")
        logger.debug(f"Captcha debug info: {info}")
    except Exception: pass

async def _solve_with_capmonster(page) -> bool:
    if not CAPMONSTER_API_KEY: return False
    page_url = page.url
    sitekey = await _extract_sitekey(page)
    if not sitekey: return False

    try:
        create_resp = await _capmonster_request(CAPMONSTER_CREATE, {
            'clientKey': CAPMONSTER_API_KEY,
            'task': {
                'type': 'YandexSmartCaptchaTaskProxyless',
                'websiteURL': page_url,
                'websiteKey': sitekey,
            }
        })
        task_id = create_resp.get('taskId')
        if not task_id: return False

        for _ in range(int(CAPMONSTER_TIMEOUT/CAPMONSTER_POLL_INTERVAL)):
            await asyncio.sleep(CAPMONSTER_POLL_INTERVAL)
            result = await _capmonster_request(CAPMONSTER_RESULT, {'clientKey': CAPMONSTER_API_KEY, 'taskId': task_id})
            if result.get('status') == 'ready':
                token = result.get('solution', {}).get('token')
                return await _inject_captcha_token(page, token)
    except Exception: return False
    return False

async def _inject_captcha_token(page, token: str) -> bool:
    try:
        submitted = await page.evaluate("""(token) => {
            const inp = document.querySelector('input[name="smart-token"]');
            if (inp) {
                inp.value = token;
                const form = inp.closest('form');
                if (form) { form.submit(); return "form"; }
            }
            return null;
        }""", token)
        if submitted:
            await asyncio.sleep(3)
            return not await _detect_captcha(page)
    except Exception: pass
    return False

CHECKBOX_CAPTCHA_BUTTON_SELECTORS = [
    '.CheckboxCaptcha-Button',
    '.CheckboxCaptcha-Anchor',
    '.CheckboxCaptcha button',
    'button[data-testid="checkbox-captcha"]',
    '.AdvancedCaptcha-SilentButton',
]

async def _try_solve_captcha(page) -> bool:
    """Solve captcha: try CapMonster, then click, then Solcap for complex images."""
    if CAPMONSTER_API_KEY:
        if await _solve_with_capmonster(page): return True

    for attempt in range(CAPTCHA_MAX_ATTEMPTS):
        logger.info(f"Click-solve attempt {attempt + 1}/{CAPTCHA_MAX_ATTEMPTS}")
        # Имитация активности
        await page.mouse.move(random.randint(100, 600), random.randint(100, 600))
        await human.pause(1.5, 3.0)

        iframe_loc = None
        if await page.locator("iframe[src*='captcha']").count() > 0:
            iframe_loc = page.frame_locator("iframe[src*='captcha']").first

        clicked = False
        # Клик по галочке (на странице или в iframe)
        if iframe_loc:
            try:
                checkbox = iframe_loc.locator(".SmartCaptcha-Checkbox, .CheckboxCaptcha-Button").first
                if await checkbox.count() > 0:
                    await checkbox.click(force=True)
                    clicked = True
            except: pass
        
        if not clicked:
            for sel in CHECKBOX_CAPTCHA_BUTTON_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await human.click_element(page, el)
                        clicked = True
                        break
                except: continue

        # Ждем появления картинок
        await human.pause(4.0, 6.0)
        captcha_sel = await _detect_captcha(page)
        if not captcha_sel and clicked: return True

        # SOLCAP ИНТЕГРАЦИЯ
        if captcha_sel or iframe_loc:
            logger.info("Escalated to complex captcha. Checking for images...")
            main_img = None
            submit_btn = None
            hint_img = None

            # Поиск картинок
            if iframe_loc and await iframe_loc.locator(".AdvancedCaptcha-Image").count() > 0:
                main_img = iframe_loc.locator(".AdvancedCaptcha-Image")
                hint_img = iframe_loc.locator(".AdvancedCaptcha-SilhouetteTask")
                submit_btn = iframe_loc.locator("button.AdvancedCaptcha-FormActionsItem")
            elif await page.locator(".AdvancedCaptcha-Image").count() > 0:
                main_img = page.locator(".AdvancedCaptcha-Image")
                hint_img = page.locator(".AdvancedCaptcha-SilhouetteTask")
                submit_btn = page.locator("button.AdvancedCaptcha-FormActionsItem")

            if main_img:
                logger.info("Images found! Solving via Solcap...")
                m_bytes = await main_img.first.screenshot()
                h_bytes = await hint_img.first.screenshot() if await hint_img.count() > 0 else m_bytes
                
                coords = await solve_coordinate_captcha(m_bytes, h_bytes, urlparse(page.url).netloc)
                if coords:
                    for p in coords:
                        await main_img.first.click(position={"x": float(p[0]), "y": float(p[1])}, force=True)
                        await asyncio.sleep(1)
                    await submit_btn.first.click(force=True)
                    await human.pause(4, 6)
                    if not await _detect_captcha(page): return True
    return False

# ---------------------------------------------------------------------------
# Search Steps
# ---------------------------------------------------------------------------

async def _find_search_input(page):
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el: return sel
        except Exception: continue
    return None

async def _focus_input(page, selector: str):
    await page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (el) { el.focus(); el.value = ""; el.dispatchEvent(new Event("input", { bubbles: true })); }
    }""", selector)

async def _ensure_no_overlay(page):
    await page.evaluate("""() => {
        const nuke = () => { document.querySelectorAll('[class*="Distribution"], [role="dialog"], .modal-overlay').forEach(el => el.remove()); };
        nuke();
        const obs = new MutationObserver(nuke);
        obs.observe(document.documentElement, { childList: true, subtree: true });
    }""")

async def open_yandex(page):
    await page.goto(YANDEX_HOME, wait_until='domcontentloaded')
    await human.pause(2, 4)
    await _ensure_no_overlay(page)
    if await _detect_captcha(page):
        if not await _try_solve_captcha(page): raise RuntimeError('Captcha fail on Home')

async def search(page, query: str):
    sel = await _find_search_input(page)
    if not sel: raise RuntimeError('No search input')
    await _focus_input(page, sel)
    await human.type_text_keyboard(page, query)
    await page.keyboard.press('Enter')
    await page.wait_for_load_state('domcontentloaded')
    await human.pause(3, 5)
    if await _detect_captcha(page):
        if not await _try_solve_captcha(page): raise RuntimeError('Captcha fail on SERP')

async def _find_target_link(page, site: str):
    links = await page.query_selector_all('.serp-item a[href], .Organic a[href]')
    for link in links:
        href = await link.get_attribute('href')
        if href and site in href:
            if await link.is_visible(): return link
    return None

async def run(page: Page, task: dict) -> dict:
    site = task['site'].replace('https://', '').replace('www.', '').rstrip('/')
    keyword = task['keyword']
    res = {'status': 'failed', 'site': site, 'keyword': keyword}

    try:
        await open_yandex(page)
        await search(page, keyword)

        for p_idx in range(1, YANDEX_MAX_SERP_PAGES + 1):
            logger.info(f"Scanning page {p_idx}...")
            if await _detect_captcha(page):
                await _try_solve_captcha(page)
            
            # Скролл
            for _ in range(random.randint(3, 6)):
                await human.scroll(page, 'down', random.randint(300, 600))
                await asyncio.sleep(1.5)

            link = await _find_target_link(page, site)
            if link:
                logger.info("Site found!")
                await link.scroll_into_view_if_needed()
                await human.click_element(page, link)
                await page.wait_for_load_state('domcontentloaded')
                
                # Поведенческие факторы на сайте
                for _ in range(random.randint(2, 4)):
                    await human.scroll(page, 'down', random.randint(200, 500))
                    await asyncio.sleep(random.randint(5, 15))
                
                res['status'] = 'success'
                return res

            # Переход на след. страницу
            next_btn = await page.query_selector('.pager__item_kind_next')
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(5)
            else: break
            
    except Exception as e:
        res['error'] = str(e)
        logger.error(f"Run error: {e}")
    return res
