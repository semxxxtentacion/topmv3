"""End-to-end REST test with the solver stubbed out (no browser needed)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from captcha_solver.api import rest as rest_module
from captcha_solver.solver import CaptchaType, SolveResult
from captcha_solver.two_captcha import Coordinate

pytest.importorskip("asgi_lifespan")


async def _client_with_stub(result: SolveResult) -> tuple[httpx.AsyncClient, LifespanManager]:
    app = rest_module.create_app()
    lifespan = LifespanManager(app)
    await lifespan.__aenter__()
    app.state.solver = AsyncMock()
    app.state.solver.solve.return_value = result
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), lifespan


async def test_healthz() -> None:
    app = rest_module.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_solve_click_returns_token() -> None:
    result = SolveResult(
        type=CaptchaType.CLICK, solved=True, token="T_OK", duration_seconds=1.5,
        page_url="https://x.ru/",
    )
    client, lifespan = await _client_with_stub(result)
    try:
        resp = await client.post("/solve", json={"url": "https://x.ru/"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "click"
    assert body["token"] == "T_OK"
    assert body["solved"] is True


async def test_solve_coordinate_returns_points() -> None:
    result = SolveResult(
        type=CaptchaType.COORDINATE, solved=True,
        coordinates=[Coordinate(10, 20), Coordinate(30, 40)],
        duration_seconds=2.0, page_url="https://x.ru/",
    )
    client, lifespan = await _client_with_stub(result)
    try:
        resp = await client.post("/solve", json={"url": "https://x.ru/"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "coordinate"
    assert body["coordinates"] == [{"x": 10, "y": 20}, {"x": 30, "y": 40}]


async def test_solve_solver_error_becomes_502() -> None:
    result = SolveResult(
        type=CaptchaType.CLICK, solved=False, error="solver error: timeout",
        duration_seconds=120.0, page_url="https://x.ru/",
    )
    client, lifespan = await _client_with_stub(result)
    try:
        resp = await client.post("/solve", json={"url": "https://x.ru/"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert resp.status_code == 502
    assert "timeout" in resp.json()["detail"]
