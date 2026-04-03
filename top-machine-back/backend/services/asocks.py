import logging
import aiohttp
from backend.config import settings

logger = logging.getLogger(__name__)

ASOCKS_COUNTRY_ID = "2017370"


class ASocksService:

    @staticmethod
    async def get_regions() -> list[dict]:
        url = f"{settings.asocks_base_url}/dir/states"
        params = {"apiKey": settings.asocks_api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        logger.error(f"ASocks get_regions failed: {data}")
                        return []
                    return [
                        s for s in data.get("states", [])
                        if str(s.get("dir_country_id")) == ASOCKS_COUNTRY_ID
                    ]
        except aiohttp.ClientError as e:
            logger.error(f"ASocks get_regions error: {e}")
            return []

    @staticmethod
    async def create_proxy(state: str, city: str | None = None) -> dict | None:
        url = f"{settings.asocks_base_url}/proxy/create-port"
        params = {"apiKey": settings.asocks_api_key}
        body = {
            "country_code": "RU",
            "state": state,
            "type_id": 1,
            "proxy_type_id": 2,
        }
        if city:
            body["city"] = city
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=body) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        logger.error(f"ASocks create_proxy failed: {data}")
                        return None
                    logger.info(f"ASocks create_proxy response: {data}")
                    result = data.get("data")
                    if not result:
                        return None
                    if isinstance(result, list):
                        p = result[0]
                    elif isinstance(result, dict):
                        p = result
                    else:
                        logger.error(f"ASocks unexpected data type: {type(result)}")
                        return None
                    proxy_url = f"socks5://{p['login']}:{p['password']}@{p['server']}:{p['port']}"
                    return {
                        "id": p.get("id"),
                        "proxy_url": proxy_url,
                        "login": p.get("login"),
                        "password": p.get("password"),
                        "server": p.get("server"),
                        "port": p.get("port"),
                    }
        except aiohttp.ClientError as e:
            logger.error(f"ASocks create_proxy error: {e}")
            return None

    @staticmethod
    async def get_balance() -> dict | None:
        url = f"{settings.asocks_base_url}/user/balance"
        params = {"apiKey": settings.asocks_api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        logger.error(f"ASocks get_balance failed: {data}")
                        return None
                    return {
                        "balance": data.get("balance"),
                        "balance_traffic": data.get("balance_traffic"),
                    }
        except aiohttp.ClientError as e:
            logger.error(f"ASocks get_balance error: {e}")
            return None
