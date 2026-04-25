"""FastAPI REST wrapper — single `/solve` endpoint, same core as gRPC server."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from captcha_solver.config import get_settings
from captcha_solver.solver import CaptchaSolver, CaptchaType, SolveResult

logger = logging.getLogger(__name__)


class SolveRequest(BaseModel):
    url: HttpUrl = Field(..., description="Page URL with SmartCaptcha")
    type: CaptchaType | None = Field(
        None,
        description="Force a specific captcha type. Omit to auto-detect.",
    )


class CoordinateModel(BaseModel):
    x: int
    y: int


class SolveResponse(BaseModel):
    type: CaptchaType
    solved: bool
    token: str = ""
    coordinates: list[CoordinateModel] = []
    duration_seconds: float
    error: str = ""


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.captcha_api_key:
        logger.warning("CAPTCHA_API_KEY is not set — /solve will fail until configured")
    app.state.solver = CaptchaSolver(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Captcha Solver",
        version="0.1.0",
        description="Yandex SmartCaptcha solver — click + coordinate variants",
        lifespan=_lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/solve", response_model=SolveResponse)
    async def solve(req: SolveRequest) -> SolveResponse:
        solver: CaptchaSolver = app.state.solver
        result: SolveResult = await solver.solve(str(req.url), force_type=req.type)
        if not result.solved and result.error:
            # 502 = upstream solver failure; caller may retry
            raise HTTPException(status_code=502, detail=result.error)
        return SolveResponse(
            type=result.type,
            solved=result.solved,
            token=result.token,
            coordinates=[CoordinateModel(x=c.x, y=c.y) for c in result.coordinates],
            duration_seconds=result.duration_seconds,
            error=result.error,
        )

    return app


app = create_app()
