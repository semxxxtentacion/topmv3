import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from backend.db.admin_queries import (
    get_admin_by_email,
    create_admin_user,
    create_admin_invite,
    get_admin_invite,
    mark_invite_used,
)
from backend.middleware.admin_auth import create_admin_token, get_current_admin, require_role
from backend.services.mail import send_admin_invite_email

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


# ── Schemas ──

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # "admin" | "manager"

class RegisterRequest(BaseModel):
    token: str
    name: str
    password: str


# ── Endpoints ──

@router.post("/login")
async def admin_login(body: LoginRequest):
    admin = await get_admin_by_email(body.email)
    if not admin:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if not bcrypt.checkpw(body.password.encode(), admin["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    token = create_admin_token(admin["id"], admin["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": admin["role"],
        "name": admin["name"],
    }


@router.post("/invite")
async def invite_admin(body: InviteRequest, admin: dict = Depends(require_role("admin"))):
    # Проверяем что роль валидна
    if body.role not in ("admin", "manager"):
        raise HTTPException(status_code=400, detail="Роль должна быть admin или manager")

    # Только superadmin может приглашать admin
    if body.role == "admin" and admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Только суперадмин может приглашать админов")

    # Проверяем что такой email ещё не зарегистрирован
    existing = await get_admin_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    await create_admin_invite(body.email, body.role, token, admin["id"], expires_at)
    await send_admin_invite_email(body.email, token, body.role)

    return {"status": "ok", "message": f"Приглашение отправлено на {body.email}"}


@router.post("/register")
async def admin_register(body: RegisterRequest):
    invite = await get_admin_invite(body.token)
    if not invite:
        raise HTTPException(status_code=400, detail="Невалидное или просроченное приглашение")

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    await create_admin_user(invite["email"], password_hash, body.name, invite["role"])
    await mark_invite_used(invite["id"])

    return {"status": "ok", "message": "Аккаунт создан, можете войти"}


@router.get("/me")
async def admin_me(admin: dict = Depends(get_current_admin)):
    from backend.db.admin_queries import get_admin_by_id
    record = await get_admin_by_id(admin["id"])
    if not record:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {
        "id": record["id"],
        "email": record["email"],
        "name": record["name"],
        "role": record["role"],
        "created_at": str(record["created_at"]),
    }
