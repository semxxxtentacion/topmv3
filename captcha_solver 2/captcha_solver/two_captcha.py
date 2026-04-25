"""2Captcha API client (also works with RuCaptcha — identical API).

Supported methods:
- yandex               — Yandex SmartCaptcha (click / slider) — returns token
- coordinatescaptcha   — click-at-coordinates on an image — returns list of (x, y)
- base64               — image-based fallback

Docs: https://2captcha.com/2captcha-api
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class TwoCaptchaError(RuntimeError):
    """Raised when the 2Captcha service reports a non-recoverable error."""


@dataclass(slots=True)
class Coordinate:
    x: int
    y: int


class TwoCaptchaClient:
    """Thin async client around 2Captcha's in.php / res.php endpoints."""

    def __init__(
        self,
        api_key: str,
        host: str = "2captcha.com",
        poll_interval: int = 5,
        poll_max_tries: int = 24,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self._submit_url = f"https://{host}/in.php"
        self._result_url = f"https://{host}/res.php"
        self.poll_interval = poll_interval
        self.poll_max_tries = poll_max_tries
        self.timeout = timeout

    # --------------------------------------------------------------- #
    # public helpers                                                   #
    # --------------------------------------------------------------- #

    async def solve_yandex_smart(
        self,
        sitekey: str,
        page_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Submit Yandex SmartCaptcha task, wait for token."""
        payload = {
            "key": self.api_key,
            "method": "yandex",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": "1",
        }
        return await self._submit_and_poll(payload, client=client)

    async def solve_coordinates(
        self,
        image_base64: str,
        *,
        instruction: str = "Click on objects in the correct order",
        language: int = 2,  # 1 = en, 2 = ru
        client: httpx.AsyncClient | None = None,
    ) -> list[Coordinate]:
        """Submit coordinate (click-the-image) captcha, return list of click points."""
        payload = {
            "key": self.api_key,
            "method": "base64",
            "coordinatescaptcha": "1",
            "body": image_base64,
            "textinstructions": instruction,
            "language": str(language),
            "json": "1",
        }
        raw = await self._submit_and_poll(payload, client=client)
        return _parse_coordinates(raw)

    async def solve_coordinates_v2(
        self,
        image_base64: str,
        *,
        img_instructions_base64: str | None = None,
        comment: str = "Click on points in the correct order",
        min_clicks: int = 1,
        max_clicks: int = 8,
        client: httpx.AsyncClient | None = None,
    ) -> list[Coordinate]:
        """CoordinatesTask via 2Captcha v2 API (createTask/getTaskResult).

        Поддерживает `imgInstructions` (картинку с эталоном) — критично для
        задач Yandex AdvancedCaptcha типа silhouette, где работнику нужно
        видеть и главную картинку (где кликать), и эталон (что искать).
        """
        host = self._submit_url.split("/")[2]  # 2captcha.com или rucaptcha.com
        api_v2 = f"https://api.{host}" if not host.startswith("api.") else f"https://{host}"
        # Для 2captcha.com / rucaptcha.com — api.* поддомен
        if host in ("2captcha.com", "rucaptcha.com"):
            api_v2 = f"https://api.{host}"

        task: dict = {
            "type": "CoordinatesTask",
            "body": image_base64,
            "comment": comment,
        }
        if img_instructions_base64:
            task["imgInstructions"] = img_instructions_base64
        if min_clicks:
            task["minClicks"] = min_clicks
        if max_clicks:
            task["maxClicks"] = max_clicks

        close_when_done = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_when_done = True
        try:
            # 1. createTask
            resp = await client.post(
                f"{api_v2}/createTask",
                json={"clientKey": self.api_key, "task": task},
            )
            data = resp.json()
            if data.get("errorId") != 0:
                raise TwoCaptchaError(
                    f"createTask error: {data.get('errorCode')}: {data.get('errorDescription')}"
                )
            task_id = data["taskId"]
            logger.info("v2 createTask CoordinatesTask id=%s", task_id)
            # 2. polling
            for attempt in range(self.poll_max_tries):
                await asyncio.sleep(self.poll_interval)
                r = await client.post(
                    f"{api_v2}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                )
                rd = r.json()
                if rd.get("errorId") != 0:
                    raise TwoCaptchaError(
                        f"getTaskResult error: {rd.get('errorCode')}: {rd.get('errorDescription')}"
                    )
                if rd.get("status") == "ready":
                    coords = rd.get("solution", {}).get("coordinates", [])
                    points = [Coordinate(x=int(p["x"]), y=int(p["y"])) for p in coords]
                    if not points:
                        raise TwoCaptchaError(f"v2 empty coordinates: {rd}")
                    return points
                # status == "processing" → ждём ещё
            raise TwoCaptchaError(f"v2 timeout after {self.poll_max_tries} polls")
        finally:
            if close_when_done:
                await client.aclose()

    async def solve_text_image(
        self,
        image_base64: str,
        *,
        language: int = 2,            # 1 = en, 2 = ru. Yandex classic = ru.
        regsense: int = 1,            # 1 = case-sensitive (важно для русских заглавных)
        numeric: int = 0,             # 0 = letters+digits; 4 = letters only
        min_len: int = 0,
        max_len: int = 0,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Submit a plain image-text CAPTCHA (Yandex AdvancedCaptcha), return recognised text."""
        payload = {
            "key": self.api_key,
            "method": "base64",
            "body": image_base64,
            "language": str(language),
            "regsense": str(regsense),
            "numeric": str(numeric),
            "json": "1",
        }
        if min_len:
            payload["min_len"] = str(min_len)
        if max_len:
            payload["max_len"] = str(max_len)
        return await self._submit_and_poll(payload, client=client)

    # --------------------------------------------------------------- #
    # internal                                                         #
    # --------------------------------------------------------------- #

    async def _submit_and_poll(
        self,
        payload: dict[str, str],
        *,
        client: httpx.AsyncClient | None,
    ) -> str:
        close_when_done = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_when_done = True
        try:
            task_id = await self._submit(payload, client)
            return await self._poll(task_id, client)
        finally:
            if close_when_done:
                await client.aclose()

    async def _submit(self, payload: dict[str, str], client: httpx.AsyncClient) -> str:
        if not self.api_key:
            raise TwoCaptchaError("CAPTCHA_API_KEY is empty")
        resp = await client.post(self._submit_url, data=payload)
        data = resp.json()
        if data.get("status") != 1:
            raise TwoCaptchaError(f"submit rejected: {data.get('request') or data.get('error_text')}")
        task_id = str(data.get("request"))
        logger.info("2Captcha task submitted: id=%s method=%s", task_id, payload.get("method"))
        return task_id

    async def _poll(self, task_id: str, client: httpx.AsyncClient) -> str:
        params = {"key": self.api_key, "action": "get", "id": task_id, "json": "1"}
        for attempt in range(self.poll_max_tries):
            await asyncio.sleep(self.poll_interval)
            try:
                resp = await client.get(self._result_url, params=params)
                data = resp.json()
            except Exception as e:  # transient network error
                logger.warning("2Captcha poll error (attempt %d): %s", attempt, e)
                continue

            if data.get("status") == 1:
                return str(data.get("request"))

            request_field = data.get("request")
            if request_field != "CAPCHA_NOT_READY":
                raise TwoCaptchaError(f"solver error: {request_field}")
            logger.debug("captcha not ready, attempt %d/%d", attempt + 1, self.poll_max_tries)

        raise TwoCaptchaError(f"timeout after {self.poll_max_tries} polls")


def _parse_coordinates(raw: str) -> list[Coordinate]:
    """Parse 2Captcha/Rucaptcha coordinate response.

    Поддерживает два формата:
      1) Старый текстовый: 'coordinates:x=10,y=20;x=30,y=40'
      2) Новый JSON (когда submit с json=1): "[{'x': '10', 'y': '20'}, ...]"
         (Rucaptcha возвращает Python-style строку с одинарными кавычками)
    """
    import ast
    import json as _json

    if raw.startswith("coordinates:"):
        raw = raw[len("coordinates:"):]
    raw = raw.strip()

    # Новый JSON-формат: [{x:N,y:N}, ...]
    if raw.startswith("["):
        # Rucaptcha возвращает Python-style (одинарные кавычки) — пробуем json.loads, потом ast.literal_eval
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError:
            try:
                data = ast.literal_eval(raw)
            except (ValueError, SyntaxError) as e:
                raise TwoCaptchaError(f"cannot parse JSON coordinates: {raw!r}: {e}") from e
        points: list[Coordinate] = []
        for item in data:
            try:
                points.append(Coordinate(x=int(item["x"]), y=int(item["y"])))
            except (KeyError, ValueError, TypeError) as e:
                raise TwoCaptchaError(f"cannot parse coordinate item '{item}': {e}") from e
        if not points:
            raise TwoCaptchaError(f"empty JSON coordinates: {raw!r}")
        return points

    # Старый текстовый формат
    points = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = dict(p.split("=", 1) for p in chunk.split(",") if "=" in p)
        try:
            points.append(Coordinate(x=int(parts["x"]), y=int(parts["y"])))
        except (KeyError, ValueError) as e:
            raise TwoCaptchaError(f"cannot parse coordinate chunk '{chunk}': {e}") from e
    if not points:
        raise TwoCaptchaError(f"no coordinates in response: {raw!r}")
    return points
