"""FastAPI REST wrapper.

Endpoints:
    POST /solve         — старый: принимает URL, открывает свой браузер, решает
    POST /solve_image   — новый: принимает картинки от парсера, возвращает координаты
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from captcha_solver.config import get_settings
from captcha_solver.solver import CaptchaSolver, CaptchaType, SolveResult
from captcha_solver.two_captcha import TwoCaptchaClient, TwoCaptchaError

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


class CookieModel(BaseModel):
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    expires: float | None = None
    httpOnly: bool = False
    secure: bool = False
    sameSite: str | None = None


class SolveResponse(BaseModel):
    type: CaptchaType
    solved: bool
    token: str = ""
    coordinates: list[CoordinateModel] = []
    cookies: list[CookieModel] = []         # для YANDEX_CLASSIC: cookies (включая spravka)
    final_url: str = ""                      # URL после прохождения капчи
    duration_seconds: float
    error: str = ""


class SolveImageRequest(BaseModel):
    """Парсер сам делает screenshot; нам нужны только base64 + контекст."""
    body_b64: str = Field(..., description="Base64 PNG основной картинки (где надо кликать)")
    instructions_b64: str | None = Field(None, description="Base64 PNG эталона/панели задания (опционально)")
    comment: str = Field(
        "Yandex SmartCaptcha silhouette task. Найдите силуэты с эталона на главной "
        "картинке и кликните по ним В ТОМ ЖЕ ПОРЯДКЕ.",
        description="Текстовая инструкция для работника",
    )
    min_clicks: int = Field(1, ge=1, le=20)
    max_clicks: int = Field(8, ge=1, le=20)


class SolveImageResponse(BaseModel):
    solved: bool
    coordinates: list[CoordinateModel] = []
    duration_seconds: float = 0.0
    error: str = ""


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.captcha_api_key:
        logger.warning("CAPTCHA_API_KEY is not set — /solve will fail until configured")
    app.state.solver = CaptchaSolver(settings)
    app.state.two_captcha = TwoCaptchaClient(
        api_key=settings.captcha_api_key,
        host=settings.captcha_service_host,
        poll_interval=settings.captcha_poll_interval,
        poll_max_tries=settings.captcha_poll_max_tries,
    )
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
            cookies=[CookieModel(**c) for c in result.cookies],
            final_url=result.final_url,
            duration_seconds=result.duration_seconds,
            error=result.error,
        )

    @app.post("/solve_image", response_model=SolveImageResponse)
    async def solve_image(req: SolveImageRequest) -> SolveImageResponse:
        """Stateless эндпойнт: парсер шлёт картинки, получает координаты.

        Использовать когда парсер сам ловит капчу и хочет сам кликать в своей сессии
        (правильно для классической Yandex CheckboxCaptcha — cookies остаются у парсера).
        """
        import time
        client: TwoCaptchaClient = app.state.two_captcha
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=30) as hc:
                points = await client.solve_coordinates_v2(
                    req.body_b64,
                    img_instructions_base64=req.instructions_b64,
                    comment=req.comment,
                    min_clicks=req.min_clicks,
                    max_clicks=req.max_clicks,
                    client=hc,
                )
        except TwoCaptchaError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return SolveImageResponse(
            solved=True,
            coordinates=[CoordinateModel(x=p.x, y=p.y) for p in points],
            duration_seconds=time.time() - t0,
        )

    return app


app = create_app()
