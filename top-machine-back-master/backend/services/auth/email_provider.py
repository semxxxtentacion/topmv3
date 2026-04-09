import secrets
from datetime import datetime, timedelta

import bcrypt

from backend.db.queries import (
    create_user_by_email,
    get_user_by_email,
    create_verification_token,
    get_verification_token,
    mark_token_used,
    update_user_password,
    verify_user_email,
)
from backend.middleware.auth import create_access_token
from backend.services.auth.base import AuthProvider
from backend.services.mail import send_verification_email, send_password_reset_email


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


class EmailAuthProvider(AuthProvider):

    async def register(self, email: str, password: str) -> dict:
        existing = await get_user_by_email(email)
        if existing:
            raise ValueError("Пользователь с таким email уже существует")

        password_hash = _hash_password(password)
        user = await create_user_by_email(email, password_hash)

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        await create_verification_token(user["id"], token, "email_verification", expires_at)
        await send_verification_email(email, token)

        return {"status": "ok", "message": "Письмо для подтверждения отправлено на вашу почту"}

    async def login(self, email: str, password: str) -> dict:
        user = await get_user_by_email(email)
        if not user:
            raise ValueError("Неверный email или пароль")

        if not _verify_password(password, user["password_hash"]):
            raise ValueError("Неверный email или пароль")

        if not user["email_verified"]:
            raise ValueError("Подтвердите email перед входом")

        token = create_access_token(user_id=user["id"])
        return {"access_token": token, "token_type": "bearer", "status": "ok"}

    async def verify_email(self, token: str) -> dict:
        record = await get_verification_token(token, "email_verification")
        if not record:
            raise ValueError("Невалидная или просроченная ссылка")

        await verify_user_email(record["user_id"])
        await mark_token_used(record["id"])

        return {"status": "ok", "message": "Email успешно подтверждён"}

    async def request_password_reset(self, email: str) -> dict:
        user = await get_user_by_email(email)
        # Не раскрываем существует ли email
        if not user:
            return {"status": "ok", "message": "Если аккаунт существует, письмо отправлено"}

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        await create_verification_token(user["id"], token, "password_reset", expires_at)
        await send_password_reset_email(email, token)

        return {"status": "ok", "message": "Если аккаунт существует, письмо отправлено"}

    async def reset_password(self, token: str, new_password: str) -> dict:
        record = await get_verification_token(token, "password_reset")
        if not record:
            raise ValueError("Невалидная или просроченная ссылка")

        password_hash = _hash_password(new_password)
        await update_user_password(record["user_id"], password_hash)
        await mark_token_used(record["id"])

        return {"status": "ok", "message": "Пароль успешно изменён"}
