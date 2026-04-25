from __future__ import annotations

"""
Proxy pool manager.
Loads proxies from file (asocks format: ip:port:user:pass[:refresh_link]).
Supports IP refresh via asocks API before use.
"""

import random
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, field

import aiohttp

from config import PROXY_FILE

logger = logging.getLogger(__name__)

HTTP_PORT = 443  # asocks HTTP proxy port


@dataclass
class Proxy:
    host: str
    port: int
    username: str = ''
    password: str = ''
    refresh_link: str = ''

    @property
    def direct_proxy(self) -> dict:
        """Proxy config for Playwright."""
        proxy = {"server": f"http://{self.host}:{self.port}"}
        if self.username:
            proxy["username"] = self.username
            proxy["password"] = self.password
        return proxy
    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


class ProxyManager:
    def __init__(self):
        self._proxies: list[Proxy] = []
        self._index = 0
        self._dead: set[str] = set()

    def load_from_file(self, filepath: str | None = None):
        filepath = filepath or PROXY_FILE
        if not filepath:
            return
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"Proxy file not found: {filepath}")
            return

        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Format: ip:port:user:pass[:refresh_link]
            # Format: ip:port:user:pass[:refresh_link]
            parts = line.split(':', 4)
            if len(parts) >= 4:
                refresh = parts[4] if len(parts) > 4 else ''
                self._proxies.append(Proxy(
                    host=parts[0],
                    port=int(parts[1]),  # Берем реальный порт из файла (9999)
                    username=parts[2],
                    password=parts[3],
                    refresh_link=refresh,
                ))
            elif len(parts) == 2:
                self._proxies.append(Proxy(
                    host=parts[0], port=int(parts[1]),
                ))
            else:
                logger.warning(f"Bad proxy line: {line}")

        logger.info(f"Loaded {len(self._proxies)} proxies from {filepath}")

    def load_all(self):
        self.load_from_file()
        random.shuffle(self._proxies)

    async def refresh_ip(self, proxy: Proxy) -> bool:
        """Call asocks refresh-ip API to get a fresh IP."""
        if not proxy.refresh_link:
            logger.debug(f"No refresh link for {proxy}")
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(proxy.refresh_link, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    body = await resp.text()
                    logger.info(f"Refresh IP for {proxy}: status={resp.status}, body={body[:100]}")
                    return resp.status == 200
        except Exception as e:
            logger.warning(f"Refresh IP failed for {proxy}: {e}")
            return False

    def get_next(self) -> Proxy | None:
        if not self._proxies:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return proxy

    def get_random(self) -> Proxy | None:
        if not self._proxies:
            return None
        return random.choice(self._proxies)

    def get_by_index(self, idx: int) -> Proxy | None:
        if not self._proxies:
            return None
        return self._proxies[idx % len(self._proxies)]

    def mark_dead(self, proxy: Proxy):
        key = f"{proxy.host}:{proxy.port}"
        self._dead.add(key)
        logger.warning(f"Proxy marked dead: {key} (dead total: {len(self._dead)})")

    def get_alive(self, exclude: Proxy | None = None) -> Proxy | None:
        alive = [
            p for p in self._proxies
            if f"{p.host}:{p.port}" not in self._dead
            and (exclude is None or f"{p.host}:{p.port}" != f"{exclude.host}:{exclude.port}")
        ]
        if not alive:
            return None
        return random.choice(alive)

    @property
    def alive_count(self) -> int:
        return sum(1 for p in self._proxies if f"{p.host}:{p.port}" not in self._dead)

    @property
    def count(self) -> int:
        return len(self._proxies)

    @property
    def all_proxies(self) -> list[Proxy]:
        return self._proxies
