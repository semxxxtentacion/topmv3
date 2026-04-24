import httpx

from backend.config import settings
from backend.db.queries import (
    get_user_by_yandex_id,
    get_user_by_email,
    create_user_by_yandex,
    link_yandex_to_user,
)
from backend.middleware.auth import create_access_token
from backend.services.auth.base import AuthProvider

YANDEX_USER_INFO_URL = "https://login.yandex.ru/info"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"


class YandexAuthProvider(AuthProvider):

    async def register(self, **kwargs):
        raise NotImplementedError

    async def exchange_code(self, code: str) -> dict:
        """Server-side OAuth flow: обмен authorization code на access_token, затем login()."""
        if not (settings.yandex_client_id and settings.yandex_client_secret):
            raise ValueError("Яндекс OAuth не настроен")

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                YANDEX_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.yandex_client_id,
                    "client_secret": settings.yandex_client_secret,
                },
            )
        if token_resp.status_code != 200:
            raise ValueError("Не удалось обменять код Яндекса")

        token_data = token_resp.json()
        yandex_access_token = token_data.get("access_token")
        if not yandex_access_token:
            raise ValueError("Яндекс не вернул access_token")

        return await self.login(access_token=yandex_access_token)

    async def login(self, access_token: str) -> dict:
        # 1. Запрос к Яндекс API за профилем
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                YANDEX_USER_INFO_URL,
                params={"format": "json"},
                headers={"Authorization": f"OAuth {access_token}"},
            )
        if resp.status_code != 200:
            raise ValueError("Не удалось получить данные от Яндекс")

        data = resp.json()
        yandex_id = data.get("id")
        email = data.get("default_email")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        phone = data.get("default_phone", {}).get("number")
        gender = data.get("sex")
        avatar_id = data.get("default_avatar_id")
        avatar_url = (
            f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"
            if avatar_id
            else None
        )

        # 2. Ищем по yandex_id
        user = await get_user_by_yandex_id(yandex_id)
        if user:
            jwt = create_access_token(user["id"])
            return {"access_token": jwt, "token_type": "bearer", "status": "ok"}

        # 3. Ищем по email — привязываем яндекс
        if email:
            user = await get_user_by_email(email)
            if user:
                await link_yandex_to_user(
                    user["id"], yandex_id, first_name, last_name, phone, gender, avatar_url
                )
                jwt = create_access_token(user["id"])
                return {"access_token": jwt, "token_type": "bearer", "status": "ok"}

        # 4. Новый пользователь
        user = await create_user_by_yandex(
            yandex_id, email, first_name, last_name, phone, gender, avatar_url
        )
        jwt = create_access_token(user["id"])
        return {"access_token": jwt, "token_type": "bearer", "status": "ok"}
