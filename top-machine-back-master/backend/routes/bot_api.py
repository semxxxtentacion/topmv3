import logging
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from backend.db.connection import get_pool
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bot-api", tags=["Bot Integration"])

def verify_bot_token(x_bot_token: str = Header(...)):
    if not hasattr(settings, 'bot_api_secret') or x_bot_token != settings.bot_api_secret:
        raise HTTPException(status_code=403, detail="Invalid token")
    return x_bot_token

class TaskResultRequest(BaseModel):
    task_id: int
    status: str

@router.get("/get-task")
async def get_next_task(token: str = Depends(verify_bot_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE bot_tasks
            SET daily_visit_count = 0, last_reset_date = CURRENT_DATE
            WHERE last_reset_date < CURRENT_DATE
        """)

        task = await conn.fetchrow("""
            SELECT id, target_site, keyword, proxy_url
            FROM bot_tasks
            WHERE is_paused = FALSE
              AND successful_visits < total_visit_target
              AND daily_visit_count < daily_visit_target
              AND (
                  last_run_at IS NULL 
                  OR 
                  last_run_at < CURRENT_TIMESTAMP - GREATEST(
                      INTERVAL '3 minutes',
                      ((DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '1 day') - CURRENT_TIMESTAMP) / NULLIF(daily_visit_target - daily_visit_count, 0)
                  )
              )
            ORDER BY last_run_at ASC NULLS FIRST
            LIMIT 1
        """)

        if not task:
            return {"status": "empty"}

        await conn.execute("UPDATE bot_tasks SET last_run_at = CURRENT_TIMESTAMP WHERE id = $1", task["id"])
        
        return {"status": "ok", "task": dict(task)}

@router.post("/report-result")
async def report_task_result(body: TaskResultRequest, token: str = Depends(verify_bot_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if body.status == "success":
            await conn.execute("""
                UPDATE bot_tasks 
                SET successful_visits = successful_visits + 1,
                    daily_visit_count = daily_visit_count + 1
                WHERE id = $1
            """, body.task_id)
        else:
            await conn.execute("""
                UPDATE bot_tasks 
                SET failed_visits = failed_visits + 1 
                WHERE id = $1
            """, body.task_id)
            
    return {"status": "ok"}
