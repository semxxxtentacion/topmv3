async def up(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_tasks (
            id SERIAL PRIMARY KEY,
            application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            
            target_site VARCHAR(500) NOT NULL,
            keyword VARCHAR(500) NOT NULL,
            proxy_url VARCHAR(1000),
            
            daily_visit_target INTEGER NOT NULL DEFAULT 50,    -- Максимум заходов в день
            total_visit_target INTEGER NOT NULL DEFAULT 1000,  -- Сколько всего нужно сделать заходов
            
            daily_visit_count INTEGER NOT NULL DEFAULT 0,      -- Заходы за текущие сутки
            successful_visits INTEGER NOT NULL DEFAULT 0,      -- Заходы за всё время (всего)
            failed_visits INTEGER NOT NULL DEFAULT 0,          -- Ошибки/капчи
            
            last_reset_date DATE DEFAULT CURRENT_DATE,         -- Дата для обнуления дневного счетчика
            last_run_at TIMESTAMP,                             -- Время последнего захода (чтобы делать паузы)
            is_paused BOOLEAN NOT NULL DEFAULT FALSE,          -- Пауза из админки
            
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bot_tasks_dispatch 
        ON bot_tasks(is_paused, last_run_at, last_reset_date);
    """)

async def down(conn):
    await conn.execute("DROP TABLE IF EXISTS bot_tasks CASCADE;")
