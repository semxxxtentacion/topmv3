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
    # Нативные текстовые селекторы Playwright (Самые надежные для десктопа)
    'a:has-text("Дальше")',
    'a:has-text("Следующая страница")',
    'button:has-text("Показать ещё")',
    'div[role="button"]:has-text("Дальше")',
    
    # Классические CSS-селекторы десктопа
    '.pager__item_kind_next',
    '.pager__item_type_next',
    'a[aria-label="Следующая страница"]',
    'a.Pager-Item_type_next',
    '[data-log-node="next"]',
    
    # Мобильные селекторы (на всякий случай)
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
    """Send a JSON POST to CapMonster Cloud and return parsed response."""
    import urllib.request
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=30))
    return json.loads(resp.read().decode())


async def _extract_sitekey(page) -> str | None:
    """Extract Yandex SmartCaptcha sitekey from the captcha page.

    The sitekey can live in:
      1. data-sitekey attribute on a container div
      2. iframe src URL from captcha-api.yandex.ru / smartcaptcha.yandexcloud.net
      3. <script src="...?sitekey=...">
      4. inline JS variable / config object
      5. Playwright child frame URLs
    """
    await asyncio.sleep(1.5)

    sitekey = await page.evaluate('''() => {
        // 1. data-sitekey on any element
        const el = document.querySelector('[data-sitekey]');
        if (el) return el.getAttribute('data-sitekey');

        // 2. iframes whose src contains sitekey param
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            const src = f.src || f.getAttribute('src') || '';
            const m = src.match(/sitekey=([^&]+)/);
            if (m) return m[1];
        }

        // 3. script tags (external) with sitekey in src
        const scripts = document.querySelectorAll('script[src]');
        for (const s of scripts) {
            const m = s.src.match(/sitekey=([^&]+)/);
            if (m) return m[1];
        }

        // 4. inline scripts — look for sitekey assignment
        const inlines = document.querySelectorAll('script:not([src])');
        for (const s of inlines) {
            const t = s.textContent || '';
            const m = t.match(/sitekey["']?\\s*[:=]\\s*["']([^"']+)["']/);
            if (m) return m[1];
        }

        // 5. raw HTML fallback patterns
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
    }''')

    if sitekey:
        return sitekey

    import re
    for frame in page.frames:
        try:
            url = frame.url
            if 'captcha-api.yandex' in url or 'smartcaptcha.yandexcloud' in url:
                m = re.search(r'sitekey=([^&]+)', url)
                if m:
                    logger.info(f"Sitekey extracted from child frame URL: {url[:120]}")
                    return m[1]
        except Exception:
            continue

    return None


async def _dump_captcha_debug(page):
    """Log page structure to help diagnose sitekey extraction failures."""
    try:
        info = await page.evaluate('''() => {
            const iframes = [...document.querySelectorAll('iframe')].map(f => f.src || '').filter(Boolean);
            const scripts = [...document.querySelectorAll('script[src]')].map(s => s.src).filter(Boolean);
            const captchaDivs = [...document.querySelectorAll('[class*="aptcha"], [class*="smart-captcha"], [id*="captcha"]')]
                .map(el => ({ tag: el.tagName, id: el.id, cls: el.className, attrs: [...el.attributes].map(a => a.name + '=' + a.value.slice(0, 60)) }));
            const htmlSnippet = document.documentElement.innerHTML.slice(0, 3000);
            return { iframes, scripts, captchaDivs, htmlSnippet };
        }''')
        logger.debug(f"Captcha page iframes: {info.get('iframes', [])}")
        logger.debug(f"Captcha page scripts: {info.get('scripts', [])}")
        logger.debug(f"Captcha page captcha divs: {info.get('captchaDivs', [])}")
        frame_urls = [f.url for f in page.frames if f.url != page.url]
        logger.debug(f"Playwright frames: {frame_urls}")
        logger.info(f"Captcha page HTML snippet (first 500 chars): {info.get('htmlSnippet', '')[:500]}")
    except Exception as e:
        logger.debug(f"Captcha debug dump failed: {e}")


async def _solve_with_capmonster(page) -> bool:
    """Solve Yandex SmartCaptcha via CapMonster Cloud API."""
    if not CAPMONSTER_API_KEY:
        logger.warning("CAPMONSTER_API_KEY not set, skipping API solve")
        return False

    page_url = page.url
    sitekey = await _extract_sitekey(page)

    if not sitekey:
        logger.warning(f"Could not extract sitekey from captcha page: {page_url}")
        await _dump_captcha_debug(page)
        return False

    logger.info(f"CapMonster: submitting task (sitekey={sitekey[:20]}...)")

    try:
        create_resp = await _capmonster_request(CAPMONSTER_CREATE, {
            'clientKey': CAPMONSTER_API_KEY,
            'task': {
                'type': 'YandexSmartCaptchaTaskProxyless',
                'websiteURL': page_url,
                'websiteKey': sitekey,
            }
        })
    except Exception as e:
        logger.error(f"CapMonster createTask failed: {e}")
        return False

    if create_resp.get('errorId', 1) != 0:
        logger.error(f"CapMonster createTask error: {create_resp}")
        return False

    task_id = create_resp.get('taskId')
    if not task_id:
        logger.error(f"CapMonster: no taskId in response: {create_resp}")
        return False

    logger.info(f"CapMonster: taskId={task_id}, polling for result...")

    elapsed = 0
    while elapsed < CAPMONSTER_TIMEOUT:
        await asyncio.sleep(CAPMONSTER_POLL_INTERVAL)
        elapsed += CAPMONSTER_POLL_INTERVAL

        try:
            result = await _capmonster_request(CAPMONSTER_RESULT, {
                'clientKey': CAPMONSTER_API_KEY,
                'taskId': task_id,
            })
        except Exception as e:
            logger.debug(f"CapMonster getTaskResult error: {e}")
            continue

        status = result.get('status')
        if status == 'ready':
            token = result.get('solution', {}).get('token')
            if not token:
                logger.error(f"CapMonster: no token in solution: {result}")
                return False
            logger.info(f"CapMonster: solved! token={token[:30]}...")
            return await _inject_captcha_token(page, token)

        if result.get('errorId', 0) != 0:
            logger.error(f"CapMonster solve error: {result}")
            return False

    logger.warning(f"CapMonster: timed out after {CAPMONSTER_TIMEOUT}s")
    return False


async def _inject_captcha_token(page, token: str) -> bool:
    """Inject the solved captcha token and submit the form."""
    try:
        submitted = await page.evaluate('''(token) => {
            // Try setting smart-token input and submitting form
            const inp = document.querySelector('input[name="smart-token"]');
            if (inp) {
                inp.value = token;
                const form = inp.closest('form');
                if (form) { form.submit(); return "form"; }
            }
            // Try calling the captcha callback directly
            if (window.smartCaptcha && window.smartCaptcha.execute) {
                window.smartCaptcha.execute(token);
                return "callback";
            }
            // Fallback: find any form with captcha action
            const forms = document.querySelectorAll('form[action*="captcha"]');
            for (const f of forms) {
                let ti = f.querySelector('input[name="smart-token"]');
                if (!ti) {
                    ti = document.createElement('input');
                    ti.type = 'hidden';
                    ti.name = 'smart-token';
                    f.appendChild(ti);
                }
                ti.value = token;
                f.submit();
                return "fallback-form";
            }
            return null;
        }''', token)

        if submitted:
            logger.info(f"Captcha token injected via: {submitted}")
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
            except Exception:
                pass
            await human.pause(1.0, 2.0)
            captcha = await _detect_captcha(page)
            if not captcha:
                logger.info("Captcha solved via CapMonster!")
                return True
            logger.warning("Captcha still present after token injection")
            return False

        logger.warning("Could not find captcha form to inject token")
        return False
    except Exception as e:
        logger.error(f"Token injection failed: {e}")
        return False


CHECKBOX_CAPTCHA_BUTTON_SELECTORS = [
    '.CheckboxCaptcha-Button',
    '.CheckboxCaptcha-Anchor',
    '.CheckboxCaptcha button',
    'button[data-testid="checkbox-captcha"]',
    '.AdvancedCaptcha-SilentButton',
]


async def _try_solve_captcha(page) -> bool:
    """Solve captcha: try CapMonster Cloud first, then fall back to clicking."""
    # 1) Try CapMonster Cloud API
    if CAPMONSTER_API_KEY:
        if await _solve_with_capmonster(page):
            return True
        logger.info("CapMonster failed, falling back to click method")

    # 2) Fallback: click the checkbox
    for attempt in range(CAPTCHA_MAX_ATTEMPTS):
        logger.info(f"Click-solve attempt {attempt + 1}/{CAPTCHA_MAX_ATTEMPTS}")
        await human.pause(1.0, 2.5)

        clicked = False
        for sel in CHECKBOX_CAPTCHA_BUTTON_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    logger.info(f"Found captcha button: {sel}")
                    await human.pause(0.5, 1.5)
                    await human.click_element(page, el)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            try:
                checkbox = await page.query_selector('.CheckboxCaptcha')
                if checkbox:
                    await human.click_element(page, checkbox)
                    clicked = True
            except Exception:
                pass

        if not clicked:
            logger.warning("No captcha button found to click")
            return False

        await human.pause(2.0, 4.0)
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=8000)
        except Exception:
            pass
        await human.pause(1.0, 2.0)

        captcha_sel = await _detect_captcha(page)
        if not captcha_sel:
            logger.info("Captcha solved via click!")
            return True

        if captcha_sel in ('.AdvancedCaptcha', '.SmartCaptcha', '.captcha__image'):
            logger.warning(f"Escalated to complex captcha ({captcha_sel}), cannot solve")
            return False

    logger.warning("Failed to solve captcha after all attempts")
    return False


async def _find_search_input(page):
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el:
                return sel
        except Exception:
            continue
    return None


async def _focus_input(page, selector: str):
    """Focus and clear the search input via JS — bypasses overlay interception."""
    await page.evaluate('''(sel) => {
        const el = document.querySelector(sel);
        if (el) {
            el.focus();
            el.value = "";
            el.dispatchEvent(new Event("input", { bubbles: true }));
        }
    }''', selector)


async def _ensure_no_overlay(page, max_attempts: int = 3):
    """Remove DistributionPopupOverlay and verify it's gone."""
    for attempt in range(max_attempts):
        await _inject_overlay_killer(page)
        await _dismiss_dialogs(page)
        still_blocking = await page.evaluate('''() => {
            const overlay = document.querySelector(
                '.DistributionPopupOverlay, [class*="DistributionPopup"], '
                + '[class*="DistributionFullscreen"], [class*="distribution"]'
            );
            if (!overlay) return false;
            const style = getComputedStyle(overlay);
            return style.display !== "none" && style.visibility !== "hidden";
        }''')
        if not still_blocking:
            return
        logger.warning(f"Overlay still present after attempt {attempt + 1}, retrying...")
        await asyncio.sleep(0.5)
    logger.warning("Could not remove overlay after all attempts, proceeding anyway")


# ---------------------------------------------------------------------------
# Step 1 – Open Yandex
# ---------------------------------------------------------------------------

async def _inject_overlay_killer(page):
    """Inject persistent CSS + MutationObserver to neutralise Yandex promo overlays."""
    try:
        await page.evaluate('''() => {
            if (window.__overlayKillerInstalled) return 0;
            window.__overlayKillerInstalled = true;

            const style = document.createElement("style");
            style.textContent = `
                [class*="Distribution"], [class*="distribution"],
                .DistributionPopupOverlay, .DistributionFullscreen,
                [role="dialog"], .modal-overlay {
                    display: none !important;
                    visibility: hidden !important;
                    pointer-events: none !important;
                    opacity: 0 !important;
                    z-index: -9999 !important;
                    width: 0 !important;
                    height: 0 !important;
                    position: fixed !important;
                    top: -9999px !important;
                }
            `;
            document.head.appendChild(style);

            const nuke = () => {
                document.querySelectorAll(
                    '[class*="Distribution"], [class*="distribution"], [role="dialog"], .modal-overlay'
                ).forEach(el => { el.remove(); });
            };
            nuke();

            const obs = new MutationObserver(nuke);
            obs.observe(document.body || document.documentElement, {
                childList: true, subtree: true
            });
            return 1;
        }''')
    except Exception as e:
        logger.debug(f"Overlay killer injection failed: {e}")


async def _dismiss_dialogs(page):
    """Close Yandex promo dialogs/overlays that block the search input."""
    await _inject_overlay_killer(page)
    try:
        removed = await page.evaluate('''() => {
            let count = 0;
            const selectors = [
                '[class*="Distribution"]',
                '[class*="distribution"]',
                '[role="dialog"]',
                '.modal-overlay',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => { el.remove(); count++; });
            }
            return count;
        }''')
        if removed:
            logger.info(f"Dismissed {removed} dialog/overlay elements")
    except Exception as e:
        logger.debug(f"Dialog dismiss failed: {e}")


async def open_yandex(page):
    await human.pause(1.0, 3.0)

    await page.goto(YANDEX_HOME, wait_until='domcontentloaded')
    await human.pause(2.0, 4.0)

    await _ensure_no_overlay(page)
    await human.pause(0.5, 1.5)

    captcha_sel = await _detect_captcha(page)
    if captcha_sel:
        logger.info("Captcha on main page, attempting to solve...")
        if not await _try_solve_captcha(page):
            raise RuntimeError('Captcha detected on Yandex main page — could not solve')
        await _ensure_no_overlay(page)


# ---------------------------------------------------------------------------
# Step 2 – Enter search query
# ---------------------------------------------------------------------------

async def search(page, query: str):
    await _ensure_no_overlay(page)

    input_sel = await _find_search_input(page)
    if not input_sel:
        raise RuntimeError('Cannot find Yandex search input')

    await _ensure_no_overlay(page)
    await human.idle_mouse(page, random.uniform(0.5, 1.5))

    await _focus_input(page, input_sel)
    await human.pause(0.3, 0.7)
    await human.type_text_keyboard(page, query)
    await human.pause(0.8, 2.0)

    await page.keyboard.press('Enter')
    await page.wait_for_load_state('domcontentloaded')
    await human.pause(2.0, 4.0)

    captcha_sel = await _detect_captcha(page)
    if captcha_sel:
        logger.info("Captcha on search results, attempting to solve...")
        if not await _try_solve_captcha(page):
            raise RuntimeError('Captcha detected on search results — could not solve')
        await human.pause(1.0, 2.0)


# ---------------------------------------------------------------------------
# Step 3 – Scan SERP for target domain
# ---------------------------------------------------------------------------

async def _find_target_link(page, target_domain: str):
    """Return the first ElementHandle whose href contains target_domain."""
    link_elements = await page.query_selector_all(
        '.serp-item a[href], [data-cid] a[href], .Organic a[href], '
        '.OrganicM a[href], .serp-item__greenurl a[href]'
    )
    for link in link_elements:
        href = await link.get_attribute('href')
        if not href:
            continue
        try:
            hostname = urlparse(href).hostname or ''
            if target_domain in hostname.replace('www.', ''):
                visible = await link.is_visible()
                if visible:
                    return link
        except Exception:
            continue
    return None


async def _simulate_serp_reading(page):
    """Scroll through SERP like a human reading results.

    On mobile SERP, results are in a long list — we need to scroll
    through the entire page to load all visible results and see them.
    """
    if random.random() < 0.5:
        await human.idle_mouse(page, random.uniform(0.5, 2.0))

    for _ in range(random.randint(4, 8)):
        await human.scroll(page, 'down', random.randint(300, 700))
        await human.pause(0.8, 2.5)
        if random.random() < 0.3:
            await human.idle_mouse(page, random.uniform(0.3, 1.0))

    if random.random() < 0.4:
        await human.scroll(page, 'up', random.randint(80, 300))
        await human.pause(0.5, 1.2)


async def _go_next_serp_page(page) -> bool:
    """Load more SERP results: click 'More' button or navigate to next page."""
    results_before = len(await page.query_selector_all(SERP_RESULT_SELECTORS))
    url_before = page.url

    # Try clicking a "next page" / "show more" button
    for sel in NEXT_PAGE_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.scroll_into_view_if_needed()
                await human.pause(0.4, 0.9)
                await human.click_element(page, el)
                try:
                    # Ждем загрузки новой страницы или подгрузки DOM
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception:
                    pass
                await human.pause(2.0, 4.0)
                
                results_after = len(await page.query_selector_all(SERP_RESULT_SELECTORS))
                url_after = page.url
                
                # Успех: если подгрузилось вниз (results > before) ИЛИ страница сменила URL (p=1 -> p=2)
                if results_after > results_before or url_after != url_before:
                    logger.info(f"Loaded next page via button. URL changed: {url_before != url_after}")
                    return True
        except Exception:
            continue

    # Fallback: scroll to bottom to trigger infinite scroll
    logger.info("No pagination button found, trying scroll to load more...")
    for _ in range(6):
        await human.scroll(page, 'down', random.randint(600, 1200))
        await human.pause(0.5, 1.0)

    await human.pause(2.0, 3.0)

    results_after = len(await page.query_selector_all(SERP_RESULT_SELECTORS))
    if results_after > results_before:
        logger.info(f"Infinite scroll loaded: {results_before} → {results_after}")
        return True

    # Last resort: JS clicker with the word "дальше"
    try:
        more_btn = await page.evaluate('''() => {
            const btns = [...document.querySelectorAll('button, a, div[role="button"]')];
            const more = btns.find(b => {
                const t = (b.textContent || '').trim().toLowerCase();
                return t === 'дальше' || t === 'ещё' || t === 'показать ещё' 
                    || t === 'больше результатов' || t === 'следующая страница';
            });
            if (more) { more.click(); return true; }
            return false;
        }''')
        if more_btn:
            await human.pause(3.0, 5.0)
            url_after_js = page.url
            results_final = len(await page.query_selector_all(SERP_RESULT_SELECTORS))
            if results_final > results_before or url_after_js != url_before:
                logger.info("Text-based button click worked (Next page loaded).")
                return True
    except Exception:
        pass

    logger.warning(f"Cannot load more SERP results (stuck at {results_before} items)")
    return False


# ---------------------------------------------------------------------------
# Step 4 – Browse target site
# ---------------------------------------------------------------------------

async def _get_internal_links(page):
    current_host = urlparse(page.url).hostname
    all_links = await page.query_selector_all('a[href]')
    internal = []
    for a in all_links:
        try:
            href = await a.get_attribute('href')
            if not href or href.startswith('#') or 'javascript:' in href:
                continue
            parsed = urlparse(href)
            link_host = parsed.hostname or current_host
            if link_host == current_host and await a.is_visible():
                internal.append(a)
        except Exception:
            continue
    return internal


async def browse_site(page):
    """Spend time on the target site: scroll, click internal links, read."""
    total_time = random.uniform(MIN_TIME_ON_SITE, MAX_TIME_ON_SITE)
    pages_to_visit = random.randint(MIN_PAGES_ON_SITE, MAX_PAGES_ON_SITE)
    time_per_page = total_time / pages_to_visit

    logger.info(f"Browsing: {pages_to_visit} pages, ~{total_time:.0f}s total")

    for pnum in range(pages_to_visit):
        t0 = asyncio.get_event_loop().time()

        for _ in range(random.randint(3, 7)):
            await human.scroll(page, 'down', random.randint(100, 400))
            await human.pause(1.0, 3.0)
            if random.random() < 0.35:
                await human.idle_mouse(page, random.uniform(0.5, 1.5))

        if random.random() < 0.45:
            await human.scroll(page, 'up', random.randint(150, 400))
            await human.pause(0.5, 1.5)

        elapsed = asyncio.get_event_loop().time() - t0
        remaining = time_per_page - elapsed
        if remaining > 0:
            wait = min(remaining, 8.0)
            await asyncio.sleep(wait)
            if remaining - wait > 1:
                await human.idle_mouse(page, min(remaining - wait, 10.0))

        if pnum < pages_to_visit - 1:
            internal = await _get_internal_links(page)
            if internal:
                chosen = random.choice(internal[:15])
                try:
                    await chosen.scroll_into_view_if_needed()
                    await human.pause(0.3, 0.7)
                    await human.click_element(page, chosen)
                    await page.wait_for_load_state('domcontentloaded')
                    await human.pause(1.0, 2.5)
                except Exception:
                    logger.debug("Failed to navigate to internal link, stopping browsing")
                    break
            else:
                break

    logger.info("Finished browsing target site")


# ---------------------------------------------------------------------------
# Full scenario
# ---------------------------------------------------------------------------

async def run(page, task: dict) -> dict:
    """
    Execute full Yandex scenario.

    task = {
        'site': 'example.com',
        'keyword': 'купить что-то',
        'region': '',            # optional
    }

    Returns dict with status, serp_page, etc.
    """
    site = (task['site']
            .replace('https://', '')
            .replace('http://', '')
            .replace('www.', '')
            .rstrip('/'))
    keyword = task['keyword']
    result = {'status': 'failed', 'site': site, 'keyword': keyword, 'serp_page': 0}

    try:
        logger.info(f"Scenario start: '{keyword}' → {site}")

        await open_yandex(page)
        await search(page, keyword)

        for serp_page in range(1, YANDEX_MAX_SERP_PAGES + 1):
            result['serp_page'] = serp_page
            logger.info(f"SERP page {serp_page}...")

            captcha_sel = await _detect_captcha(page)
            if captcha_sel:
                logger.info(f"Captcha on SERP page {serp_page}, attempting to solve...")
                if not await _try_solve_captcha(page):
                    result['status'] = 'captcha'
                    logger.warning("Captcha detected, could not solve, aborting")
                    return result
                logger.info("Captcha solved, continuing SERP scan")

            await _simulate_serp_reading(page)

            target_link = await _find_target_link(page, site)
            if target_link:
                logger.info(f"Found '{site}' on SERP page {serp_page}")

                await target_link.scroll_into_view_if_needed()
                await human.pause(0.3, 0.8)
                await human.click_element(page, target_link)

                await page.wait_for_load_state('domcontentloaded')
                await human.pause(1.5, 3.0)

                await browse_site(page)

                result['status'] = 'success'
                result['landed_url'] = page.url
                logger.info(f"Scenario OK: '{keyword}' → {site} (page {serp_page})")
                return result

            if serp_page < YANDEX_MAX_SERP_PAGES:
                if not await _go_next_serp_page(page):
                    logger.warning("No more SERP pages available")
                    result['status'] = 'not_found'
                    return result

        result['status'] = 'not_found'
        logger.warning(f"'{site}' not found in {YANDEX_MAX_SERP_PAGES} SERP pages for '{keyword}'")

    except RuntimeError as e:
        result['status'] = 'captcha' if 'captcha' in str(e).lower() else 'error'
        result['error'] = str(e)
        logger.error(f"Scenario runtime error: {e}")
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        logger.error(f"Scenario error: {e}", exc_info=True)

    return result
