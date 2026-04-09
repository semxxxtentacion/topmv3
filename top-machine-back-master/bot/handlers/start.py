import random
import string
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db.queries import upsert_user

logger = logging.getLogger(__name__)
router = Router()


def generate_code(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@router.message(CommandStart())
async def start_handler(message: Message):
    user = message.from_user
    code = generate_code()

    try:
        await upsert_user(
            telegram_id=user.id,
            name=user.first_name or "",
            username=user.username or "",
            code=code,
        )
        await message.answer(
            f"Ваш код: `{code}`",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользователя: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")
