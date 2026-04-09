import json
from time import clock_getres

from fastapi import HTTPException
import logging
import asyncio
import aiohttp
from backend.config import settings
from backend.db.queries import update_application, insert_keywords_for_project, get_keywords_by_id, update_keywords_for_project

logger = logging.getLogger(__name__)

class TopVizardGetLinkResponse:
    result: str
    total: int

class TopVizardService:
    def __init__(self, row):
        super().__init__()
        self.row = row
        
    async def add_to_project(self):
        url = f"{settings.URL_topvisor_url}{settings.URL_add_new_project_at_topvisor}"

        payload = {
            "url": self.row["site"]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=settings.topvizor_headers, json=payload) as response:
                    res = await response.json()
                    if response.status == 200:
                        await update_application(self.row["id"], 'topvizard_id', res["result"])
                        return int(res["result"])
                    else:
                        raise HTTPException(status_code=503, detail='Ошибка сервиса')

        except aiohttp.ClientError as e:
            logger.error(f"Произошла ошибка добавления проекта: {e}")
            raise HTTPException(status_code=503, detail='Ошибка сервиса')
        
        
    async def get_history_link(self, project_id: str):
        url = f"{settings.URL_topvisor_url}{settings.URL_get_positions_2_history_links}"
        payload ={
            "project_id": int(project_id)
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=settings.topvizor_headers, json=payload) as response:
                    resp = await response.json()
                    if response.status == 200:
                        await update_application(self.row["id"], "topvizard_link", resp["result"])
                        logger.info("Добавлена ссылка на проект: %s", resp["result"])
                    else:
                        raise HTTPException(status_code=503, detail='Ошибка сервиса')
        except aiohttp.ClientError as e:
            logger.error(f"Произошла ошибка при получении ссылки: {e}" )
            raise HTTPException(status_code=503, detail='Ошибка сервиса')

    async def add_searchers_regions(self, project_id: str, search_key: int):
        url = f"{settings.URL_topvisor_url}{settings.URL_add_positions_2_searchers_regions}"
        payload = {
            "project_id": int(project_id),
            "searcher_key": int(search_key),
            "region_key": int(self.row["region_id"])
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=settings.topvizor_headers,
                    json=payload
                ) as resp:
                    data = await resp.json()
                    if data:
                        logger.info(f"Добавление региона в проект {project_id} успешно")

        except aiohttp.ClientError as e:
            logger.error(f"Не удалось достучаться до Topvisor: {e}")
            raise HTTPException(status_code=503, detail="Topvizard не доступен")


    async def add_keywords_2_keywords_import(self, project_id: int):
        base_url = settings.URL_topvisor_url
        headers = settings.topvizor_headers

        try:
            async with aiohttp.ClientSession(headers=headers) as session:

                add_resp = await session.post(
                    f"{base_url}{settings.URL_add_keywords_2_keywords_import}",
                    headers=settings.topvizor_headers,
                    json={
                        "project_id": project_id,
                        "keywords": self.row["keywords"],
                    },
                )
                add_resp.raise_for_status()
                add_data = await add_resp.json()

                if not add_data:
                    return

                logger.info("Добавление ключевых слов прошло успешно")
                get_group_id = await session.post(
                    f"{base_url}{settings.URL_get_keywords_2_groups}",
                    headers=settings.topvizor_headers,
                    json={ "project_id": project_id }
                )

                get_group_id.raise_for_status()
                get_id_group = await get_group_id.json()
                group_id = get_id_group['result'][0]["id"]

                
                get_resp = await session.post(
                    f"{base_url}{settings.URL_get_keywords_2_keywords}",
                    json={"project_id": project_id},
                )
                get_resp.raise_for_status()
                get_data = await get_resp.json()

                if not get_data or "result" not in get_data:
                    return

                await insert_keywords_for_project(
                    project_id=self.row["id"],
                    group_id=group_id,
                    keywords=get_data["result"],
                )

        except aiohttp.ClientError:
            logger.exception("Ошибка при работе с Topvisor API")
            raise HTTPException(
                status_code=503,
                detail="Ошибка на стороне сервиса Topvisor",
            )
        
    async def update_keyword(self, keyword_id: str, new_word: str) -> None:
        keyword = await get_keywords_by_id(keyword_id)
        url = f"{settings.URL_topvisor_url}{settings.URL_edit_keywords_2_keywords_rename}"
        payload = {
            "project_id": keyword["project_id"],
            "name": new_word,
            "id": keyword["keyword_id"]
        }
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(url, headers=settings.topvizor_headers, json=payload)

                response.raise_for_status()
                data = await response.json()

                if not data or "result" not in data:
                    return
                
                new_data = data["result"]
                new_word = await update_keywords_for_project(keyword_id, new_data.id, new_data.name)

                return new_word
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка обновления ключевой фразы")
            return False
                
    async def start_push_service(self):
        project_id = await self.add_to_project()
        if not project_id:
            logger.error("Ошибка при добавлении проекта")
            return
        
        tasks = []
        tasks.append(self.get_history_link(project_id))
        tasks.append(self.add_keywords_2_keywords_import(project_id))
        if self.row.get("yandex"):
            tasks.append(self.add_searchers_regions(project_id, 0))

        if self.row.get("google"):
            tasks.append(self.add_searchers_regions(project_id, 1))

        if tasks:
            await asyncio.gather(*tasks)