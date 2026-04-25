import aiohttp
import asyncio
import logging
import base64

logger = logging.getLogger(__name__)

API_TOKEN = "Token d16f4e233ef43fe7b0fc44682b9814fa2598aa05"
BASE_URL = "https://api.solcap.site/api/v1"

async def solve_coordinate_captcha(image_bytes: bytes, hint_bytes: bytes, domain: str):
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    hint_b64 = base64.b64encode(hint_bytes).decode('utf-8')
    
    headers = {
        "Authorization": API_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "image": image_b64,
        "hint_image": hint_b64,
        "domain": domain
    }

    async with aiohttp.ClientSession() as session:
        logger.info("Отправляем капчу в Solcap...")
        async with session.post(f"{BASE_URL}/coordinate_captcha/task/", json=payload, headers=headers) as resp:
            
            # ИСПРАВЛЕНИЕ 1: Сервис возвращает 200, а не 201
            if resp.status not in (200, 201, 202):
                logger.error(f"Ошибка Solcap при создании: HTTP {resp.status} - {await resp.text()}")
                return None
            
            data = await resp.json()
            task_id = data.get("task_id") or data.get("id")

        if not task_id: 
            logger.error(f"Solcap не вернул task_id! Ответ сервера: {data}")
            return None
            
        logger.info(f"✅ Задача создана! ID: {task_id}. Ждем решения (обычно 5-15 сек)...")

        # Шаг 2: Опрашиваем результат
        for _ in range(20):
            await asyncio.sleep(3)
            async with session.get(f"{BASE_URL}/coordinate_captcha/task/{task_id}/", headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    answer = result.get("answer")
                    
                    if answer:
                        # ИСПРАВЛЕНИЕ 2: Универсальный парсинг координат
                        # Вытаскиваем координаты, как бы Solcap их не спрятал
                        raw_coords = None
                        if isinstance(answer, dict) and "coordinates" in answer:
                            raw_coords = answer["coordinates"]
                        else:
                            raw_coords = answer

                        parsed_coords = []
                        if isinstance(raw_coords, list):
                            for item in raw_coords:
                                if isinstance(item, dict) and "x" in item and "y" in item:
                                    parsed_coords.append([item["x"], item["y"]])
                                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                                    parsed_coords.append([item[0], item[1]])
                        
                        if parsed_coords:
                            logger.info(f"🎯 Решение получено! Координаты: {parsed_coords}")
                            return parsed_coords
                
                # Если сервер ответил не 200 (например, 400 task not ready), просто ждем дальше
                
        logger.error("❌ Solcap не успел решить капчу за 60 секунд.")
        return None
