import logging
import aiohttp
from aiogram import Router
from aiogram.types import CallbackQuery

from bot.db.queries import update_application_status, get_application
from bot.config import YANDEX_BOT_SECRET, YANDEX_BOT_URL
logger = logging.getLogger(__name__)
router = Router()

STATUS_MAP = {
    "accept": "accepted",
    "reject": "rejected",
}

STATUS_LABEL = {
    "accept": "Принят в работу",
    "reject": "Отклонён",
}

async def _trigger_yandex_bot(site: str, keywords: str | None, region: str | None) -> dict | None:
    """Send PF task to yandex-bot API."""
    if not keywords:
        return None

    kw_list = [kw.strip() for kw in keywords.splitlines() if kw.strip()]
    if not kw_list:
        return None

    payload = {
        "site": site,
        "keywords": kw_list,
        "region": region or "",
        "count_per_keyword": 1,
        "secret": YANDEX_BOT_SECRET,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{YANDEX_BOT_URL}/api/task",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"Yandex-bot task created: {data}")
                    return data
                else:
                    body = await resp.text()
                    logger.error(f"Yandex-bot error {resp.status}: {body}")
    except Exception as e:
        logger.error(f"Cannot reach yandex-bot at {YANDEX_BOT_URL}: {e}")

    return None
@router.callback_query()
async def handle_callback(callback: CallbackQuery):
    await callback.answer()

    try:
        action, telegram_id, site, request_id  = callback.data.split(":")
    except ValueError:
        await callback.message.edit_text("❌ Неверный формат данных кнопки.")
        logger.error(f"Некорректный callback_data: {callback.data}")
        return

    status = STATUS_MAP.get(action)
    label = STATUS_LABEL.get(action)

    if not status:
        await callback.message.edit_text("❌ Неизвестное действие.")
        return
    updated_text = f"..."
    if action == "accept":
        app_data = await get_application(int(telegram_id), site)
        if app_data and app_data.get('yandex') and app_data.get('keywords'):
            result = await _trigger_yandex_bot(
                site=app_data['site'],
                keywords=app_data['keywords'],
                region=app_data.get('region'),
            )
            if result:
                task_id = result.get('task_id', '?')
                total = result.get('total_jobs', 0)
                updated_text += f"\n🚀 PF запущен: {total} задач (id: {task_id})"
            else:
                updated_text += "\n⚠️ PF не запущен (нет ключевых слов или yandex-bot недоступен)"
        elif app_data and not app_data.get('yandex'):
            updated_text += "\n📌 Яндекс PF не требуется для этой заявки"
    try:
        await update_application_status(
            request_id=int(request_id),
            status=status,
        )
    except Exception as e:
        logger.error(f"Ошибка обновления статуса: {e}")

    updated_text = f"{callback.message.text}\n\n📝 Статус: {label}"
    await callback.message.edit_text(updated_text)
