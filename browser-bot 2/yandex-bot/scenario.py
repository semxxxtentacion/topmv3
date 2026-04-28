from __future__ import annotations

import asyncio
import random
import os
import aiohttp
import base64
import human

YANDEX_HOME = 'https://ya.ru'
CAPTCHA_SELECTORS = ['.CheckboxCaptcha', '.AdvancedCaptcha', '.SmartCaptcha', '#captcha-page', '[data-sitekey]']

def force_log(msg: str):
    print(msg, flush=True)

async def _detect_captcha(page) -> bool:
    if 'showcaptcha' in page.url: return True
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.locator(sel).count() > 0: return True
        except: pass
    return False

async def _try_solve_captcha(page) -> bool:
    force_log(f"⚠️ ОБНАРУЖЕНА КАПЧА: {page.url}")
    solver_url = os.getenv("CAPTCHA_SOLVER_URL", "http://captcha-solver:8080")
    stuck_counter = 0 
    
    for attempt in range(8):
        force_log(f"🔄 Анализ состояния капчи (Шаг {attempt + 1}/8)...")
        await asyncio.sleep(2)
        
        try:
            if not await _detect_captcha(page):
                force_log("✅ Капча успешно пройдена (исчезла)!")
                return True

            checkbox = await page.query_selector('.CheckboxCaptcha-Button, #js-button')
            if checkbox and await checkbox.is_visible():
                stuck_counter = 0
                force_log("💡 Видим чекбокс. Кликаем 'Я не робот'...")
                await human.click_element(page, checkbox)
                # Даем Яндексу больше времени на автоматический редирект (зеленую галочку)
                await asyncio.sleep(6) 
                continue 
            
            img_wrapper = await page.query_selector('.AdvancedCaptcha-ImageWrapper, .AdvancedCaptcha-Image')
            if img_wrapper and await img_wrapper.is_visible():
                stuck_counter = 0
                force_log("🖼️ Видим картинку. Снимаем скриншоты...")
                
                await img_wrapper.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                body_bytes = await img_wrapper.screenshot(timeout=10000, animations='disabled', type='jpeg')
                body_b64 = base64.b64encode(body_bytes).decode('utf-8')
                
                instr_b64 = ""
                instr_elem = await page.query_selector('.AdvancedCaptcha-SilhouetteTask')
                if instr_elem and await instr_elem.is_visible():
                    instr_bytes = await instr_elem.screenshot(timeout=5000, type='jpeg')
                    instr_b64 = base64.b64encode(instr_bytes).decode('utf-8')
                
                payload = {"body_b64": body_b64, "instructions_b64": instr_b64, "comment": "Yandex Captcha"}
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{solver_url}/solve_image", json=payload, timeout=120) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("solved") and data.get("coordinates"):
                                force_log("✅ Координаты получены. Кликаем...")
                                box = await img_wrapper.bounding_box()
                                if box:
                                    for pt in data["coordinates"]:
                                        await page.mouse.click(box['x'] + pt['x'], box['y'] + pt['y'])
                                        await asyncio.sleep(0.8)
                                    
                                    submit_btn = await page.query_selector('button.CaptchaButton_view_action, button.AdvancedCaptcha-Submit')
                                    if submit_btn:
                                        force_log("🖱️ Нажали 'Отправить'. Ждем проверку от Яндекса...")
                                        await submit_btn.click()
                                        await asyncio.sleep(7)
                continue 

            stuck_counter += 1
            force_log(f"⚠️ Элементы капчи не найдены (Счетчик пустоты: {stuck_counter})")
            
            # Увеличили терпение до 4 циклов (около 8 секунд) перед перезагрузкой
            if stuck_counter >= 4:
                force_log("🔄 Страница зависла. Принудительно жмем F5 (Reload)...")
                await page.reload(wait_until='domcontentloaded')
                stuck_counter = 0 
                await asyncio.sleep(5)

        except Exception as e:
            if "destroyed" in str(e) or "closed" in str(e):
                force_log("✅ Произошла навигация (нас пустили дальше).")
                await asyncio.sleep(3)
                if not await _detect_captcha(page): return True
            else:
                force_log(f"❌ Ошибка шага: {e}")
                await asyncio.sleep(2)
            
    return False

async def search(page, query: str):
    await page.goto(YANDEX_HOME, wait_until='domcontentloaded', timeout=60000)
    await human.pause(2, 4)
    if await _detect_captcha(page): await _try_solve_captcha(page)
    
    for sel in ['input[name="text"]', 'textarea[name="text"]', '#search-input']:
        if await page.query_selector(sel):
            await page.focus(sel)
            await human.type_text_keyboard(page, query)
            await page.keyboard.press('Enter')
            break
            
    await asyncio.sleep(5)
    if await _detect_captcha(page): await _try_solve_captcha(page)

async def run(page, task: dict) -> dict:
    site = task['site'].replace('https://', '').replace('www.', '').rstrip('/')
    keyword = task['keyword']
    res = {'status': 'failed', 'site': site, 'keyword': keyword}
    
    try:
        force_log(f"🚀 Запуск поиска: {keyword}")
        await search(page, keyword)
        
        for p_idx in range(1, 6):
            force_log(f"📖 Ищем на странице {p_idx}...")
            if await _detect_captcha(page): await _try_solve_captcha(page)
            
            await human.scroll(page, 'down', 800)
            links = await page.query_selector_all('.serp-item a[href], .Organic a[href]')
            for link in links:
                href = await link.get_attribute('href')
                if href and site in href:
                    force_log("🔥 САЙТ НАЙДЕН! Кликаем...")
                    await link.scroll_into_view_if_needed()
                    await human.click_element(page, link)
                    await asyncio.sleep(30)
                    res['status'] = 'success'
                    force_log(f"🏁 Итог задачи: {res}")
                    return res
            
            next_btn = await page.query_selector('.pager__item_kind_next')
            if next_btn: 
                await next_btn.click()
                await asyncio.sleep(4)
            else: break
            
    except Exception as e:
        force_log(f"❌ Критическая ошибка сценария: {e}")
        res['error'] = str(e)
        
    force_log(f"🏁 Итог задачи: {res}")
    return res
