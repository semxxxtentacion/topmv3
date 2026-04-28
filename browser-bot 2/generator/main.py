"""
Profile generator CLI.

Usage:
    cd yandexBot

    # With 3proxy from config.py (recommended):
    python -m generator --count 100 --workers 10 --use-3proxy

    # With proxy file:
    python -m generator --count 100 --workers 8 --proxy-file proxies.txt

    # Without proxies (slow, auto-throttled):
    python -m generator --count 10 --workers 2

    # Only fingerprints, no cookies:
    python -m generator --count 1000 --no-farm
"""

from __future__ import annotations

import asyncio
import json
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.fingerprints import generate_profiles
from generator.farmer import farm_one_profile
from generator.proxy_forwarder import start_forwarders, stop_forwarders
from generator import proxy_manager

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated_profiles"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).resolve().parent.parent / "profile_generator.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("profile_generator")


def _load_proxies_from_file(filepath: str) -> list[dict]:
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Proxy file not found: {filepath}")
        return []

    proxies: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) == 4:
            proxies.append({
                "server": f"socks5://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": parts[3],
            })
        elif len(parts) == 2:
            proxies.append({"server": f"socks5://{parts[0]}:{parts[1]}"})
        else:
            logger.warning(f"Bad proxy line: {line}")

    logger.info(f"Loaded {len(proxies)} proxies from {filepath}")
    return proxies


def _load_3proxy_range() -> list[dict]:
    """Load proxies from 3proxy port range defined in config.py."""
    from generator.config import (
        PROXY_HOST, PROXY_PORT_FIRST, PROXY_PORT_LAST,
        PROXY_USER, PROXY_PASS,
    )

    proxies: list[dict] = []
    for port in range(PROXY_PORT_FIRST, PROXY_PORT_LAST + 1):
        proxy: dict = {"server": f"socks5://{PROXY_HOST}:{port}"}
        if PROXY_USER:
            proxy["username"] = PROXY_USER
            proxy["password"] = PROXY_PASS
        proxies.append(proxy)

    logger.info(
        f"3proxy: {len(proxies)} proxies "
        f"({PROXY_HOST}:{PROXY_PORT_FIRST}-{PROXY_PORT_LAST})"
    )
    return proxies


async def run(
    count: int,
    workers: int,
    headless: bool,
    proxy_file: str | None,
    use_3proxy: bool,
    farm: bool,
    delay: float,
    source: str = "builtin",
    external_path: str | None = None,
):
    logger.info(f"Generating {count} mobile fingerprints (source={source})...")
    profiles = generate_profiles(count, source=source, external_path=external_path)
    logger.info(f"Generated {count} fingerprints (source={source})")

    if not farm:
        logger.info("Skipping cookie farming (--no-farm)")
        return _save(profiles)

    proxies: list[dict] = []
    if use_3proxy:
        proxies = _load_3proxy_range()
    elif proxy_file:
        # Try asocks format (ip:port:login:pass:refresh_link), fallback to old
        loaded = proxy_manager.load_proxies(proxy_file)
        if loaded:
            proxies = proxy_manager.get_all_proxies()
        else:
            proxies = _load_proxies_from_file(proxy_file)

    if not proxies and workers > 2:
        logger.warning(
            f"No proxies loaded — capping workers to 2 (was {workers}) "
            f"to avoid mass captchas"
        )
        workers = 2

    if not proxies and delay < 5:
        delay = max(delay, 8.0)
        logger.info(f"No proxies — auto delay set to {delay:.0f}s between profiles")

    if proxies:
        per_ip = count / len(proxies)
        logger.info(
            f"Proxy pool: {len(proxies)} IPs, ~{per_ip:.1f} profiles per IP"
        )
        needs_auth = any(p.get("username") for p in proxies)
        if needs_auth:
            logger.info("Proxies require auth — starting local forwarders...")
            proxies = await start_forwarders(proxies)

    semaphore = asyncio.Semaphore(workers)
    done_count = 0
    start_time = asyncio.get_event_loop().time()

    async def process(idx: int, profile: dict) -> dict:
        nonlocal done_count

        if delay > 0:
            stagger = idx * delay / workers
            await asyncio.sleep(stagger)

        proxy = proxies[idx % len(proxies)] if proxies else None
        async with semaphore:
            result = await farm_one_profile(
                profile, proxy_cfg=proxy, headless=headless,
            )
            done_count += 1
            warm = result.get("warm")
            partial = result.get("partial")
            n_cookies = len(result.get("cookies", []))

            if warm:
                tag = "WARM"
            elif partial:
                tag = f"PARTIAL({n_cookies}ck)"
            else:
                tag = "FAIL"

            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(
                f"[{done_count}/{count}] {tag} "
                f"pid={result['pid'][:8]} cookies={n_cookies} "
                f"({elapsed:.0f}s elapsed)"
            )
            return result

    logger.info(
        f"Starting cookie farming: {workers} workers, "
        f"{delay:.0f}s delay between profiles"
    )
    tasks = [process(i, p) for i, p in enumerate(profiles)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid: list[dict] = []
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
            logger.error(f"Worker exception: {r}")
        else:
            valid.append(r)

    output = _save(valid, errors)
    if valid:
        try:
            from generator.database import insert_profiles_batch
            logger.info("💾 Сохраняем сгенерированные профили в базу данных...")
            await insert_profiles_batch(valid)
            logger.info("✅ Профили успешно добавлены в БД!")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в БД: {e}", exc_info=True)

    try:
        await asyncio.wait_for(stop_forwarders(), timeout=5)
    except Exception:
        logger.debug("Forwarder cleanup timed out (harmless)")

    return output


def _save(profiles: list[dict], errors: int = 0) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"profiles_{ts}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2, default=str)

    warm = sum(1 for p in profiles if p.get("warm"))
    partial = sum(1 for p in profiles if p.get("partial") and not p.get("warm"))
    total_cookies = sum(len(p.get("cookies", [])) for p in profiles)

    logger.info("=" * 55)
    logger.info(f"Total profiles : {len(profiles)}")
    logger.info(f"Warm (full)    : {warm}")
    logger.info(f"Partial (caps) : {partial}")
    logger.info(f"Errors         : {errors}")
    logger.info(f"Total cookies  : {total_cookies}")
    logger.info(f"Saved to       : {output_file}")
    logger.info("=" * 55)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Generate mobile browser profiles with real Yandex cookies",
    )
    parser.add_argument(
        "--count", type=int, default=100,
        help="Number of profiles (default: 100)",
    )
    parser.add_argument(
        "--workers", type=int, default=5,
        help="Parallel browser instances (default: 5)",
    )
    parser.add_argument(
        "--headless", action="store_true", default=True,
        help="Run browsers headless (default)",
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Show browser windows (for debugging)",
    )
    parser.add_argument(
        "--no-farm", action="store_true", default=False,
        help="Only generate fingerprints, skip cookie farming",
    )
    parser.add_argument(
        "--proxy-file", type=str, default=None,
        help="Proxy list file (host:port:user:pass per line)",
    )
    parser.add_argument(
        "--use-3proxy", action="store_true", default=False,
        help="Use 3proxy range from config.py (PROXY_HOST:PORT_FIRST-PORT_LAST)",
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Seconds between launching new profiles (auto-set if no proxies)",
    )
    parser.add_argument(
        "--source", type=str, default="builtin",
        choices=["builtin", "external"],
        help="Fingerprint source: builtin (default) or external (from JSON file)",
    )
    parser.add_argument(
        "--external-path", type=str, default=None,
        help="Path to external fingerprints JSON file (required if --source=external)",
    )

    args = parser.parse_args()

    output = asyncio.run(run(
        count=args.count,
        workers=args.workers,
        headless=args.headless,
        proxy_file=args.proxy_file,
        use_3proxy=args.use_3proxy,
        farm=not args.no_farm,
        delay=args.delay,
        source=args.source,
        external_path=args.external_path,
    ))

    print(f"\nProfiles saved to: {output}")


if __name__ == "__main__":
    main()
