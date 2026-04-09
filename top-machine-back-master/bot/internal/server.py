import json
import logging

from aiohttp import web
from aiogram import Bot

from bot.services.notify import notify_admin

logger = logging.getLogger(__name__)


def make_internal_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def handle_notify(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        telegram_id = data.get("telegram_id")
        site = data.get("site")

        if not telegram_id or not site:
            return web.Response(
                status=422,
                content_type="application/json",
                text=json.dumps({"status": "error", "message": "Missing telegram_id or site"})
            )

        try:
            await notify_admin(
                bot=bot,
                telegram_id=int(telegram_id),
                site=site,
                request_id=data.get("request_id"),
                keywords=data.get("keywords"),
                region=data.get("region"),
                audit=data.get("audit"),
                keywords_selection=data.get("keywords_selection"),
                google=data.get("google"),
                yandex=data.get("yandex"),
            )
        except Exception as e:
            logger.error(f"Ошибка в handle_notify: {e}")
            return web.Response(
                status=500,
                content_type="application/json",
                text=json.dumps({"status": "error", "message": "Internal error"})
            )

        return web.Response(
            content_type="application/json",
            text=json.dumps({"status": "ok"})
        )

    async def handle_health(request: web.Request) -> web.Response:
        return web.Response(
            status=200,
            content_type="application/json",
            text=json.dumps({"status": "ok"})
        )

    app.router.add_post("/internal/notify", handle_notify)
    app.router.add_get('/health', handle_health)
    return app
