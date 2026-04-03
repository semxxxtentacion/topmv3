import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher

from bot.config import TOKEN, INTERNAL_HOST, INTERNAL_PORT
from bot.db.connection import get_pool, close_pool
from bot.db.init_db import init_db
from bot.handlers import start, callbacks
from bot.internal.server import make_internal_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(callbacks.router)

    # Инициализируем пул БД и создаём таблицы если нет
    await get_pool()
    await init_db()
    logger.info("✅ БД готова")

    # Поднимаем внутренний HTTP-сервер
    internal_app = make_internal_app(bot)
    runner = web.AppRunner(internal_app)
    await runner.setup()
    site = web.TCPSite(runner, INTERNAL_HOST, INTERNAL_PORT)
    await site.start()
    logger.info(f"✅ Внутренний сервер запущен на {INTERNAL_HOST}:{INTERNAL_PORT}")

    try:
        logger.info("✅ Бот запущен (polling)")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await close_pool()
        await bot.session.close()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
