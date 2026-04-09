"""
Proxy manager for asocks-style proxy lists.

Format per line: ip:port:login:password:refresh_link
Provides round-robin proxy selection and IP refresh via asocks API.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from itertools import cycle

logger = logging.getLogger(__name__)

_proxies: list[dict] = []
_cycle = None


def load_proxies(path: str | Path = "proxies.txt") -> list[dict]:
    """Load proxies from text file (ip:port:login:password:refresh_link)."""
    global _proxies, _cycle

    p = Path(path)
    if not p.exists():
        logger.warning(f"Proxy file not found: {path}")
        return []

    proxies = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split into 5 parts: ip, port, login, password, refresh_link
        # refresh_link contains ":" so we split max 4 times
        parts = line.split(":", 4)
        if len(parts) < 4:
            logger.warning(f"Bad proxy line (need ip:port:login:pass[:refresh]): {line[:40]}...")
            continue

        entry = {
            "ip": parts[0],
            "port": int(parts[1]),
            "login": parts[2],
            "password": parts[3],
            "refresh_link": parts[4] if len(parts) > 4 else None,
        }
        proxies.append(entry)

    _proxies = proxies
    _cycle = cycle(range(len(_proxies))) if _proxies else None

    logger.info(f"Loaded {len(_proxies)} proxies from {path}")
    return _proxies


def get_proxy_count() -> int:
    return len(_proxies)


def get_all_proxies() -> list[dict]:
    """Return all loaded proxies as Playwright proxy configs."""
    return [_to_playwright(p) for p in _proxies]


def next_proxy() -> dict | None:
    """Get next proxy in round-robin as Playwright proxy config."""
    if not _proxies or not _cycle:
        return None
    idx = next(_cycle)
    return _to_playwright(_proxies[idx])


def next_proxy_with_meta() -> tuple[dict | None, dict | None]:
    """Get next proxy as (playwright_cfg, raw_entry) tuple."""
    if not _proxies or not _cycle:
        return None, None
    idx = next(_cycle)
    p = _proxies[idx]
    return _to_playwright(p), p


def _to_playwright(p: dict) -> dict:
    """Универсальная конвертация прокси для Playwright (SOCKS5)"""
    # Вытаскиваем данные независимо от того, как они названы в словаре
    ip = p.get("ip") or p.get("host") or p.get("server", "")
    port = p.get("port", "")
    login = p.get("login") or p.get("username") or p.get("user", "")
    pwd = p.get("password") or p.get("pwd") or p.get("pass", "")
    
    # Формируем правильный SOCKS5 словарь
    result = {
        "server": f"socks5://{ip}:{port}"
    }
    
    # Добавляем авторизацию, если она есть
    if login and pwd:
        result["username"] = login
        result["password"] = pwd
        
    return result


async def refresh_proxy_ip(proxy: dict) -> bool:
    """Call asocks refresh_link to rotate proxy IP."""
    url = proxy.get("refresh_link")
    if not url:
        return False

    try:
        import urllib.request
        loop = asyncio.get_event_loop()
        req = urllib.request.Request(url, method="GET")

        def _do():
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status

        status = await loop.run_in_executor(None, _do)
        ok = 200 <= status < 300
        if ok:
            logger.info(f"Refreshed IP for {proxy['ip']}:{proxy['port']}")
        else:
            logger.warning(f"Refresh returned status {status} for {proxy['ip']}")
        return ok
    except Exception as e:
        logger.error(f"Failed to refresh proxy {proxy['ip']}: {e}")
        return False


async def refresh_all() -> int:
    """Refresh IPs on all proxies. Returns count of successes."""
    if not _proxies:
        return 0
    results = await asyncio.gather(
        *[refresh_proxy_ip(p) for p in _proxies],
        return_exceptions=True,
    )
    ok = sum(1 for r in results if r is True)
    logger.info(f"Refreshed {ok}/{len(_proxies)} proxy IPs")
    return ok
