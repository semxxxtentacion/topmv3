import asyncio
import aiohttp
import asyncpg
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Диспетчер: %(message)s")
logger = logging.getLogger("dispatcher")

BACKEND_URL = "https://xn--80aaxohchw2d.xn--p1ai/api/bot-api"
BACKEND_SECRET = "topmachine-super-secret-2026"
LOCAL_DB_DSN = "postgresql://admin:s5YX15RUJv6B3vsjr4@5.129.206.79:5433/acc_generator"
LOCAL_BOT_API = "http://127.0.0.1:8082/api/task"

async def init_db(pool):
    """Создает таблицу истории профилей, если ее еще нет"""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_task_history (
                id SERIAL PRIMARY KEY,
                profile_id UUID NOT NULL,
                task_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

async def main():
    pool = await asyncpg.create_pool(LOCAL_DB_DSN)
    await init_db(pool)
    
    async with aiohttp.ClientSession() as session:
        logger.info("🚀 Диспетчер запущен. Ожидание задач от админки...")
        while True:
            # 1. Спрашиваем задачу у бэка
            try:
                async with session.get(f"{BACKEND_URL}/get-task", headers={"x-bot-token": BACKEND_SECRET}) as resp:
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

            # 2. Ищем свободный профиль в локальной БД
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

            # 3. Бронируем профиль в истории
            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO profile_task_history (profile_id, task_id) VALUES ($1, $2)", profile_id, task_id)

            # 4. Отправляем задачу софту
            payload = {
                "site": task["target_site"],
                "keywords": [task["keyword"]],
                "count_per_keyword": 1,
                "proxy_url": task.get("proxy_url"),
                "profile_id": profile_id
            }
            
            status = "failed"
            try:
                async with session.post(LOCAL_BOT_API, json=payload, timeout=300) as resp:
                    if resp.status == 200:
                        status = "success" if (await resp.json()).get("status") == "running" else "failed"
            except Exception as e:
                logger.error(f"Ошибка софта yandex-bot: {e}")

            # 5. Возвращаем статистику на бэкенд
            try:
                await session.post(
                    f"{BACKEND_URL}/report-result",
                    headers={"x-bot-token": BACKEND_SECRET},
                    json={"task_id": task_id, "status": status}
                )
                logger.info(f"📊 Результат ({status}) отправлен в админку.")
            except Exception as e:
                logger.error(f"Не удалось отправить отчет: {e}")
            
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
