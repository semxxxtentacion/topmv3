import asyncio
import aiohttp
import asyncpg
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Диспетчер: %(message)s")
logger = logging.getLogger("dispatcher")

BACKEND_URL = "http://194.87.86.199:8080/api/bot-api"
BACKEND_SECRET = "topmachine-super-secret-2026"
LOCAL_DB_DSN = "postgresql://admin:s5YX15RUJv6B3vsjr4@db:5432/acc_generator"
LOCAL_BOT_API = "http://yandex-bot:8082/api/task"

CHANGE_IP_LINK = "https://changeip.mobileproxy.space/?proxy_key=d8432adacb8716438427ff7ddfacb28c"

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_task_history (
                id SERIAL PRIMARY KEY,
                profile_id UUID NOT NULL,
                task_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

async def change_proxy_ip(session):
    logger.info("🔄 Отправляем команду на смену IP мобильного прокси...")
    try:
        async with session.get(CHANGE_IP_LINK, timeout=15) as resp:
            if resp.status == 200:
                logger.info("✅ Команда на смену IP принята. Ждем 10 секунд (перезагрузка модема)...")
            else:
                logger.warning(f"⚠️ Ошибка смены IP: сервер вернул код {resp.status}")
    except Exception as e:
        logger.error(f"⚠️ Не удалось дернуть ссылку смены IP (проверьте ссылку): {e}")
    
    await asyncio.sleep(10)

async def main():
    pool = await asyncpg.create_pool(LOCAL_DB_DSN)
    await init_db(pool)
    
    async with aiohttp.ClientSession() as session:
        logger.info("🚀 Диспетчер запущен. Ожидание задач от админки...")
        while True:
            try:
                async with session.get(f"{BACKEND_URL}/get-task", headers={"x-bot-token": BACKEND_SECRET}) as resp:
                    if resp.status == 404:
                        logger.error(f"Бэкенд вернул 404 по адресу {BACKEND_URL}/get-task. Проверьте маршруты API.")
                        await asyncio.sleep(30)
                        continue
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    data = await resp.json()
            except Exception as e:
                logger.error(f"Нет связи с бэкендом: {e}")
                await asyncio.sleep(30)
                continue

            if data.get("status") != "ok":
                await asyncio.sleep(30)
                continue
            
            task = data["task"]
            task_id = task["id"]
            logger.info(f"📥 Принята задача #{task_id}: {task['keyword']} -> {task['target_site']}")

            async with pool.acquire() as conn:
                profile = await conn.fetchrow("""
                    SELECT id FROM profiles 
                    WHERE status = 'warm' 
                      AND id NOT IN (SELECT profile_id FROM profile_task_history WHERE task_id = $1)
                    ORDER BY RANDOM() LIMIT 1
                """, task_id)

            if not profile:
                logger.warning(f"⚠️ Нет свободных 'warm' профилей для #{task_id}. Пропуск.")
                await asyncio.sleep(15)
                continue
            
            profile_id = str(profile["id"])
            logger.info(f"🕵️ Выбран профиль {profile_id[:8]}...")

            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO profile_task_history (profile_id, task_id) VALUES ($1, $2)", profile_id, task_id)

            await change_proxy_ip(session)

            payload = {
                "site": task["target_site"],
                "keywords": [task["keyword"]],
                "count_per_keyword": 1,
                "proxy_url": task.get("proxy_url"),
                "profile_id": profile_id
            }
            
            local_task_id = None
            try:
                async with session.post(LOCAL_BOT_API, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        bot_resp = await resp.json()
                        local_task_id = bot_resp.get("task_id")
                    else:
                        raise Exception(f"Worker API returned {resp.status}")
            except Exception as e:
                logger.error(f"Ошибка отправки задачи в yandex-bot: {e}")
                try:
                    await session.post(
                        f"{BACKEND_URL}/report-result",
                        headers={"x-bot-token": BACKEND_SECRET},
                        json={"task_id": task_id, "status": "failed"}
                    )
                except: pass
                await asyncio.sleep(10)
                continue

            if local_task_id:
                logger.info(f"⏳ Ожидание выполнения задачи {local_task_id} воркером...")
                final_status = "failed"
                
                while True:
                    try:
                        async with session.get(f"http://yandex-bot:8082/api/task/{local_task_id}", timeout=10) as status_resp:
                            if status_resp.status == 200:
                                task_info = await status_resp.json()
                                if task_info.get("status") == "completed":
                                    if task_info.get("success", 0) > 0:
                                        final_status = "success"
                                    elif task_info.get("captcha", 0) > 0:
                                        final_status = "failed" 
                                    else:
                                        final_status = "failed"
                                    break
                    except Exception as e:
                        logger.error(f"Ошибка проверки статуса у воркера: {e}")
                        break
                    
                    await asyncio.sleep(10)

                try:
                    await session.post(
                        f"{BACKEND_URL}/report-result",
                        headers={"x-bot-token": BACKEND_SECRET},
                        json={"task_id": task_id, "status": final_status}
                    )
                    logger.info(f"📊 РЕАЛЬНЫЙ Результат ({final_status}) отправлен в админку.")
                except Exception as e:
                    logger.error(f"Не удалось отправить отчет: {e}")
            
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
