from abc import ABC, abstractmethod


class AuthProvider(ABC):
    """
    Базовый класс для провайдеров авторизации.

    Для добавления нового провайдера (Яндекс, Google и т.д.):
    1. Создать файл в services/auth/ (например yandex_provider.py)
    2. Наследоваться от AuthProvider
    3. Реализовать нужные методы
    4. Подключить в __init__.py и routes/auth.py
    """

    @abstractmethod
    async def register(self, **kwargs) -> dict:
        """Регистрация нового пользователя."""
        ...

    @abstractmethod
    async def login(self, **kwargs) -> dict:
        """Вход пользователя, возвращает JWT токен."""
        ...
