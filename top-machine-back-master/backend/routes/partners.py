"""Partners routes.

Contains two routers:
- public_router  — открытый GET списка активных партнёров для лендинга.
- admin_router   — CRUD + загрузка логотипа, защищено admin JWT.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.db import partners_queries as q
from backend.middleware.admin_auth import get_current_admin

public_router = APIRouter(prefix="/public/partners", tags=["Partners (public)"])
admin_router = APIRouter(prefix="/admin/partners", tags=["Partners (admin)"])


# ── Schemas ──────────────────────────────────────────────────────────────

class PartnerCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    logo_url: str
    short_description: str
    full_description: str
    website_url: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    website_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Upload config ────────────────────────────────────────────────────────

_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
_PARTNERS_DIR = _STATIC_ROOT / "partners"
_PARTNERS_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/gif": ".gif",
}
_MAX_LOGO_BYTES = 3 * 1024 * 1024  # 3 MB


# ── Public ───────────────────────────────────────────────────────────────

@public_router.get("")
async def list_active_partners():
    rows = await q.get_active_partners()
    return [dict(r) for r in rows]


# ── Admin CRUD ───────────────────────────────────────────────────────────

@admin_router.get("")
async def admin_list_partners(admin: dict = Depends(get_current_admin)):
    rows = await q.get_all_partners()
    return [dict(r) for r in rows]


@admin_router.post("")
async def admin_create_partner(
    payload: PartnerCreate,
    admin: dict = Depends(get_current_admin),
):
    try:
        row = await q.create_partner(payload.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dict(row)


@admin_router.patch("/{partner_id}")
async def admin_update_partner(
    partner_id: int,
    payload: PartnerUpdate,
    admin: dict = Depends(get_current_admin),
):
    data = payload.model_dump(exclude_unset=True)
    row = await q.update_partner(partner_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    return dict(row)


@admin_router.delete("/{partner_id}")
async def admin_delete_partner(
    partner_id: int,
    admin: dict = Depends(get_current_admin),
):
    ok = await q.delete_partner(partner_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Партнёр не найден")
    return {"ok": True}


@admin_router.post("/upload-logo")
async def admin_upload_partner_logo(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin),
):
    ext = _ALLOWED_MIME.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла")

    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс 3 МБ)")

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = _PARTNERS_DIR / filename
    with open(dest, "wb") as f:
        f.write(data)

    return {"url": f"/static/partners/{filename}"}
