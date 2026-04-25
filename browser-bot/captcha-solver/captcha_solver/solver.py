"""Core solver — auto-detects Yandex captcha variant and dispatches to the right handler.

Two variants supported:

1. **Click SmartCaptcha** (`CaptchaType.CLICK`)
   Yandex renders a widget with `data-sitekey`. 2Captcha's `method=yandex`
   returns a token which we inject and the form submits normally.

2. **Coordinate captcha** (`CaptchaType.COORDINATE`)
   Yandex sometimes shows an image challenge ("click the cars in order").
   We screenshot the image, submit to 2Captcha `coordinatescaptcha`, and
   replay the clicks inside Playwright at the returned offsets.

Public entry point: :meth:`CaptchaSolver.solve` — accepts a URL, opens a
fresh browser context, detects the variant, returns the solution.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import random
from dataclasses import dataclass, field
from enum import Enum

import httpx
from playwright.async_api import ElementHandle, Page

from captcha_solver.browser import browser_page
from captcha_solver.config import Settings, get_settings
from captcha_solver.two_captcha import Coordinate, TwoCaptchaClient, TwoCaptchaError

logger = logging.getLogger(__name__)


class CaptchaType(str, Enum):
    CLICK = "click"             # standard Yandex SmartCaptcha (sitekey + token)
    COORDINATE = "coordinate"   # image-based coordinate challenge
    NONE = "none"               # no captcha detected on page


@dataclass(slots=True)
class SolveResult:
    type: CaptchaType
    token: str = ""
    coordinates: list[Coordinate] = field(default_factory=list)
    solved: bool = False
    page_url: str = ""
    duration_seconds: float = 0.0
    error: str = ""


# --- Selectors ----------------------------------------------------------------

_SMARTCAPTCHA_CONTAINER = (
    "[data-testid='captcha'], .smartcaptcha, "
    "#smart-captcha, iframe[src*='smartcaptcha'], "
    ".yndx-captcha, [class*='SmartCaptcha'], [data-sitekey]"
)

_COORDINATE_IMAGE = (
    "img[src*='captcha'], canvas.captcha, "
    ".yndx-captcha__image, [class*='coordinate'] img, "
    ".captcha-image img"
)


class CaptchaSolver:
    """High-level solver bound to one 2Captcha account / setting set."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = TwoCaptchaClient(
            api_key=self.settings.captcha_api_key,
            host=self.settings.captcha_service_host,
            poll_interval=self.settings.captcha_poll_interval,
            poll_max_tries=self.settings.captcha_poll_max_tries,
        )

    # ------------------------------------------------------------------ #
    # public API                                                          #
    # ------------------------------------------------------------------ #

    async def solve(self, url: str, *, force_type: CaptchaType | None = None) -> SolveResult:
        """Open `url`, detect captcha, solve, return structured result."""
        started = asyncio.get_event_loop().time()
        async with browser_page(
            headless=self.settings.headless,
            proxy=self.settings.http_proxy,
        ) as page:
            await page.goto(url, wait_until="networkidle")
            await _human_delay(2, 4)

            detected = force_type or await self.detect(page)
            result = SolveResult(type=detected, page_url=url)

            if detected is CaptchaType.NONE:
                result.solved = True
                result.duration_seconds = asyncio.get_event_loop().time() - started
                return result

            try:
                if detected is CaptchaType.CLICK:
                    token = await self._solve_click(page)
                    result.token = token
                    result.solved = bool(token)
                elif detected is CaptchaType.COORDINATE:
                    points = await self._solve_coordinate(page)
                    result.coordinates = points
                    result.solved = bool(points)
            except TwoCaptchaError as e:
                logger.exception("solver error on %s", url)
                result.error = str(e)
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("unexpected error on %s", url)
                result.error = f"{type(e).__name__}: {e}"

            result.duration_seconds = asyncio.get_event_loop().time() - started
            return result

    # ------------------------------------------------------------------ #
    # detection                                                           #
    # ------------------------------------------------------------------ #

    async def detect(self, page: Page) -> CaptchaType:
        """Classify which captcha (if any) is on the current page."""
        # Coordinate challenge takes priority — SmartCaptcha may also render
        # a sitekey container around the coordinate image.
        if await page.query_selector(_COORDINATE_IMAGE):
            instruction = await _read_instruction(page)
            if instruction and _looks_like_coordinate_instruction(instruction):
                return CaptchaType.COORDINATE

        if await page.query_selector(_SMARTCAPTCHA_CONTAINER):
            return CaptchaType.CLICK

        return CaptchaType.NONE

    # ------------------------------------------------------------------ #
    # click variant                                                       #
    # ------------------------------------------------------------------ #

    async def _solve_click(self, page: Page) -> str:
        # Try free path: emulate a human click on the checkbox. If Yandex
        # accepts without escalation, widget exposes the token directly
        # and we save a 2Captcha call.
        token = await _try_auto_click(page)
        if token:
            logger.info("SmartCaptcha passed by auto-click, 2Captcha not used")
            return token
        logger.info("auto-click did not yield a token, falling back to 2Captcha")

        sitekey = await _extract_sitekey(page)
        if not sitekey:
            raise TwoCaptchaError("could not extract SmartCaptcha sitekey")

        logger.info("SmartCaptcha sitekey=%s…", sitekey[:12])
        async with httpx.AsyncClient(timeout=30) as hc:
            token = await self._client.solve_yandex_smart(sitekey, page.url, client=hc)

        await _inject_token(page, token)
        await _human_delay(2, 5)
        await _submit_captcha_form(page)
        await _human_delay(3, 6)

        if await page.query_selector(_SMARTCAPTCHA_CONTAINER):
            logger.warning("captcha still present after token injection")
        return token

    # ------------------------------------------------------------------ #
    # coordinate variant                                                  #
    # ------------------------------------------------------------------ #

    async def _solve_coordinate(self, page: Page) -> list[Coordinate]:
        image_el = await page.query_selector(_COORDINATE_IMAGE)
        if image_el is None:
            raise TwoCaptchaError("coordinate image element not found")

        box = await image_el.bounding_box()
        if not box:
            raise TwoCaptchaError("could not measure captcha image")

        screenshot_bytes = await image_el.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode("ascii")

        instruction = await _read_instruction(page) or "Click on objects in the correct order"

        async with httpx.AsyncClient(timeout=30) as hc:
            points = await self._client.solve_coordinates(
                image_b64,
                instruction=instruction,
                client=hc,
            )

        logger.info("coordinate solver returned %d points", len(points))
        await _replay_clicks(page, image_el, points)
        await _human_delay(2, 5)
        await _submit_captcha_form(page)
        return points


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

async def _human_delay(lo: float, hi: float) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def _try_auto_click(page: Page) -> str:
    """Attempt to pass SmartCaptcha by clicking the checkbox like a human.

    Yandex analyses mouse trajectory, dwell time, and fingerprint before
    deciding whether to escalate to an image challenge. On low-protection
    pages (invisible mode, residential IP, warm profile) a clean human-like
    click is enough — the widget exposes a token via
    ``window.smartCaptcha.getResponse()`` and no challenge is shown.

    Returns the token on success, empty string if escalation happened or
    the checkbox could not be found.
    """
    # Find the checkbox iframe — SmartCaptcha renders it in its own frame
    checkbox_frame = None
    for frame in page.frames:
        if "checkbox" in frame.url and "captcha" in frame.url:
            checkbox_frame = frame
            break
    if checkbox_frame is None:
        return ""

    try:
        checkbox = await checkbox_frame.query_selector(
            "[role='checkbox'], .CheckboxCaptcha-Button, .CheckboxCaptcha, "
            "button[data-testid='checkbox'], input[type='checkbox']"
        )
        if checkbox is None:
            return ""

        box = await checkbox.bounding_box()
        if not box:
            return ""

        frame_el = await checkbox_frame.frame_element()
        frame_box = await frame_el.bounding_box()
        if not frame_box:
            return ""

        # Target point inside the checkbox, with jitter
        target_x = frame_box["x"] + box["x"] + box["width"] / 2 + random.uniform(-4, 4)
        target_y = frame_box["y"] + box["y"] + box["height"] / 2 + random.uniform(-3, 3)

        # Human-like approach: start off-target, curve towards it with variable speed
        start_x = target_x + random.uniform(-300, 300)
        start_y = target_y + random.uniform(-200, 200)
        await page.mouse.move(start_x, start_y, steps=1)
        await _human_delay(0.3, 0.8)

        # Move in several chunks with easing — Yandex logs the trajectory
        chunks = random.randint(6, 12)
        for i in range(1, chunks + 1):
            t = i / chunks
            # ease-out cubic — fast start, slow at target
            eased = 1 - (1 - t) ** 3
            x = start_x + (target_x - start_x) * eased + random.uniform(-2, 2)
            y = start_y + (target_y - start_y) * eased + random.uniform(-2, 2)
            await page.mouse.move(x, y, steps=1)
            await asyncio.sleep(random.uniform(0.02, 0.08))

        await _human_delay(0.4, 0.9)  # dwell before click
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()

        # Let widget process; challenge iframe appears within ~1-2s if escalated
    except Exception as e:
        logger.debug("auto-click attempt failed: %s", e)
        return ""

    # Poll up to 6s for either token (success) or challenge iframe (escalation)
    for _ in range(12):
        await asyncio.sleep(0.5)
        token = await page.evaluate(
            """
            () => {
                if (window.smartCaptcha && typeof window.smartCaptcha.getResponse === 'function') {
                    const keys = Object.keys(window.smartCaptcha).filter(k => k !== 'getResponse');
                    const r = window.smartCaptcha.getResponse();
                    if (r) return r;
                }
                const ta = document.querySelector(
                    'textarea[name="smart-token"], input[name="smart-token"]'
                );
                return ta && ta.value ? ta.value : '';
            }
            """
        )
        if token:
            return token
        # Check for escalation frame
        for frame in page.frames:
            if "advanced" in frame.url or "challenge" in frame.url:
                return ""
    return ""


async def _extract_sitekey(page: Page) -> str:
    return await page.evaluate(
        """
        () => {
            const el = document.querySelector(
                '[data-sitekey], .smartcaptcha, #smart-captcha, [data-smart-captcha-key]'
            );
            if (el) {
                const sk = el.getAttribute('data-sitekey')
                    || el.getAttribute('data-smart-captcha-key');
                if (sk) return sk;
            }
            const iframe = document.querySelector('iframe[src*="smartcaptcha"]');
            if (iframe) {
                try {
                    const u = new URL(iframe.src);
                    const sk = u.searchParams.get('sitekey');
                    if (sk) return sk;
                } catch (e) {}
            }
            // last resort: regex over HTML
            const m = document.documentElement.outerHTML.match(/sitekey["'\\s:=]+([A-Za-z0-9_\\-]{16,})/);
            return m ? m[1] : '';
        }
        """
    )


async def _inject_token(page: Page, token: str) -> bool:
    """Feed the solver token into SmartCaptcha via any of the known widget APIs."""
    return await page.evaluate(
        """
        (token) => {
            if (window.smartCaptcha && typeof window.smartCaptcha.setToken === 'function') {
                window.smartCaptcha.setToken(token);
                return true;
            }
            const ta = document.querySelector(
                'textarea[name="smart-token"], input[name="smart-token"], [name="g-recaptcha-response"]'
            );
            if (ta) {
                ta.value = token;
                ta.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            const callbacks = Object.keys(window).filter(k => k.startsWith('smartCaptchaCallback'));
            if (callbacks.length > 0) {
                window[callbacks[0]](token);
                return true;
            }
            return false;
        }
        """,
        token,
    )


async def _submit_captcha_form(page: Page) -> None:
    await page.evaluate(
        """
        () => {
            const form = document.querySelector(
                'form:has(.smartcaptcha), form:has([data-sitekey]), form:has(#smart-captcha)'
            );
            if (!form) return false;
            const btn = form.querySelector('button[type="submit"]');
            if (btn) { btn.click(); return true; }
            form.submit();
            return true;
        }
        """
    )


async def _read_instruction(page: Page) -> str:
    """Try to read the visible instruction text ('Click the cars in order')."""
    for selector in (
        ".CaptchaInstructions", ".captcha__instructions",
        "[class*='instruction']", "[class*='Instruction']",
    ):
        el = await page.query_selector(selector)
        if el:
            try:
                text = (await el.inner_text()).strip()
                if text:
                    return text
            except Exception:
                continue
    return ""


def _looks_like_coordinate_instruction(text: str) -> bool:
    low = text.lower()
    markers = ("нажм", "кликн", "выбер", "укаж", "click", "select", "tap", "по очер")
    return any(m in low for m in markers)


async def _replay_clicks(
    page: Page,
    image_el: ElementHandle,
    points: list[Coordinate],
) -> None:
    """Replay solver coordinates with human-like pacing relative to image origin."""
    box = await image_el.bounding_box()
    if not box:
        raise TwoCaptchaError("image bounding box unavailable")
    for point in points:
        abs_x = box["x"] + point.x + random.uniform(-2, 2)
        abs_y = box["y"] + point.y + random.uniform(-2, 2)
        await page.mouse.move(abs_x, abs_y, steps=random.randint(8, 20))
        await _human_delay(0.2, 0.6)
        await page.mouse.click(abs_x, abs_y)
        await _human_delay(0.4, 1.2)
