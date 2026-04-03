from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from backend.db.queries import get_user_by_id, update_user_profile
from backend.middleware.auth import get_current_user_id
from backend.services.auth import email_auth, yandex_auth

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Request / Response models ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenRequest(BaseModel):
    token: str

class ResetRequest(BaseModel):
    email: EmailStr

class NewPasswordRequest(BaseModel):
    token: str
    password: str

class AuthTokenResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    status: str

class MessageResponse(BaseModel):
    status: str
    message: str

class YandexAuthRequest(BaseModel):
    access_token: str

class UpdateProfileRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    username: str | None = None

class MeResponse(BaseModel):
    id: int
    email: str | None = None
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    username: str | None = None
    gender: str | None = None
    avatar_url: str | None = None
    applications_balance: int | None = None
    email_verified: bool = False
    created_at: str | None = None


# --- Endpoints ---

@router.post("/register", response_model=MessageResponse)
async def register(body: RegisterRequest):
    """Регистрация по email. Отправляет письмо подтверждения."""
    try:
        result = await email_auth.register(email=body.email, password=body.password)
        return MessageResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthTokenResponse)
async def login(body: LoginRequest):
    """Вход по email/password. Возвращает JWT токен."""
    try:
        result = await email_auth.login(email=body.email, password=body.password)
        return AuthTokenResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/yandex", response_model=AuthTokenResponse)
async def yandex_login(body: YandexAuthRequest):
    """Вход через Яндекс OAuth. Принимает access_token от Яндекс."""
    try:
        result = await yandex_auth.login(access_token=body.access_token)
        return AuthTokenResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: TokenRequest):
    """Подтверждение email по токену из письма."""
    try:
        result = await email_auth.verify_email(token=body.token)
        return MessageResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/request-reset", response_model=MessageResponse)
async def request_reset(body: ResetRequest):
    """Запрос сброса пароля. Отправляет письмо со ссылкой."""
    result = await email_auth.request_password_reset(email=body.email)
    return MessageResponse(**result)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: NewPasswordRequest):
    """Установка нового пароля по токену из письма."""
    try:
        result = await email_auth.reset_password(token=body.token, new_password=body.password)
        return MessageResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=MeResponse)
async def get_me_profile(user_id: int = Depends(get_current_user_id)):
    """Получить профиль текущего пользователя."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return _user_to_response(user)


@router.patch("/me", response_model=MeResponse)
async def update_me_profile(body: UpdateProfileRequest, user_id: int = Depends(get_current_user_id)):
    """Обновить профиль текущего пользователя."""
    user = await update_user_profile(
        user_id,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        username=body.username,
    )
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return _user_to_response(user)


def _user_to_response(user) -> MeResponse:
    return MeResponse(
        id=user["id"],
        email=user.get("email"),
        name=user.get("name"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        phone=user.get("phone"),
        username=user.get("username"),
        gender=user.get("gender"),
        avatar_url=user.get("avatar_url"),
        applications_balance=user["applications_balance"],
        email_verified=user.get("email_verified", False),
        created_at=str(user["created_at"]) if user.get("created_at") else None,
    )
