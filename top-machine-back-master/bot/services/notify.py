import re
import logging
import idna

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import ADMIN_CHAT_IDS

logger = logging.getLogger(__name__)


def _checkmark(value) -> str:
    return "✅" if str(value).strip().lower() == "true" else "❌"


def _sanitize(value) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else "—"


def _format_keywords(keywords) -> str:
    if keywords and isinstance(keywords, str):
        lines = [w.strip() for w in keywords.splitlines() if w.strip()]
        return "\n".join(f"{i+1}. {kw}" for i, kw in enumerate(lines)) if lines else "—"
    return "—"

def _normalize_site(site: str) -> str:
    site = re.sub(r'^https?://', '', site.strip(), flags=re.IGNORECASE).strip('/')
    try:
        return idna.encode(site).decode()
    except idna.IDNAError:
        return re.sub(r'[^a-zA-Z0-9.-]', '', site)

async def notify_admin(
    bot: Bot,
    telegram_id: int,
    site: str,
    request_id: int,
    keywords: str | None = None,
    region: str | None = None,
    audit=None,
    keywords_selection=None,
    google=None,
    yandex=None,
) -> None:
    if not site or not str(telegram_id):
        return

    safe_site = _normalize_site(site)[:50]
    # Получаем инфо о пользователе
    try:
        user = await bot.get_chat(telegram_id)
        name = user.first_name or "—"
        username = f"@{user.username}" if user.username else "—"
    except Exception as e:
        logger.warning(f"Не удалось получить данные пользователя: {e}")
        name = "—"
        username = "—"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять в работу", callback_data=f"accept:{telegram_id}:{safe_site}:{request_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{telegram_id}:{safe_site}:{request_id}")],
    ])

    text = (
        f"👤 ID: {telegram_id}\n"
        f"📛 Имя: {name}\n"
        f"🔗 Никнейм: {username}\n"
        f"🌐 Сайт: {site}\n"
        f"📍 Регион: {_sanitize(region)}\n"
        f"🔍 Аудит сайта: {_checkmark(audit)}\n"
        f"🧠 Подбор ключей: {_checkmark(keywords_selection)}\n"
        f"🌐 Google: {_checkmark(google)}\n"
        f"🌐 Yandex: {_checkmark(yandex)}\n"
        f"🔑 Ключевые слова:\n{_format_keywords(keywords)}"
    )

    for admin_id in ADMIN_CHAT_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")
