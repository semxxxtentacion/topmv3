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
            if resp.status != 201:
                logger.error(f"Ошибка Solcap: {await resp.text()}")
                return None
            
            data = await resp.json()
            task_id = data.get("task_id")

        if not task_id: return None
        logger.info(f"Задача создана! ID: {task_id}. Ждем решения (обычно 5-15 сек)...")

        for _ in range(20):
            await asyncio.sleep(3)
            async with session.get(f"{BASE_URL}/coordinate_captcha/task/{task_id}/", headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    answer = result.get("answer")                    
                    if answer and "coordinates" in answer:
                        coords = answer["coordinates"]
                        logger.info(f"Решение получено! Координаты: {coords}")
                        return coords
                elif resp.status >= 400:
                    return None
        return None
