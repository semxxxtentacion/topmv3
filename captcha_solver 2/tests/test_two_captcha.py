"""Tests for the 2Captcha HTTP client using httpx MockTransport."""
from __future__ import annotations

import json

import httpx
import pytest

from captcha_solver.two_captcha import (
    Coordinate,
    TwoCaptchaClient,
    TwoCaptchaError,
    _parse_coordinates,
)


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_solve_yandex_smart_happy_path() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("in.php"):
            body = dict(p.split("=", 1) for p in request.content.decode().split("&"))
            assert body["method"] == "yandex"
            assert body["sitekey"] == "SK123"
            return httpx.Response(200, json={"status": 1, "request": "42"})
        if request.url.path.endswith("res.php"):
            return httpx.Response(200, json={"status": 1, "request": "TOKEN_OK"})
        return httpx.Response(404)

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=2)
    async with _mock_client(handler) as hc:
        token = await client.solve_yandex_smart("SK123", "https://x.ru/", client=hc)

    assert token == "TOKEN_OK"
    assert calls == ["/in.php", "/res.php"]


async def test_solve_text_image_returns_recognised_text() -> None:
    """Yandex classic CheckboxCaptcha image OCR — method=base64 without coordinatescaptcha."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("in.php"):
            body = dict(p.split("=", 1) for p in request.content.decode().split("&"))
            seen.update(body)
            assert body["method"] == "base64"
            assert "coordinatescaptcha" not in body  # text mode, NOT coordinate
            assert body["language"] == "2"           # Russian
            assert body["regsense"] == "1"           # case-sensitive
            return httpx.Response(200, json={"status": 1, "request": "9001"})
        if request.url.path.endswith("res.php"):
            return httpx.Response(200, json={"status": 1, "request": "Привет42"})
        return httpx.Response(404)

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=2)
    async with _mock_client(handler) as hc:
        text = await client.solve_text_image("BASE64_IMG", client=hc)

    assert text == "Привет42"
    assert seen["body"] == "BASE64_IMG"


async def test_solve_yandex_smart_polls_until_ready() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("in.php"):
            return httpx.Response(200, json={"status": 1, "request": "42"})
        state["calls"] += 1
        if state["calls"] < 3:
            return httpx.Response(200, json={"status": 0, "request": "CAPCHA_NOT_READY"})
        return httpx.Response(200, json={"status": 1, "request": "LATE_TOKEN"})

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=5)
    async with _mock_client(handler) as hc:
        token = await client.solve_yandex_smart("SK", "https://x.ru/", client=hc)

    assert token == "LATE_TOKEN"
    assert state["calls"] == 3


async def test_submit_rejection_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 0, "request": "ERROR_WRONG_USER_KEY"})

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=1)
    async with _mock_client(handler) as hc:
        with pytest.raises(TwoCaptchaError) as exc:
            await client.solve_yandex_smart("SK", "https://x.ru/", client=hc)
    assert "ERROR_WRONG_USER_KEY" in str(exc.value)


async def test_poll_timeout_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("in.php"):
            return httpx.Response(200, json={"status": 1, "request": "42"})
        return httpx.Response(200, json={"status": 0, "request": "CAPCHA_NOT_READY"})

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=3)
    async with _mock_client(handler) as hc:
        with pytest.raises(TwoCaptchaError) as exc:
            await client.solve_yandex_smart("SK", "https://x.ru/", client=hc)
    assert "timeout" in str(exc.value)


async def test_poll_permanent_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("in.php"):
            return httpx.Response(200, json={"status": 1, "request": "42"})
        return httpx.Response(200, json={"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=3)
    async with _mock_client(handler) as hc:
        with pytest.raises(TwoCaptchaError) as exc:
            await client.solve_yandex_smart("SK", "https://x.ru/", client=hc)
    assert "UNSOLVABLE" in str(exc.value)


async def test_solve_coordinates_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("in.php"):
            body = dict(p.split("=", 1) for p in request.content.decode().split("&"))
            assert body["coordinatescaptcha"] == "1"
            assert body["method"] == "base64"
            return httpx.Response(200, json={"status": 1, "request": "99"})
        return httpx.Response(
            200,
            json={"status": 1, "request": "coordinates:x=10,y=20;x=30,y=40"},
        )

    client = TwoCaptchaClient("k", poll_interval=0, poll_max_tries=2)
    async with _mock_client(handler) as hc:
        pts = await client.solve_coordinates("aGVsbG8=", client=hc)

    assert pts == [Coordinate(10, 20), Coordinate(30, 40)]


def test_parse_coordinates_various_formats() -> None:
    assert _parse_coordinates("coordinates:x=1,y=2") == [Coordinate(1, 2)]
    assert _parse_coordinates("x=5,y=6;x=7,y=8") == [Coordinate(5, 6), Coordinate(7, 8)]


def test_parse_coordinates_rejects_empty() -> None:
    with pytest.raises(TwoCaptchaError):
        _parse_coordinates("")


def test_parse_coordinates_rejects_garbage() -> None:
    with pytest.raises(TwoCaptchaError):
        _parse_coordinates("coordinates:x=a,y=b")


async def test_empty_api_key_raises_on_solve() -> None:
    client = TwoCaptchaClient("", poll_interval=0, poll_max_tries=1)
    async with _mock_client(lambda r: httpx.Response(200, json={})) as hc:
        with pytest.raises(TwoCaptchaError) as exc:
            await client.solve_yandex_smart("SK", "https://x.ru/", client=hc)
    assert "CAPTCHA_API_KEY" in str(exc.value)
