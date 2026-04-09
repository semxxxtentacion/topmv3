# Путь: yandex-bot/api.py

from __future__ import annotations

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Optional
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import MAX_WORKERS, API_SECRET, USE_LOCAL_PROXY
from db import create_pool, get_profiles, close_pool
from proxy_manager import ProxyManager
import worker as browser_worker

logger = logging.getLogger(__name__)

app = FastAPI(title="Yandex PF Bot API")

proxy_mgr = ProxyManager()
db_pool = None
profiles: list[dict] = []
tasks_registry: dict[str, dict] = {}

class TaskRequest(BaseModel):
    site: str
    keywords: list[str]
    region: str = ""
    count_per_keyword: int = 1
    secret: str = ""
    proxy_url: Optional[str] = None
    profile_id: Optional[str] = None

class TaskStatus(BaseModel):
    task_id: str
    status: str
    total: int
    done: int
    success: int
    not_found: int
    captcha: int
    errors: int
    created_at: str

@app.on_event("startup")
async def startup():
    global db_pool, profiles
    proxy_mgr.load_all()
    logger.info(f"API: {proxy_mgr.count} proxies ready")

    import local_proxy
    base_port = 8000
    fwd_configs = []
    for i, p in enumerate(proxy_mgr.all_proxies):
        fwd_configs.append({
            'local_port': base_port + i,
            'upstream_host': p.host,
            'upstream_port': p.port,
            'username': p.username,
            'password': p.password,
        })
    if fwd_configs:
        await local_proxy.start_all(fwd_configs)
        logger.info(f"API: {len(fwd_configs)} local proxy forwarders running")

    try:
        db_pool = await create_pool()
        profiles = await get_profiles(db_pool, limit=MAX_WORKERS * 3)
    except Exception as e:
        logger.error(f"API: cannot load profiles from DB: {e}")

    if not profiles:
        logger.error("API: no profiles in DB — run the generator first")
    else:
        logger.info(f"API: {len(profiles)} profiles loaded from DB")

@app.on_event("shutdown")
async def shutdown():
    if USE_LOCAL_PROXY:
        import local_proxy
        await local_proxy.stop_all()
    if db_pool:
        await db_pool.close()

@app.get("/api/health")
async def health():
    running = sum(1 for t in tasks_registry.values() if t['status'] == 'running')
    return {
        "status": "ok",
        "proxies": proxy_mgr.count,
        "profiles": len(profiles),
        "max_workers": MAX_WORKERS,
        "active_tasks": running,
    }

@app.post("/api/task")
async def create_task(req: TaskRequest):
    if API_SECRET and req.secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    if not req.keywords:
        raise HTTPException(status_code=400, detail="keywords list is empty")

    task_id = str(uuid.uuid4())[:8]

    jobs = []
    for kw in req.keywords:
        for _ in range(req.count_per_keyword):
            jobs.append({
                'site': req.site,
                'keyword': kw.strip(),
                'region': req.region,
                'proxy_url': req.proxy_url,
                'profile_id': req.profile_id
            })

    state = {
        'task_id': task_id,
        'status': 'running',
        'total': len(jobs),
        'done': 0,
        'success': 0,
        'not_found': 0,
        'captcha': 0,
        'errors': 0,
        'results': [],
        'created_at': datetime.utcnow().isoformat(),
    }
    tasks_registry[task_id] = state

    asyncio.create_task(_run_task(task_id, jobs))

    logger.info(f"Task {task_id} created: {req.site} | {len(jobs)} jobs")
    return {"task_id": task_id, "total_jobs": len(jobs), "status": "running"}

@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    state = tasks_registry.get(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(**state)

async def _run_task(task_id: str, jobs: list[dict]):
    state = tasks_registry[task_id]
    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def run_job(idx: int, job: dict):
        try:
            async with semaphore:
                # 1. Загружаем профиль
                profile = None
                if job.get('profile_id'):
                    try:
                        async with db_pool.acquire() as conn:
                            row = await conn.fetchrow("SELECT * FROM profiles WHERE id = $1::uuid", job['profile_id'])
                            if row:
                                profile = dict(row)
                                for k in ['fingerprints', 'cookies', 'localstorage', 'proxy', 'viewport', 'geo', 'mouse_config']:
                                    if profile.get(k) and isinstance(profile[k], str):
                                        try: profile[k] = json.loads(profile[k])
                                        except: pass
                    except Exception as e:
                        logger.error(f"[{task_id}] Ошибка БД при поиске профиля: {e}")

                if not profile:
                    if not profiles:
                        raise ValueError(f"Нет доступных профилей в БД для задачи {task_id}!")
                    profile = profiles[idx % max(len(profiles), 1)]

                raw_proxy = job.get('proxy_url')
                local_proxy_cfg = None

                if raw_proxy and raw_proxy.strip():
                    raw_proxy = raw_proxy.strip()
                    logger.info(f"[{task_id}] Получен прокси из админки: {raw_proxy}")
                    
                    found_port = None
                    for i, p in enumerate(proxy_mgr.all_proxies):
                        if p.host in raw_proxy:
                            found_port = 8000 + i
                            break
                    
                    if found_port:
                        local_proxy_cfg = {"server": f"http://127.0.0.1:{found_port}"}
                        logger.info(f"[{task_id}] Найден локальный туннель для этого прокси на порту: {found_port}")
                    else:
                        parts = raw_proxy.replace("http://","").replace("socks5://","").split(':')
                        if len(parts) >= 4:
                            local_proxy_cfg = {
                                "server": f"http://{parts[0]}:{parts[1]}",
                                "username": parts[2],
                                "password": parts[3]
                            }
                        else:
                            local_proxy_cfg = {"server": f"http://{parts[0]}:{parts[1]}"}
                
                if not local_proxy_cfg:
                    base_port = 8000
                    local_port = base_port + (idx % max(proxy_mgr.count, 1))
                    local_proxy_cfg = {"server": f"http://127.0.0.1:{local_port}"}
                    logger.info(f"[{task_id}] Используем стандартный туннель: {local_port}")

                result = await browser_worker.execute(profile, local_proxy_cfg, job)

                status = result.get('status', 'error')
                state['done'] += 1
                if status == 'success': state['success'] += 1
                elif status == 'not_found': state['not_found'] += 1
                elif status == 'captcha': state['captcha'] += 1
                else: state['errors'] += 1
                state['results'].append(result)
                
        except Exception as e:
            logger.error(f"[{task_id}] КРИТИЧЕСКАЯ ОШИБКА в задаче: {e}", exc_info=True)
            state['done'] += 1
            state['errors'] += 1

    coros = [run_job(i, j) for i, j in enumerate(jobs)]
    await asyncio.gather(*coros, return_exceptions=True)

    state['status'] = 'completed'
    logger.info(f"[{task_id}] DONE: success={state['success']} captcha={state['captcha']} errors={state['errors']}")
