from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import settings
from backend.db.admin_queries import get_admin_by_id

# Отдельный bearer scheme для админов (можно использовать тот же токен,
# но payload содержит "scope": "admin")
admin_bearer = HTTPBearer()

ADMIN_JWT_SECRET = settings.jwt_secret + "_admin"


def create_admin_token(admin_id: int, role: str) -> str:
    payload = {
        "sub": str(admin_id),
        "role": role,
        "scope": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm=settings.jwt_algorithm)


def decode_admin_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, ADMIN_JWT_SECRET, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("scope") != "admin":
            raise jwt.InvalidTokenError("Not an admin token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(admin_bearer),
) -> dict:
    payload = decode_admin_token(credentials.credentials)
    return {"id": int(payload["sub"]), "role": payload["role"]}


# Роли по уровню привилегий
ROLE_HIERARCHY = {"manager": 0, "admin": 1, "superadmin": 2}


def require_role(min_role: str):
    """Dependency factory — проверка минимальной роли."""
    min_level = ROLE_HIERARCHY[min_role]

    def checker(admin: dict = Depends(get_current_admin)) -> dict:
        admin_level = ROLE_HIERARCHY.get(admin["role"], -1)
        if admin_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return admin

    return checker
