import logging
import re
import idna
import aiohttp
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from backend.config import settings
from backend.db.queries import deduct_user_balance, get_user_by_id, get_user_applications, create_application, get_keywords_by_project_id, delete_project, get_application_by_id, get_user_balance
from backend.middleware.auth import get_current_user_id
from backend.services.topvizard import TopVizardService
import json
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/site", tags=["site"])


class ReceiveSiteRequest(BaseModel):
    site: str
    keywords: str | None = None
    region: str | None = None
    region_id: int
    audit: bool = False
    keywords_selection: bool = False
    google: bool = False
    yandex: bool = False

class KeywordOut(BaseModel):
    id: str
    keyword_id: int | None
    name: str
    group_id: int

class ApplicationOut(BaseModel):
    id: int
    site: str
    region: str | None
    region_id: int | None
    audit: bool
    keywords_selection: bool
    google: bool
    yandex: bool
    keywords: str | None
    status: str | None
    created_at: str
    topvizard_id: str | None
    topvizard_link: str | None
    keywords_from_topvizard: list[KeywordOut] = []



def _normalize_site(site: str) -> str:
    site = re.sub(r'^https?://', '', site.strip(), flags=re.IGNORECASE).strip('/')
    try:
        return idna.encode(site).decode()
    except idna.IDNAError:
        return re.sub(r'[^a-zA-Z0-9.-]', '', site)


@router.post("/receive")
async def receive_site(
    body: ReceiveSiteRequest,
    user_id: int = Depends(get_current_user_id),
):

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    keywords_count = len([k for k in body.keywords.strip().splitlines() if k.strip()]) if body.keywords else 0

    # Без ключей можно только если включён автоподбор. Иначе — 422.
    if keywords_count == 0 and not body.keywords_selection:
        raise HTTPException(
            status_code=422,
            detail="Укажите ключевые слова или включите автоматический подбор",
        )

    # Проверяем, хватает ли баланса ДО создания заявки и списания
    if keywords_count > 0:
        balance = await get_user_balance(user_id)
        if balance is None or balance < keywords_count:
            raise HTTPException(status_code=402, detail="Недостаточно средств на балансе")

    safe_site = _normalize_site(body.site)[:50]
    request = await create_application(
        user_id=user_id,
        site=safe_site,
        region=body.region,
        region_id=body.region_id,
        audit=body.audit,
        keywords_selection=body.keywords_selection,
        google=body.google,
        yandex=body.yandex,
        keywords=body.keywords,
    )

    # Списание — после успешного создания заявки; атомарный deduct на случай гонки
    if keywords_count > 0:
        success = await deduct_user_balance(user_id, amount=keywords_count)
        if not success:
            # компенсация: откатываем созданную заявку
            await delete_project(request["id"])
            raise HTTPException(status_code=402, detail="Недостаточно средств на балансе")

    # Topvisor-пуш только если есть реальные ключи. При keywords_selection=true
    # без ключей — ждём пока юзер/админ подберёт, отдельный flow.
    if keywords_count > 0:
        top_vizard = TopVizardService(request)
        await top_vizard.start_push_service()

    return {"status": "ok"}


@router.get("/applications", response_model=list[ApplicationOut])
async def get_applications(
    user_id: int = Depends(get_current_user_id),
) -> list[ApplicationOut]:
    apps = await get_user_applications(user_id)

    def convert_status(value):
        status = 'Принято в работу' if value == 'accepted' else 'Отклонено'
        return status

    result = []
    for a in apps:
        keywords = await get_keywords_by_project_id(a["id"])
        result.append(
            ApplicationOut(
                id=a["id"],
                site=a["site"],
                region=a["region"],
                region_id=a["region_id"],
                audit=a["audit"],
                keywords_selection=a["keywords_selection"],
                google=a["google"],
                yandex=a["yandex"],
                keywords=a["keywords"],
                status=convert_status(a["status"]),
                created_at=a["created_at"].isoformat(),
                topvizard_id=a["topvizard_id"],
                topvizard_link=a["topvizard_link"],
                keywords_from_topvizard=[
                    KeywordOut(
                        id=str(k["id"]),
                        keyword_id=k["keyword_id"],
                        name=k["name"],
                        group_id=k["group_id"]
                    )
                    for k in keywords
                ]
            )
        )
    return result

class RemoveRequest(BaseModel):
    topvizard_id: int

@router.delete('/{project_id}')
async def remove_project(
    project_id: int,
    body: RemoveRequest,
    user_id: int = Depends(get_current_user_id),
):
    project = await get_application_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if project["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления проекта")

    url = f"{settings.URL_topvisor_url}{settings.URL_del_projects_2_projects}"
    payload = {
        "fields": ['id'],
        "filters": [
            {
                "name": "id",
                "operator": "EQUALS",
                "values": [int(body.topvizard_id)]
            }
        ]
    }
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(url, headers=settings.topvizor_headers, json=payload)
            response.raise_for_status()
            data = await response.json()
            if data:
                await delete_project(project_id)
            return {"message": "OK"}
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка удаления проекта в Topvisor: {e}")
        raise HTTPException(status_code=503, detail="Сервис временно недоступен, попробуйте позже")
