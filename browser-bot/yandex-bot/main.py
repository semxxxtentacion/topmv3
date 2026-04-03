from __future__ import annotations

"""
Entry point for yandex-bot.

Two modes:
  python main.py          → starts HTTP API server (for Telegram bot integration)
  python main.py --cli    → runs tasks from tasks.json (one-shot batch mode)
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from config import (
    MAX_WORKERS, LOG_LEVEL, LOG_FILE, TASKS_FILE,
    API_HOST, API_PORT,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ],
)
logger = logging.getLogger('main')


def run_api_server():
    """Start the HTTP API server (default mode)."""
    import uvicorn
    logger.info(f"=== Yandex PF Bot API | {API_HOST}:{API_PORT} | workers={MAX_WORKERS} ===")
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, log_level="info")


async def run_cli():
    """Run tasks from tasks.json (batch mode)."""
    import config # <-- Добавили импорт самого модуля config
    from db import create_pool, get_profiles, close_pool
    from proxy_manager import ProxyManager
    import worker as browser_worker

    logger.info(f"=== CLI mode | workers={config.MAX_WORKERS} ===")

    proxy_mgr = ProxyManager()
    proxy_mgr.load_all()
    logger.info(f"Proxy pool: {proxy_mgr.count} IPs")

    if proxy_mgr.count == 0:
        logger.error("No proxies. Check proxy config in .env")
        return

    # ЗАПУСК ЛОКАЛЬНОГО ПРОКСИ
    import local_proxy
    base_port = 8000
    fwd_configs = []
    for i, p in enumerate(proxy_mgr.all_proxies):
        fwd_configs.append({
            'local_port': base_port + i,
            'upstream_host': p.host,
            'upstream_port': p.port,
            'username': p.username,
            'password': p.password,
        })
    if fwd_configs:
        await local_proxy.start_all(fwd_configs)
        logger.info(f"Local proxy forwarders (SOCKS5 Bridge): {len(fwd_configs)} started")
    # ==========================

    pool = None
    profiles = []
    try:
        pool = await create_pool()
        profiles = await get_profiles(pool, limit=config.MAX_WORKERS * 3)
    except Exception as e:
        logger.error(f"Cannot load profiles from DB: {e}")
        return

    if not profiles:
        logger.error("No profiles in DB. Run the generator first.")
        return

    path = Path(TASKS_FILE)
    if not path.exists():
        logger.error(f"Tasks file not found: {TASKS_FILE}")
        return

    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    tasks = []
    for item in raw:
        count = item.get('count', 1)
        for _ in range(count):
            tasks.append({
                'site': item['site'],
                'keyword': item['keyword'],
                'region': item.get('region', ''),
            })

    if not tasks:
        logger.error("No tasks in file.")
        return

    logger.info(f"{len(tasks)} tasks, {len(profiles)} profiles, {proxy_mgr.count} proxies")

    # Используем config.MAX_WORKERS, который мы могли переопределить из консоли
    semaphore = asyncio.Semaphore(config.MAX_WORKERS)
    results: list[dict] = []

    async def run_one(idx: int, task: dict):
        async with semaphore:
            profile = profiles[idx % len(profiles)]
            proxy = proxy_mgr.get_by_index(idx)
            
            # Локальный прокси для задачи
            local_port = base_port + (idx % proxy_mgr.count)
            local_proxy_cfg = {"server": f"http://127.0.0.1:{local_port}"}

            logger.info(f"[{idx+1}/{len(tasks)}] '{task['keyword']}' → {task['site']} via {proxy.host}:{proxy.port} (local: {local_port})")
            
            # Передаем local_proxy_cfg
            result = await browser_worker.execute(profile, local_proxy_cfg, task)
            results.append(result)
            logger.info(f"[{idx+1}/{len(tasks)}] status={result.get('status', '?')}")
            return result

    await asyncio.gather(*(run_one(i, t) for i, t in enumerate(tasks)), return_exceptions=True)

    success = sum(1 for r in results if r.get('status') == 'success')
    not_found = sum(1 for r in results if r.get('status') == 'not_found')
    captcha = sum(1 for r in results if r.get('status') == 'captcha')
    errors = sum(1 for r in results if r.get('status') in ('error', 'timeout'))

    logger.info(f"=== DONE === success={success} not_found={not_found} captcha={captcha} errors={errors}")

    results_file = Path(__file__).parent / 'results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Results → {results_file}")

    await local_proxy.stop_all()
    await close_pool()


if __name__ == '__main__':
    if '--cli' in sys.argv:
        # Парсим --workers из командной строки, если он есть
        for i, arg in enumerate(sys.argv):
            if arg == '--workers' and i + 1 < len(sys.argv):
                try:
                    import config
                    config.MAX_WORKERS = int(sys.argv[i + 1])
                except ValueError:
                    pass
        
        asyncio.run(run_cli())
    else:
        run_api_server()
