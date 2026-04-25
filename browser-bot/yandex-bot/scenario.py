from __future__ import annotations

import asyncio
import random
import os
import aiohttp
import logging
from urllib.parse import urlparse

import human
from config import (
    YANDEX_MAX_SERP_PAGES,
    MIN_TIME_ON_SITE, MAX_TIME_ON_SITE,
    MIN_PAGES_ON_SITE, MAX_PAGES_ON_SITE,
)

logger = logging.getLogger(__name__)
CAPTCHA_MAX_ATTEMPTS = 3
YANDEX_HOME = 'https://ya.ru'

# Селекторы для поиска полей ввода и капчи
SEARCH_INPUT_SELECTORS = [
    'input[name="text"]', '#search-input', '.mini-suggest__input',
    '.search3__input input', 'input.input__control', 'textarea[name="text"]',
    '.search2__input input',
]

CAPTCHA_SELECTORS = [
    '.CheckboxCaptcha', '.AdvancedCaptcha', '.SmartCaptcha', '#captcha-page', '[data-sitekey]'
]

def force_log(msg: str):
    """Принудительный вывод в консоль Docker логов"""
    print(msg, flush=True)

async def _detect_captcha(page) -> bool:
    """Проверка наличия капчи на странице"""
    if 'showcaptcha' in page.url: 
        return True
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.locator(sel).count() > 0: 
                return True
        except: pass
    return False

async def _try_solve_captcha(page) -> bool:
    """Логика обработки капчи: от простого клика до внешнего решателя"""
    force_log(f"⚠️ ОБНАРУЖЕНА КАПЧА: {page.url}")
    
    # 1. Пробуем кликнуть по галочке "Я не робот" как человек
    try:
        checkbox = await page.query_selector('.CheckboxCaptcha-Button, #js-button')
        if checkbox and await checkbox.is_visible():
            force_log("💡 Найдена галочка Яндекса. Имитируем движение мыши и клик...")
            await human.pause(1, 2)
            
            # Используем human-модуль для обхода простых детекторов
            await human.click_element(page, checkbox)
            
            try:
                await page.wait_for_load_state('networkidle', timeout=7000)
            except:
                pass
                
            await human.pause(2, 3)
            
            if not await _detect_captcha(page):
                force_log("✅ Яндекс пропустил после человечного клика!")
                return True
            else:
                force_log("⚠️ Клик не помог. Возможно, Яндекс требует решения SmartCaptcha...")
                # Сохраняем скриншот для диагностики
                await page.screenshot(path="captcha_debug.png")
    except Exception as e:
        force_log(f"⚠️ Ошибка при попытке авто-клика: {e}")

    # 2. Обращаемся к внешнему решателю (captcha-solver)
    solver_url = os.getenv("CAPTCHA_SOLVER_URL", "http://captcha-solver:8080")
    
    for attempt in range(CAPTCHA_MAX_ATTEMPTS):
        force_log(f"⏳ Попытка решения через RuCaptcha {attempt + 1}/{CAPTCHA_MAX_ATTEMPTS}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{solver_url}/solve",
                    json={"url": page.url},
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as resp:
                    if resp.status != 200:
                        force_log(f"❌ Ошибка решателя: HTTP {resp.status}")
                        await asyncio.sleep(5)
                        continue
                    
                    data = await resp.json()
        except Exception as e:
            force_log(f"❌ Ошибка связи с решателем: {e}")
            await asyncio.sleep(5)
            continue

        if not data.get("solved"):
            force_log(f"❌ Решатель не справился: {data.get('error')}")
            await asyncio.sleep(5)
            continue

        token = data.get("token")
        if not token:
            force_log("❌ Решатель вернул пустой токен. Проверьте прокси решателя.")
            await asyncio.sleep(5)
            continue

        force_log(f"✅ Токен получен. Вставляем в страницу...")
        
        # Инъекция токена через JavaScript
        await page.evaluate(f"""
            (token) => {{
                if (window.smartCaptcha && typeof window.smartCaptcha.setToken === 'function') {{
                    window.smartCaptcha.setToken(token);
                }}
                const ta = document.querySelector('textarea[name="smart-token"], input[name="smart-token"]');
                if (ta) {{ 
                    ta.value = token; 
                    ta.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
                const form = document.querySelector('form');
                if (form) {{
                    const btn = form.querySelector('button[type="submit"], .CaptchaButton_view_action, #smartcaptcha-demo-submit');
                    if (btn) {{ btn.click(); }} else {{ form.submit(); }}
                }}
            }}
        """, token)
        
        await asyncio.sleep(5)
        if not await _detect_captcha(page):
            force_log("✅ Капча успешно пройдена!")
            return True
        
        force_log("⚠️ Токен принят, но страница не обновилась. Пробуем снова...")

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
    """Открытие главной страницы Яндекса"""
    try:
        await page.goto(YANDEX_HOME, wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        if "ERR_" in str(e) and "ERR_TIMED_OUT" not in str(e):
            raise RuntimeError(f"Proxy Connection Error: {e}")
    
    await human.pause(2, 4)
    if await _detect_captcha(page):
        if not await _try_solve_captcha(page): 
            raise RuntimeError('Не удалось пройти капчу на главной')

async def search(page, query: str):
    """Ввод поискового запроса"""
    sel = await _find_search_input(page)
    if not sel: 
        raise RuntimeError(f"Не найдено поле поиска. URL: {page.url}")
    
    await _focus_input(page, sel)
    await human.type_text_keyboard(page, query)
    await page.keyboard.press('Enter')
    
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=60000)
    except: 
        pass
        
    await human.pause(3, 5)
    if await _detect_captcha(page):
        if not await _try_solve_captcha(page): 
            raise RuntimeError('Не удалось пройти капчу в выдаче')

async def _find_target_link(page, site: str):
    """Поиск ссылки на целевой сайт в органической выдаче"""
    links = await page.query_selector_all('.serp-item a[href], .Organic a[href]')
    for link in links:
        href = await link.get_attribute('href')
        if href and site in href:
            if await link.is_visible(): 
                return link
    return None

async def run(page, task: dict) -> dict:
    """Основной цикл выполнения сценария ПФ"""
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
            
            # Листаем страницу вниз
            for _ in range(random.randint(3, 6)):
                await human.scroll(page, 'down', random.randint(300, 600))
                await asyncio.sleep(1.5)
            
            link = await _find_target_link(page, site)
            if link:
                force_log("🔥 САЙТ НАЙДЕН! Переходим...")
                await link.scroll_into_view_if_needed()
                await human.click_element(page, link)
                
                try: 
                    await page.wait_for_load_state('domcontentloaded', timeout=45000)
                except: 
                    pass
                
                # Имитируем активность на сайте (скроллы и паузы)
                for _ in range(random.randint(2, 4)):
                    await human.scroll(page, 'down', random.randint(200, 500))
                    await asyncio.sleep(random.randint(5, 15))
                
                res['status'] = 'success'
                return res
            
            # Переход на следующую страницу выдачи
            next_btn = await page.query_selector('.pager__item_kind_next')
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(5)
            else: 
                break
                
    except Exception as e:
        res['error'] = str(e)
        force_log(f"❌ Ошибка выполнения сценария: {e}")
        
    return res
