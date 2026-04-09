import logging
import aiohttp
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from backend.config import settings
from backend.db.queries import update_keywords_for_project, delete_keywords_by_id, upsert_keywords_for_project, deduct_user_balance, get_application_by_id, get_application_by_topvizard_id, get_user_balance
from backend.middleware.auth import get_current_user_id


async def _assert_app_owned_by_id(application_id: int, user_id: int):
    """Проверяет, что заявка существует и принадлежит вызывающему юзеру (по внутреннему id)."""
    project = await get_application_by_id(application_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if project["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав для этого проекта")
    return project


async def _assert_app_owned_by_topvizard(topvizard_project_id: int, user_id: int):
    """Проверяет владельца по topvisor project_id."""
    project = await get_application_by_topvizard_id(topvizard_project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if project["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав для этого проекта")
    return project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/keywords", tags=["keywords"])

class ApplicationRequest(BaseModel):
    id: str          # наш UUID из keywords_applications
    keyword_id: int  # текущий Topvisor ID
    name: str
    project_id: int

@router.post('/')
async def update_keywords(
    body: ApplicationRequest,
    user_id: int = Depends(get_current_user_id),
):
    await _assert_app_owned_by_topvizard(body.project_id, user_id)

    url = f"{settings.URL_topvisor_url}{settings.URL_edit_keywords_2_keywords_rename}"
    payload = {
        "project_id": body.project_id,
        "name": body.name,
        "id": body.keyword_id,
    }
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(url, headers=settings.topvizor_headers, json=payload)
            response.raise_for_status()
            data = await response.json()
            print(data)
            if "result" not in data or data["result"] is None:
                raise HTTPException(status_code=400, detail="Ошибка сервиса")

            new_word = await update_keywords_for_project(
                id=body.id,
                keyword_id=int(data["result"]["id"]),
                name=data["result"]["name"],
            )
            return new_word
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка обновления ключевой фразы: {e}")
        raise HTTPException(status_code=400, detail=f"Не удалось обновить ключевую фразу: {e}")

class AddKeywordsRequest(BaseModel):
    keywords: str
    project_id: int        # topvisor project_id
    application_id: int   # наш internal id из таблицы applications

@router.post('/add')
async def add_keywords(
    body: AddKeywordsRequest,
    user_id: int = Depends(get_current_user_id),
):
    # Проверяем владельца по обеим сущностям, чтобы нельзя было подсунуть чужой topvisor id
    await _assert_app_owned_by_id(body.application_id, user_id)
    await _assert_app_owned_by_topvizard(body.project_id, user_id)

    add_url = f"{settings.URL_topvisor_url}{settings.URL_add_keywords_2_keywords_import}"
    get_url = f"{settings.URL_topvisor_url}{settings.URL_get_keywords_2_keywords}"

    keywords_count = len([k for k in body.keywords.strip().splitlines() if k.strip()])
    if keywords_count > 0:
        balance = await get_user_balance(user_id)
        if balance is None or balance < keywords_count:
            raise HTTPException(status_code=402, detail="Недостаточно средств на балансе")
        success = await deduct_user_balance(user_id, amount=keywords_count)
        if not success:
            raise HTTPException(status_code=402, detail="Недостаточно средств на балансе")

    try:
        async with aiohttp.ClientSession() as session:
            get_group_id = await session.post(
                f"{settings.URL_topvisor_url}{settings.URL_get_keywords_2_groups}",
                headers=settings.topvizor_headers,
                json={ "project_id": int(body.project_id) }
            )

            get_group_id.raise_for_status()
            get_id_group = await get_group_id.json()
            group_id = get_id_group['result'][0]["id"]
            # 1. Отправляем слова в Topvisor
            add_resp = await session.post(
                add_url,
                headers=settings.topvizor_headers,
                json={
                    "project_id": int(body.project_id),
                    "keywords": body.keywords,
                    "group_id": group_id
                },
            )

            add_resp.raise_for_status()
            add_data = await add_resp.json()
            print("Добавление новых фраз",add_data)
            if not add_data:
                raise HTTPException(status_code=400, detail="Ошибка сервиса при добавлении ключевых фраз")

            get_resp = await session.post(
                get_url,
                headers=settings.topvizor_headers,
                json={"project_id": body.project_id},
            )
            get_resp.raise_for_status()
            get_data = await get_resp.json()

            if not get_data or "result" not in get_data:
                raise HTTPException(status_code=400, detail="Не удалось получить ключевые фразы из сервиса")

            keywords = await upsert_keywords_for_project(
                project_id=body.application_id,
                group_id=group_id,
                keywords=get_data["result"],
            )

            return [dict(kw) for kw in keywords]

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка добавления ключевых фраз: {e}")
        raise HTTPException(status_code=400, detail=f"Не удалось добавить ключевые фразы: {e}")


class DeleteKeywordApplicationHandler(BaseModel):
    project_ids: List[int]
    project_id: int
@router.delete('/')
async def remove_keywords(
    body: DeleteKeywordApplicationHandler,
    user_id: int = Depends(get_current_user_id),
):
    await _assert_app_owned_by_topvizard(body.project_id, user_id)

    url = f"{settings.URL_topvisor_url}{settings.URL_del_keywords_2_keywords}"
    payload = {
        "project_id": body.project_id,
        "fields":["id"],
        "filters": [
            {
                "name":"id",
                "operator":"EQUALS",
                "values": body.project_ids
            }
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=settings.topvizor_headers, json=payload) as resp:
              data = await resp.json()
              if data:
                  for item in body.project_ids:
                      await delete_keywords_by_id(item)

              return {"message": "Keywords removed successfully"}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=400, detail=f"{e}")


class KeysSoRequest(BaseModel):
    domain: str


class KeysSoItem(BaseModel):
    word: str
    ws: int


@router.post('/keys-so')
async def get_keys_so_keywords(
    body: KeysSoRequest,
    user_id: int = Depends(get_current_user_id),
):
    url = settings.get_url(body.domain)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={ "X-Keyso-TOKEN": '69a6da36289ce5.45558874224374d3b735a8e1154e98e8c2ff7c24'}) as resp:
                resp.raise_for_status()
                data = await resp.json()

                if "data" not in data or not data["data"]:
                    raise HTTPException(status_code=404, detail="Данные не найдены")

                return [
                    KeysSoItem(word=item["word"], ws=item["ws"])
                    for item in data["data"]
                ]

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка запроса к keys.so: {e}")
        raise HTTPException(status_code=502, detail=f"Ошибка запроса к keys.so: {e}")
