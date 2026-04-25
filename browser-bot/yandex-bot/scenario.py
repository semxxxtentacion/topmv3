from __future__ import annotations

import asyncio
import random
import json
import sys
from urllib.parse import urlparse

import human
from config import (
    YANDEX_MAX_SERP_PAGES,
    MIN_TIME_ON_SITE, MAX_TIME_ON_SITE,
    MIN_PAGES_ON_SITE, MAX_PAGES_ON_SITE,
    CAPMONSTER_API_KEY,
)

from solcap import solve_coordinate_captcha

CAPTCHA_MAX_ATTEMPTS = 3
YANDEX_HOME = 'https://ya.ru'

SEARCH_INPUT_SELECTORS = [
    'input[name="text"]', '#search-input', '.mini-suggest__input',
    '.search3__input input', 'input.input__control', 'textarea[name="text"]',
    '.search2__input input',
]

CAPTCHA_SELECTORS = [
    '.CheckboxCaptcha', '.AdvancedCaptcha', '.SmartCaptcha', '#captcha-page'
]

def force_log(msg: str):
    print(msg, flush=True)

async def _detect_captcha(page) -> bool:
    if 'showcaptcha' in page.url: 
        return True
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.locator(sel).count() > 0: 
                return True
        except: pass
    return False

CHECKBOX_CAPTCHA_BUTTON_SELECTORS = [
    '.CheckboxCaptcha-Button', '.CheckboxCaptcha-Anchor',
    'button[data-testid="checkbox-captcha"]', '.AdvancedCaptcha-SilentButton',
    '.smart-captcha-checkbox',
]

async def _try_solve_captcha(page) -> bool:
    force_log(f"⚠️ НАЧИНАЕМ РЕШАТЬ КАПЧУ НА URL: {page.url}")
    
    # Селекторы картинок Яндекса
    image_selectors = "img[src*='captchaimage'], img.AdvancedCaptcha-Image, img.captcha__image"

    for attempt in range(CAPTCHA_MAX_ATTEMPTS):
        force_log(f"⏳ Попытка {attempt + 1}/{CAPTCHA_MAX_ATTEMPTS}...")
        await page.mouse.move(random.randint(100, 600), random.randint(100, 600))
        await human.pause(1.5, 3.0)

        iframe_loc = None
        if await page.locator("iframe[src*='captcha']").count() > 0:
            iframe_loc = page.frame_locator("iframe[src*='captcha']").first

        # 1. ПРОВЕРКА: Есть ли уже картинки на странице? (Защита от зацикливания)
        has_images = False
        try:
            if iframe_loc:
                if await iframe_loc.locator(image_selectors).count() > 0: has_images = True
            else:
                if await page.locator(image_selectors).count() > 0: has_images = True
        except: pass

        # 2. ЕСЛИ КАРТИНОК НЕТ - жмем галочку
        if not has_images:
            clicked = False
            if iframe_loc:
                try:
                    checkbox = iframe_loc.locator(".SmartCaptcha-Checkbox, .CheckboxCaptcha-Button").first
                    if await checkbox.count() > 0 and await checkbox.is_visible():
                        force_log("🖱️ Кликаем по галочке внутри iframe...")
                        await checkbox.click(force=True)
                        clicked = True
                except: pass
            
            if not clicked:
                for sel in CHECKBOX_CAPTCHA_BUTTON_SELECTORS:
                    try:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            force_log(f"🖱️ Кликаем по галочке на странице: {sel}")
                            await human.click_element(page, el)
                            clicked = True
                            break
                    except: continue

            if clicked:
                force_log("⏳ Ждем загрузки картинок от Яндекса (до 8 секунд)...")
                # УМНОЕ ОЖИДАНИЕ: Playwright будет активно ждать появления картинок
                try:
                    if iframe_loc:
                        await iframe_loc.locator(image_selectors).first.wait_for(state="attached", timeout=8000)
                    else:
                        await page.locator(image_selectors).first.wait_for(state="attached", timeout=8000)
                    force_log("✅ Картинки появились!")
                except:
                    pass # Картинки не появились, возможно Яндекс пропустил нас без них

        # Проверяем, пропустил ли нас Яндекс без картинок
        await human.pause(1.0, 2.0)
        if not await _detect_captcha(page): 
            force_log("✅ Капча пройдена галочкой! Идем дальше.")
            return True

        # 3. ИЩЕМ И ОТПРАВЛЯЕМ КАРТИНКИ В SOLCAP
        force_log("🖼️ Капча просит картинки! Ищем элементы для Solcap...")
        main_img = None
        submit_btn = None
        hint_img = None

        if iframe_loc and await iframe_loc.locator("img[src*='captchaimage']").count() > 0:
            main_img = iframe_loc.locator("img[src*='captchaimage']:not(.TaskImage)").first
            if await main_img.count() == 0:
                main_img = iframe_loc.locator("img[src*='captchaimage']").first
            hint_img = iframe_loc.locator("img.TaskImage").first
            submit_btn = iframe_loc.locator("button:has-text('Отправить'), .CaptchaButton_view_action").first
        
        elif await page.locator("img[src*='captchaimage']").count() > 0:
            main_img = page.locator("img[src*='captchaimage']:not(.TaskImage)").first
            if await main_img.count() == 0:
                main_img = page.locator("img[src*='captchaimage']").first
            hint_img = page.locator("img.TaskImage").first
            submit_btn = page.locator("button:has-text('Отправить'), .CaptchaButton_view_action").first

        if main_img and await main_img.count() > 0:
            force_log("🧠 Картинки найдены! Отправляем в Solcap...")
            try:
                m_bytes = await main_img.screenshot(timeout=5000)
                h_bytes = await hint_img.screenshot(timeout=5000) if hint_img and await hint_img.count() > 0 else m_bytes
                
                coords = await solve_coordinate_captcha(m_bytes, h_bytes, urlparse(page.url).netloc)
                if coords:
                    force_log(f"🎯 Solcap вернул координаты: {coords}")
                    for p in coords:
                        await main_img.click(position={"x": float(p[0]), "y": float(p[1])}, force=True)
                        await asyncio.sleep(1)
                    
                    if submit_btn and await submit_btn.count() > 0:
                        force_log("🖱️ Кликаем 'Отправить'...")
                        await submit_btn.click(force=True)
                    
                    force_log("⏳ Ждем решения Яндекса...")
                    for _ in range(10):
                        await asyncio.sleep(1)
                        if not await _detect_captcha(page):
                            force_log("✅ Капча успешно пройдена через Solcap!")
                            return True
                    
                    force_log("⚠️ Яндекс не принял картинку, пробуем еще раз...")
                else:
                    force_log("❌ Solcap не смог решить картинку.")
            except Exception as e:
                force_log(f"❌ Ошибка при работе с картинкой: {e}")
        else:
            force_log("❌ Элементы картинок не найдены на странице!")

    force_log("❌ Исчерпаны все 3 попытки решения капчи.")
    return False

async def _find_search_input(page):
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el: return sel
        except: continue
    return None

async def _focus_input(page, selector: str):
    await page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (el) { el.focus(); el.value = ""; el.dispatchEvent(new Event("input", { bubbles: true })); }
    }""", selector)

async def open_yandex(page):
    try:
        await page.goto(YANDEX_HOME, wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        if "ERR_" in str(e) and "ERR_TIMED_OUT" not in str(e):
            raise RuntimeError(f"Proxy Connection Error: {e}")
    if "blank" in page.url: raise RuntimeError("Page loaded as about:blank.")
    await human.pause(2, 4)
    if await _detect_captcha(page):
        if not await _try_solve_captcha(page): raise RuntimeError('Captcha fail on Home')

async def search(page, query: str):
    sel = await _find_search_input(page)
    if not sel: raise RuntimeError(f"No search input. Current URL: {page.url}")
    await _focus_input(page, sel)
    await human.type_text_keyboard(page, query)
    await page.keyboard.press('Enter')
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=60000)
    except: pass
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

async def run(page, task: dict) -> dict:
    site = task['site'].replace('https://', '').replace('www.', '').rstrip('/')
    keyword = task['keyword']
    res = {'status': 'failed', 'site': site, 'keyword': keyword}
    try:
        await open_yandex(page)
        await search(page, keyword)
        for p_idx in range(1, YANDEX_MAX_SERP_PAGES + 1):
            force_log(f"📖 Ищем сайт на странице {p_idx}...")
            if await _detect_captcha(page):
                await _try_solve_captcha(page)
            for _ in range(random.randint(3, 6)):
                await human.scroll(page, 'down', random.randint(300, 600))
                await asyncio.sleep(1.5)
            link = await _find_target_link(page, site)
            if link:
                force_log("🔥 САЙТ НАЙДЕН! Переходим...")
                await link.scroll_into_view_if_needed()
                await human.click_element(page, link)
                try: await page.wait_for_load_state('domcontentloaded', timeout=45000)
                except: pass
                for _ in range(random.randint(2, 4)):
                    await human.scroll(page, 'down', random.randint(200, 500))
                    await asyncio.sleep(random.randint(5, 15))
                res['status'] = 'success'
                return res
            next_btn = await page.query_selector('.pager__item_kind_next')
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(5)
            else: break
    except Exception as e:
        res['error'] = str(e)
        force_log(f"❌ Run error: {e}")
    return res
