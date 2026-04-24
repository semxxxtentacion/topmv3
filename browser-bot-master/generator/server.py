"""
FastAPI server for acc-generator.

Auto-pilot mode: profiles are generated and warmed up automatically.
API is for monitoring only.

Run:
    uvicorn generator.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from generator import database as db
from generator.warmup import start_scheduler, stop_scheduler
from generator.config import API_HOST, API_PORT, PROXY_FILE, MAX_PROFILES
from generator import proxy_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("server")


# ---------------------------------------------------------------------------
# Lifespan — DB pool + auto-pilot scheduler
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_pool()
    logger.info("DB pool ready")
    loaded = proxy_manager.load_proxies(PROXY_FILE)
    if loaded:
        logger.info(f"Proxy pool: {proxy_manager.get_proxy_count()} proxies")
    else:
        logger.warning("No proxies loaded — farming/warmup will run without proxies")
    start_scheduler()
    yield
    stop_scheduler()
    await db.close_pool()
    logger.info("Shutdown complete")


app = FastAPI(
    title="acc-generator API",
    description="Auto-pilot profile generator & warmup service",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class StatsResponse(BaseModel):
    total: int
    warm: int
    partial: int
    new: int
    dead: int
    total_cookies: int
    avg_cookies: float
    needing_warmup: int
    max_profiles: int
    slots_available: int


# ---------------------------------------------------------------------------
# Endpoints — monitoring only
# ---------------------------------------------------------------------------

@app.get("/stats", response_model=StatsResponse)
async def stats():
    """Profile pool statistics."""
    data = await db.get_stats()
    active = data["total"] - data["dead"]
    return StatsResponse(
        total=data["total"],
        warm=data["warm"],
        partial=data["partial"],
        new=data["new"],
        dead=data["dead"],
        total_cookies=int(data["total_cookies"]),
        avg_cookies=round(float(data["avg_cookies"]), 1),
        needing_warmup=data["needing_warmup"],
        max_profiles=MAX_PROFILES,
        slots_available=max(0, MAX_PROFILES - active),
    )


@app.get("/profiles")
async def list_profiles(
    status: str | None = Query(None, pattern="^(new|warm|partial|dead)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List profiles with optional status filter."""
    profiles = await db.list_profiles(status=status, limit=limit, offset=offset)
    return [
        {
            **p,
            "id": str(p["id"]),
            "created_at": str(p["created_at"]) if p.get("created_at") else None,
            "last_warmup_at": str(p["last_warmup_at"]) if p.get("last_warmup_at") else None,
        }
        for p in profiles
    ]


@app.get("/profiles/{profile_id}")
async def get_profile(profile_id: UUID):
    """Get a single profile with its latest cookies."""
    profile = await db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    result = {}
    for k, v in profile.items():
        if isinstance(v, UUID):
            result[k] = str(v)
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


@app.post("/profiles/take")
async def take_profile(status: str = Query("warm", pattern="^(new|warm|partial)$")):
    """Take a random profile (full data + cookies + localStorage), removes it from DB."""
    profile = await db.take_random_profile(status=status)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profiles with status '{status}' available")

    result = {}
    for k, v in profile.items():
        if isinstance(v, UUID):
            result[k] = str(v)
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


@app.post("/proxies/refresh")
async def refresh_proxies():
    """Refresh IPs on all proxies via asocks API."""
    count = proxy_manager.get_proxy_count()
    if count == 0:
        raise HTTPException(status_code=400, detail="No proxies loaded")
    refreshed = await proxy_manager.refresh_all()
    return {"message": f"Refreshed {refreshed}/{count} proxy IPs"}


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("generator.server:app", host=API_HOST, port=API_PORT, reload=True)
