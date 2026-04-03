import logging
import re
import aiohttp
from aiohttp_socks import ProxyConnector

logger = logging.getLogger(__name__)

CHECK_URL = "https://httpbin.org/ip"
TIMEOUT = aiohttp.ClientTimeout(total=10)


def clean_proxy_url(proxy_url: str) -> str:
    """Извлекает чистый socks5://login:pass@host:port из строки с мусором."""
    m = re.match(r'(socks[45h]?://[^@]+@[\d.]+:\d+)', proxy_url)
    if m:
        return m.group(1)
    return proxy_url


async def check_proxy(proxy_url: str) -> dict:
    clean_url = clean_proxy_url(proxy_url)
    try:
        connector = ProxyConnector.from_url(clean_url)
        async with aiohttp.ClientSession(connector=connector, timeout=TIMEOUT) as session:
            async with session.get(CHECK_URL) as resp:
                data = await resp.json()
                return {
                    "status": "ok",
                    "ip": data.get("origin", "unknown"),
                }
    except Exception as e:
        logger.warning(f"Proxy check failed for {clean_url}: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
