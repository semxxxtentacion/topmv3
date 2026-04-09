import asyncio
from backend.db.connection import get_pool
from pathlib import Path
import importlib.util

MIGRATIONS_PATH = Path(__file__).parent / "migrations"

async def apply_migrations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Создаём таблицу миграций, если её нет
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT NOW()
        );
        """)

        # Получаем список уже применённых миграций
        rows = await conn.fetch("SELECT name FROM migrations")
        applied = {row["name"] for row in rows}

        # Пробегаем все файлы миграций в папке
        for file in sorted(MIGRATIONS_PATH.glob("*.py")):
            migration_name = file.stem
            if migration_name in applied:
                continue  # пропускаем уже применённые

            # Динамически импортируем миграцию
            spec = importlib.util.spec_from_file_location(migration_name, file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Выполняем функцию up()
            await module.up(conn)

            # Помечаем миграцию как применённую
            await conn.execute(
                "INSERT INTO migrations (name) VALUES ($1)", migration_name
            )
            print(f"✅ Applied migration: {migration_name}")

asyncio.run(apply_migrations())