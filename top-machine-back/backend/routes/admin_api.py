from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from backend.middleware.admin_auth import get_current_admin, require_role
from backend.db.admin_queries import (
    get_clients,
    get_clients_count,
    get_client_detail,
    update_client,
    delete_client,
    get_client_applications,
    get_client_payments,
    get_all_applications,
    get_applications_count,
    get_application_detail,
    update_application_status,
    assign_manager,
    admin_update_application,
    get_all_admins,
    deactivate_admin,
    get_dashboard_stats,
    get_bot_tasks_by_application,
    get_bot_task_by_id,
    create_bot_task,
    update_bot_task_pause,
    update_bot_task_proxy,
    delete_bot_task,
    get_project_proxies,
    get_project_proxy_by_id,
    create_project_proxy,
    update_project_proxy,
    delete_project_proxy,
    get_random_project_proxy,
)
from backend.db.queries import get_user_by_id
from backend.services.auth.email_provider import EmailAuthProvider
from backend.services.asocks import ASocksService
from backend.services.proxy_checker import check_proxy
from backend.db.bot_queries import get_profiles_stats

router = APIRouter(prefix="/admin", tags=["Admin API"])


# ── Schemas ──

class UpdateClientRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None

class UpdateStatusRequest(BaseModel):
    status: str  # "accepted" | "rejected"

class AssignManagerRequest(BaseModel):
    manager_id: int

class UpdateProjectRequest(BaseModel):
    site: Optional[str] = None
    region: Optional[str] = None
    region_id: Optional[int] = None
    keywords: Optional[str] = None
    audit: Optional[bool] = None
    google: Optional[bool] = None
    yandex: Optional[bool] = None
    keywords_selection: Optional[bool] = None

class CreateProjectProxyRequest(BaseModel):
    proxy_url: str

class UpdateProjectProxyRequest(BaseModel):
    proxy_url: str


# ── Dashboard ──

@router.get("/stats/dashboard")
async def dashboard(admin: dict = Depends(get_current_admin)):
    stats = await get_dashboard_stats()
    return stats


# ── Clients ──

@router.get("/clients")
async def list_clients(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    clients = await get_clients(limit, offset, search)
    total = await get_clients_count(search)
    return {"items": [dict(c) for c in clients], "total": total}


@router.get("/clients/{client_id}")
async def client_detail(client_id: int, admin: dict = Depends(get_current_admin)):
    client = await get_client_detail(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    applications = await get_client_applications(client_id)
    payments = await get_client_payments(client_id)

    return {
        "client": dict(client),
        "applications": [dict(a) for a in applications],
        "payments": [dict(p) for p in payments],
    }


@router.patch("/clients/{client_id}")
async def edit_client(
    client_id: int,
    body: UpdateClientRequest,
    admin: dict = Depends(require_role("admin")),
):
    result = await update_client(client_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return dict(result)


@router.delete("/clients/{client_id}")
async def remove_client(
    client_id: int,
    admin: dict = Depends(require_role("admin")),
):
    client = await get_client_detail(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    await delete_client(client_id)
    return {"status": "ok"}


@router.post("/clients/{client_id}/reset-password")
async def send_reset_to_client(
    client_id: int,
    admin: dict = Depends(get_current_admin),
):
    user = await get_user_by_id(client_id)
    if not user or not user["email"]:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    provider = EmailAuthProvider()
    await provider.request_password_reset(user["email"])
    return {"status": "ok", "message": f"Ссылка сброса отправлена на {user['email']}"}


# ── Applications ──

@router.get("/applications")
async def list_applications(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    apps = await get_all_applications(limit, offset, status)
    total = await get_applications_count(status)
    return {"items": [dict(a) for a in apps], "total": total}


@router.get("/applications/{app_id}")
async def application_detail(app_id: int, admin: dict = Depends(get_current_admin)):
    app = await get_application_detail(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return dict(app)


@router.patch("/applications/{app_id}/status")
async def change_application_status(
    app_id: int,
    body: UpdateStatusRequest,
    admin: dict = Depends(get_current_admin),
):
    if body.status not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Статус должен быть accepted или rejected")

    result = await update_application_status(app_id, body.status)
    if not result:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return dict(result)


@router.patch("/applications/{app_id}/manager")
async def set_manager(
    app_id: int,
    body: AssignManagerRequest,
    admin: dict = Depends(require_role("admin")),
):
    result = await assign_manager(app_id, body.manager_id)
    if not result:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return dict(result)


# ── Projects (edit application details) ──

@router.patch("/projects/{app_id}")
async def edit_project(
    app_id: int,
    body: UpdateProjectRequest,
    admin: dict = Depends(get_current_admin),
):
    result = await admin_update_application(app_id, **body.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return dict(result)


# ── Team ──

@router.get("/team")
async def list_team(admin: dict = Depends(require_role("admin"))):
    admins = await get_all_admins()
    return {"items": [dict(a) for a in admins]}


@router.delete("/team/{admin_id}")
async def remove_team_member(
    admin_id: int,
    admin: dict = Depends(require_role("admin")),
):
    if admin_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Нельзя деактивировать самого себя")

    await deactivate_admin(admin_id)
    return {"status": "ok"}


# ── ASocks Proxy ──

@router.get("/asocks/regions")
async def asocks_regions(admin: dict = Depends(get_current_admin)):
    regions = await ASocksService.get_regions()
    return {"regions": regions}


@router.post("/asocks/create-proxy")
async def asocks_create_proxy(
    state: str = Query(...),
    city: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    result = await ASocksService.create_proxy(state, city)
    if not result:
        raise HTTPException(status_code=502, detail="Не удалось создать прокси")
    return result


@router.get("/asocks/balance")
async def asocks_balance(admin: dict = Depends(get_current_admin)):
    result = await ASocksService.get_balance()
    if result is None:
        raise HTTPException(status_code=502, detail="Не удалось получить баланс")
    return result


# ── Bot Profiles (external DB) ──

@router.get("/bot-profiles/stats")
async def bot_profiles_stats(admin: dict = Depends(get_current_admin)):
    stats = await get_profiles_stats()
    return stats


# ── Project Proxies ──

@router.get("/projects/{app_id}/proxies")
async def list_project_proxies(app_id: int, admin: dict = Depends(get_current_admin)):
    proxies = await get_project_proxies(app_id)
    return {"items": [dict(p) for p in proxies]}


@router.post("/projects/{app_id}/proxies")
async def add_project_proxy(
    app_id: int,
    body: CreateProjectProxyRequest,
    admin: dict = Depends(get_current_admin),
):
    app = await get_application_detail(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Проект не найден")
    proxy = await create_project_proxy(app_id, body.proxy_url)
    return dict(proxy)


@router.put("/project-proxies/{proxy_id}")
async def edit_project_proxy(
    proxy_id: int,
    body: UpdateProjectProxyRequest,
    admin: dict = Depends(get_current_admin),
):
    result = await update_project_proxy(proxy_id, body.proxy_url)
    if not result:
        raise HTTPException(status_code=404, detail="Прокси не найден")
    return dict(result)


@router.delete("/project-proxies/{proxy_id}")
async def remove_project_proxy(
    proxy_id: int,
    admin: dict = Depends(get_current_admin),
):
    proxy = await get_project_proxy_by_id(proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Прокси не найден")
    await delete_project_proxy(proxy_id)
    return {"status": "ok"}


@router.post("/project-proxies/{proxy_id}/check")
async def check_project_proxy(
    proxy_id: int,
    admin: dict = Depends(get_current_admin),
):
    proxy = await get_project_proxy_by_id(proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Прокси не найден")
    result = await check_proxy(proxy["proxy_url"])
    return result


# ── Bot Tasks ──

class CreateBotTaskRequest(BaseModel):
    target_site: str
    keyword: str
    daily_visit_target: int = 50
    total_visit_target: int = 1000
    proxy_url: Optional[str] = None


class TogglePauseRequest(BaseModel):
    is_paused: bool


class SetProxyRequest(BaseModel):
    proxy_url: str


@router.get("/applications/{app_id}/bot-tasks")
async def list_bot_tasks(app_id: int, admin: dict = Depends(get_current_admin)):
    tasks = await get_bot_tasks_by_application(app_id)
    return {"items": [dict(t) for t in tasks]}


@router.post("/applications/{app_id}/bot-tasks")
async def add_bot_task(
    app_id: int,
    body: CreateBotTaskRequest,
    admin: dict = Depends(get_current_admin),
):
    app = await get_application_detail(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Проект не найден")

    proxy_url = body.proxy_url
    if not proxy_url:
        random_proxy = await get_random_project_proxy(app_id)
        if random_proxy:
            proxy_url = random_proxy["proxy_url"]

    if not proxy_url:
        raise HTTPException(status_code=400, detail="У проекта нет прокси. Добавьте прокси перед созданием задачи.")

    task = await create_bot_task(
        application_id=app_id,
        target_site=body.target_site,
        keyword=body.keyword,
        daily_visit_target=body.daily_visit_target,
        total_visit_target=body.total_visit_target,
        proxy_url=proxy_url,
    )
    return dict(task)


@router.patch("/bot-tasks/{task_id}/pause")
async def toggle_bot_task_pause(
    task_id: int,
    body: TogglePauseRequest,
    admin: dict = Depends(get_current_admin),
):
    result = await update_bot_task_pause(task_id, body.is_paused)
    if not result:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return dict(result)


@router.patch("/bot-tasks/{task_id}/proxy")
async def set_bot_task_proxy(
    task_id: int,
    body: SetProxyRequest,
    admin: dict = Depends(get_current_admin),
):
    result = await update_bot_task_proxy(task_id, body.proxy_url)
    if not result:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return dict(result)


@router.delete("/bot-tasks/{task_id}")
async def remove_bot_task(
    task_id: int,
    admin: dict = Depends(get_current_admin),
):
    task = await get_bot_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    await delete_bot_task(task_id)
    return {"status": "ok"}
