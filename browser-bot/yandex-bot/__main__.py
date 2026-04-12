"""
CLI entry point for yandex-bot.

Usage:
  # Single task (test mode):
  python -m yandex-bot --keyword "купить диван" --site example.com

  # Multiple keywords:
  python -m yandex-bot -k "купить диван" -k "диван москва" --site example.com

  # Visual debugging:
  python -m yandex-bot -k "тест" --site example.com --headless false --workers 1

  # Batch from tasks.json:
  python -m yandex-bot --cli

  # API server mode:
  python -m yandex-bot server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

# Ensure yandex-bot dir is on path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging(level: str = 'INFO'):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        prog='yandex-bot',
        description='Yandex PF bot — search and click on target sites',
    )
    sub = parser.add_subparsers(dest='command')

    # "server" subcommand
    sub.add_parser('server', help='Start API server')

    # Default: task mode (no subcommand needed)
    parser.add_argument('-k', '--keyword', action='append', help='Search keyword(s)')
    parser.add_argument('-s', '--site', help='Target site domain')
    parser.add_argument('-r', '--region', default='', help='Yandex region code (e.g. 213 for Moscow)')
    parser.add_argument('-c', '--count', type=int, default=1, help='Repeats per keyword')
    parser.add_argument('-w', '--workers', type=int, default=None, help='Max parallel workers')
    parser.add_argument('--headless', default=None, help='true/false — show browser window')
    parser.add_argument('--cli', action='store_true', help='Run batch from tasks.json')
    parser.add_argument('--log-level', default='INFO', help='Log level')

    return parser.parse_args()


def run_server():
    from config import API_HOST, API_PORT, LOG_LEVEL, LOG_FILE
    setup_logging(LOG_LEVEL)
    logger = logging.getLogger('main')

    import uvicorn
    logger.info(f"=== Yandex PF Bot API | {API_HOST}:{API_PORT} ===")
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, log_level="info")


async def run_tasks(args):
    import config

    # Override config from CLI args
    if args.workers is not None:
        config.MAX_WORKERS = args.workers
    if args.headless is not None:
        config.HEADLESS = args.headless.lower() == 'true'

    from db import create_pool, get_profiles, close_pool
    from proxy_manager import ProxyManager
    import worker as browser_worker

    logger = logging.getLogger('main')

    # Load proxies
    proxy_mgr = ProxyManager()
    proxy_mgr.load_all()
    logger.info(f"Proxy pool: {proxy_mgr.count} IPs")

    if proxy_mgr.count == 0:
        logger.error("No proxies available. Check proxy config in .env")
        return

    # Load profiles from DB
    pool = await create_pool()
    profiles = await get_profiles(pool, limit=config.MAX_WORKERS * 3)

    if not profiles:
        logger.error("No profiles in DB. Run the generator first.")
        await close_pool()
        return

    # Build task list
    tasks = []
    if args.cli:
        # Batch mode: load from tasks.json
        from pathlib import Path
        path = Path(config.TASKS_FILE)
        if not path.exists():
            logger.error(f"Tasks file not found: {config.TASKS_FILE}")
            await close_pool()
            return
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        for item in raw:
            count = item.get('count', 1)
            for _ in range(count):
                tasks.append({
                    'site': item['site'],
                    'keyword': item['keyword'],
                    'region': item.get('region', ''),
                })
    elif args.keyword and args.site:
        for kw in args.keyword:
            for _ in range(args.count):
                tasks.append({
                    'site': args.site,
                    'keyword': kw,
                    'region': args.region,
                })
    else:
        logger.error("Specify --keyword and --site, or use --cli for batch mode")
        await close_pool()
        return

    logger.info(f"Tasks: {len(tasks)} | Profiles: {len(profiles)} | Proxies: {proxy_mgr.count} | Workers: {config.MAX_WORKERS}")

    semaphore = asyncio.Semaphore(config.MAX_WORKERS)
    results: list[dict] = []

    MAX_PROXY_RETRIES = 5

    async def run_one(idx: int, task: dict):
        async with semaphore:
            profile = profiles[idx % len(profiles)]
            proxy = proxy_mgr.get_by_index(idx)

            for attempt in range(MAX_PROXY_RETRIES):
                logger.info(f"[{idx+1}/{len(tasks)}] '{task['keyword']}' → {task['site']} via {proxy} (attempt {attempt+1})")
                result = await browser_worker.execute(profile, proxy, task)
                status = result.get('status', '?')

                if status == 'error' and 'Proxy unreachable' in result.get('error', ''):
                    if attempt < MAX_PROXY_RETRIES - 1:
                        # Refresh IP and try again
                        next_proxy = proxy_mgr.get_random()
                        if next_proxy:
                            proxy = next_proxy
                        logger.info(f"[{idx+1}/{len(tasks)}] Proxy failed, refreshing IP and retrying with {proxy}")
                        await proxy_mgr.refresh_ip(proxy)
                        await asyncio.sleep(2)  # wait for new IP to propagate
                        continue
                    else:
                        logger.error(f"[{idx+1}/{len(tasks)}] All {MAX_PROXY_RETRIES} attempts failed")
                break

            results.append(result)
            logger.info(f"[{idx+1}/{len(tasks)}] done: {status}")
            return result

    await asyncio.gather(*(run_one(i, t) for i, t in enumerate(tasks)), return_exceptions=True)

    success = sum(1 for r in results if r.get('status') == 'success')
    not_found = sum(1 for r in results if r.get('status') == 'not_found')
    captcha = sum(1 for r in results if r.get('status') == 'captcha')
    errors = sum(1 for r in results if r.get('status') in ('error', 'timeout'))

    logger.info(f"=== DONE === success={success} not_found={not_found} captcha={captcha} errors={errors}")

    await close_pool()


def main():
    args = parse_args()

    if args.command == 'server':
        run_server()
    else:
        setup_logging(args.log_level)
        asyncio.run(run_tasks(args))


if __name__ == '__main__':
    main()
