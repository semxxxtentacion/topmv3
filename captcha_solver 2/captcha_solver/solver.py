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
    CLICK = "click"                       # standard Yandex SmartCaptcha (sitekey + token)
    COORDINATE = "coordinate"             # image-based coordinate challenge
    YANDEX_CLASSIC = "yandex_classic"     # legacy Yandex CheckboxCaptcha (ya.ru/showcaptcha)
    NONE = "none"                          # no captcha detected on page


@dataclass(slots=True)
class SolveResult:
    type: CaptchaType
    token: str = ""
    coordinates: list[Coordinate] = field(default_factory=list)
    cookies: list[dict] = field(default_factory=list)   # для YANDEX_CLASSIC: session cookies (spravka, yandexuid)
    solved: bool = False
    page_url: str = ""
    final_url: str = ""                                  # URL после прохождения капчи (для классической)
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

# Классическая Yandex CheckboxCaptcha (ya.ru/showcaptcha?cc=1).
# Двухфазная: сначала кнопка «Я не робот», после — картинка с искажённым русским текстом.
_YANDEX_CLASSIC_CONTAINER = (
    "[data-testid='checkbox-captcha'], .CheckboxCaptcha, "
    "#js-button.CheckboxCaptcha-Button, .CheckboxCaptcha-Button"
)
_YANDEX_CLASSIC_CHECKBOX = (
    "#js-button, .CheckboxCaptcha-Button, [data-testid='checkbox-captcha'] input[type='button']"
)
_YANDEX_CLASSIC_IMAGE = (
    ".AdvancedCaptcha-Image, img.AdvancedCaptcha__image, "
    "[class*='AdvancedCaptcha'] img, .captcha__image-wrapper img, "
    "img[src*='captcha-image']"
)
_YANDEX_CLASSIC_INPUT = (
    "input[name='rep'], input.Textinput-Control, input.AdvancedCaptcha-Input, "
    "[class*='AdvancedCaptcha'] input[type='text'], #js-rep, "
    "form input[type='text'], form input:not([type])"        # широкий fallback
)
_YANDEX_CLASSIC_SUBMIT = (
    "button[data-testid='submit'], "
    "button.CaptchaButton.CaptchaButton_view_action, "        # «Отправить» — action-вариант
    "button.Button2_view_action, "
    "button[type='submit']"
    # NB: НЕ берём .CaptchaButton_view_clear — это «крестик» обновления капчи!
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
        keep = getattr(self.settings, "keep_open_seconds", 0)
        # Отдельная папка для дампов этой капчи
        from datetime import datetime
        from pathlib import Path
        dump_dir = Path("data/captcha_dumps") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / "url.txt").write_text(url, encoding="utf-8")
        except Exception:
            pass
        self._current_dump_dir = dump_dir
        logger.info("=== captcha dump dir: %s ===", dump_dir)
        async with browser_page(
            headless=self.settings.headless,
            proxy=self.settings.http_proxy,
            disable_stealth=getattr(self.settings, "disable_stealth", False),
        ) as page:
            try:
                await page.goto(url, wait_until="networkidle")
            except Exception as e:
                logger.warning("goto failed: %s", e)

            # Yandex /showcaptchafast — промежуточный JS-редирект на /showcaptcha с виджетом.
            # Без этого ожидания detect срабатывает на пустой странице.
            if "showcaptchafast" in page.url.lower():
                try:
                    await page.wait_for_function(
                        "() => !location.pathname.toLowerCase().includes('showcaptchafast')",
                        timeout=20000,
                    )
                except Exception:
                    logger.warning("showcaptchafast did not redirect within 20s")
                # Виджету ещё нужно отрендериться после редиректа
                await page.wait_for_timeout(2000)

            await _human_delay(2, 4)

            detected = force_type or await self.detect(page)
            result = SolveResult(type=detected, page_url=url)

            if detected is CaptchaType.NONE:
                # Bug fix: если URL похож на капча-страницу (/showcaptcha), но виджет
                # не нашёлся — это НЕ успех. Возвращаем solved=False с понятной ошибкой,
                # чтобы парсер не считал что капча решена.
                if "showcaptcha" in url.lower() or "captcha" in page.url.lower():
                    result.solved = False
                    result.error = "captcha page detected by URL but no known widget found"
                else:
                    result.solved = True
                result.final_url = page.url
                result.duration_seconds = asyncio.get_event_loop().time() - started
                if keep > 0:
                    logger.info("keeping browser open for %ds (debug)", keep)
                    await asyncio.sleep(keep)
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
                elif detected is CaptchaType.YANDEX_CLASSIC:
                    ok = await self._solve_yandex_classic(page)
                    result.solved = ok
                    if ok:
                        # Главный ценный артефакт классической капчи — cookies (spravka, yandexuid).
                        # Парсер инжектит их в свой контекст через context.add_cookies(...).
                        result.cookies = await page.context.cookies()
            except TwoCaptchaError as e:
                logger.exception("solver error on %s", url)
                result.error = str(e)
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("unexpected error on %s", url)
                result.error = f"{type(e).__name__}: {e}"

            result.final_url = page.url
            result.duration_seconds = asyncio.get_event_loop().time() - started
            # Debug: pause before closing so a human can inspect the result window
            if keep > 0:
                logger.info("keeping browser open for %ds (debug)", keep)
                await asyncio.sleep(keep)
            return result

    # ------------------------------------------------------------------ #
    # detection                                                           #
    # ------------------------------------------------------------------ #

    async def detect(self, page: Page) -> CaptchaType:
        """Classify which captcha (if any) is on the current page."""
        # Yandex classic CheckboxCaptcha — приоритет, т.к. в 90% случаев Яндекс
        # отдаёт именно её, а не SmartCaptcha.
        if await page.query_selector(_YANDEX_CLASSIC_CONTAINER):
            return CaptchaType.YANDEX_CLASSIC

        # Coordinate challenge — SmartCaptcha может оборачивать coordinate image.
        if await page.query_selector(_COORDINATE_IMAGE):
            instruction = await _read_instruction(page)
            if instruction and _looks_like_coordinate_instruction(instruction):
                return CaptchaType.COORDINATE

        if await page.query_selector(_SMARTCAPTCHA_CONTAINER):
            return CaptchaType.CLICK

        # Если URL — капча-страница, но виджет не отрендерился: подождём и retry.
        if "showcaptcha" in page.url.lower():
            await page.wait_for_timeout(3000)
            if await page.query_selector(_YANDEX_CLASSIC_CONTAINER):
                return CaptchaType.YANDEX_CLASSIC
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

    async def _solve_yandex_classic_phase2_attempt(self, page: Page, start_url: str, attempt: int) -> bool:
        """Одна попытка решить эскалированную silhouette-капчу через Rucaptcha v2.

        Возвращает True если капча пройдена. False если клики не сработали
        (Яндекс показал новую картинку для следующей попытки).
        """
        click_area = await page.query_selector(".AdvancedCaptcha-ImageWrapper")
        instr_area = await page.query_selector(".AdvancedCaptcha-SilhouetteTask, .AdvancedCaptcha-Footer")
        if click_area is None:
            click_area = await page.query_selector("form")
        if click_area is None:
            logger.warning("yandex classic phase2: no .AdvancedCaptcha-ImageWrapper")
            return False
        click_box = await click_area.bounding_box()
        click_b64 = base64.b64encode(await click_area.screenshot()).decode("ascii")
        instr_b64 = None
        if instr_area is not None:
            instr_b64 = base64.b64encode(await instr_area.screenshot()).decode("ascii")

        instruction = await page.evaluate("""() => {
            const candidates = [];
            document.querySelectorAll('.AdvancedCaptcha *, form *').forEach(el => {
                const t = (el.innerText || '').trim();
                if (!t || t.length < 5 || t.length > 200) return;
                if (/нажм|кликн|выбер|порядк|укаж|тако|click|select|tap|order/i.test(t)) {
                    candidates.push(t);
                }
            });
            return candidates.sort((a,b) => a.length - b.length)[0] || '';
        }""")
        # Жёсткий, конкретный comment для работника Rucaptcha
        comment = (
            "Yandex SmartCaptcha task (silhouette). "
            "На главной картинке (BODY) спрятаны те же предметы что показаны в эталоне (imgInstructions). "
            "Найдите эти предметы на главной картинке и кликните по ним В ТОМ ЖЕ ПОРЯДКЕ что в эталоне (слева направо). "
            "Кликайте именно по предметам, не по фону. "
        )
        if instruction:
            comment += f"Инструкция Яндекса: «{instruction}». "
        logger.info(
            "phase2 attempt %d: click_area=%dx%d has_instructions=%s instruction=%r",
            attempt, int(click_box["width"]), int(click_box["height"]), bool(instr_b64), (instruction or "—")[:60],
        )

        # Дамп для отладки (per attempt) — в папку этой капчи
        dd = getattr(self, "_current_dump_dir", None)
        try:
            if dd:
                await click_area.screenshot(path=str(dd / f"a{attempt}_body.png"))
                if instr_area:
                    await instr_area.screenshot(path=str(dd / f"a{attempt}_instructions.png"))
                (dd / f"a{attempt}_comment.txt").write_text(comment, encoding="utf-8")
                await page.screenshot(path=str(dd / f"a{attempt}_full_before_click.png"), full_page=True)
        except Exception as e:
            logger.debug("dump phase2 attempt failed: %s", e)

        async with httpx.AsyncClient(timeout=30) as hc:
            try:
                points = await self._client.solve_coordinates_v2(
                    click_b64,
                    img_instructions_base64=instr_b64,
                    comment=comment,
                    min_clicks=2, max_clicks=8,
                    client=hc,
                )
            except TwoCaptchaError as e:
                logger.warning("phase2 attempt %d: 2Captcha err: %s", attempt, e)
                return False
        logger.info("phase2 attempt %d: got %d points: %s", attempt, len(points),
                    [(p.x, p.y) for p in points])
        try:
            if dd:
                import json as _json
                (dd / f"a{attempt}_coords.json").write_text(
                    _json.dumps([{"x": p.x, "y": p.y} for p in points], indent=2),
                    encoding="utf-8",
                )
                # Визуализация кликов на body.png — увидим попали ли в силуэты
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    body_path = dd / f"a{attempt}_body.png"
                    if body_path.exists():
                        img = Image.open(body_path).convert("RGB")
                        draw = ImageDraw.Draw(img)
                        for i, p in enumerate(points, 1):
                            r = 14
                            draw.ellipse((p.x - r, p.y - r, p.x + r, p.y + r),
                                         outline=(255, 0, 0), width=3)
                            draw.text((p.x + r + 2, p.y - r), str(i), fill=(255, 0, 0))
                        img.save(dd / f"a{attempt}_clicks_overlay.png")
                except Exception as _e:
                    logger.debug("overlay viz failed: %s", _e)
        except Exception:
            pass

        # Кликаем по абсолютным координатам страницы
        for point in points:
            abs_x = click_box["x"] + point.x + random.uniform(-2, 2)
            abs_y = click_box["y"] + point.y + random.uniform(-2, 2)
            await page.mouse.move(abs_x, abs_y, steps=random.randint(8, 20))
            await _human_delay(0.2, 0.5)
            await page.mouse.click(abs_x, abs_y)
            await _human_delay(0.4, 1.0)

        # Пауза после последнего клика по силуэту — даём виджету «осознать»
        await _human_delay(1.5, 2.5)

        # Кнопка «Отправить» — строго .CaptchaButton_view_action, никогда _view_clear (крестик)
        submit_clicked = False
        for sel in [
            "button.CaptchaButton.CaptchaButton_view_action",
            "button[data-testid='submit']",
            "button.Button2_view_action",
            "button[type='submit']",
        ]:
            loc = page.locator(sel).filter(visible=True).first
            try:
                await loc.wait_for(state="visible", timeout=2000)
                # Проверим что это НЕ кнопка обновления
                cls = (await loc.get_attribute("class")) or ""
                if "view_clear" in cls.lower() or "centered" in cls.lower():
                    continue
                txt = (await loc.inner_text() or "").strip()[:30]
                await loc.click()
                logger.info("phase2 attempt %d: clicked submit '%s' (selector: %s)",
                            attempt, txt, sel)
                submit_clicked = True
                break
            except Exception:
                continue
        if not submit_clicked:
            logger.warning("phase2 attempt %d: no submit button found", attempt)

        # Ожидаем success или новую картинку
        for _ in range(16):  # ~8s
            await asyncio.sleep(0.5)
            if await _yandex_classic_passed(page, start_url):
                logger.info("phase2 attempt %d: PASSED; final_url=%s", attempt, page.url[:120])
                try:
                    if dd:
                        await page.screenshot(path=str(dd / f"a{attempt}_PASSED.png"), full_page=True)
                        (dd / "result.txt").write_text(f"PASSED on attempt {attempt}\nfinal_url={page.url}", encoding="utf-8")
                except Exception:
                    pass
                return True
        logger.warning("phase2 attempt %d: failed; final_url=%s", attempt, page.url[:120])
        try:
            if dd:
                await page.screenshot(path=str(dd / f"a{attempt}_FAILED.png"), full_page=True)
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ #
    # Yandex classic CheckboxCaptcha (ya.ru/showcaptcha)                  #
    # ------------------------------------------------------------------ #

    async def _solve_yandex_classic(self, page: Page) -> bool:
        """Two-phase: 1) human-click checkbox; 2) if image escalates — OCR via 2Captcha.

        Success markers (any one is enough):
        - URL changed away from /showcaptcha
        - cookie `spravka` issued by ya.ru
        - checkbox/image widgets disappeared

        On success, caller picks up cookies via `page.context.cookies()`.
        """
        start_url = page.url

        # === Phase 1: human click on the "I'm not a robot" checkbox ===
        clicked = await _human_click(page, _YANDEX_CLASSIC_CHECKBOX)
        if not clicked:
            raise TwoCaptchaError("yandex classic: checkbox button not found")

        # Дать DOM стабилизироваться: после клика Яндекс через AJAX либо отдаёт
        # success, либо подгружает image. Без этой паузы возможен false-positive
        # «нет виджетов» в коротком окне между удалением checkbox и появлением image.
        await asyncio.sleep(1.5)

        # Wait for either: escalation to image (приоритет) или success.
        for _ in range(20):  # up to ~10s
            await asyncio.sleep(0.5)
            # Сначала проверяем эскалацию — это надёжный сигнал «нужна фаза 2»
            if await page.query_selector(_YANDEX_CLASSIC_IMAGE):
                logger.info("yandex classic: escalated to image challenge")
                break
            # Потом — реальный success (URL изменился или есть spravka cookie)
            if await _yandex_classic_passed(page, start_url):
                logger.info("yandex classic: passed by checkbox click alone")
                return True

        # === Phase 2: image challenge ===
        image_el = await page.query_selector(_YANDEX_CLASSIC_IMAGE)
        if image_el is None:
            logger.warning("yandex classic: no image after click, page may need different handling")
            return await _yandex_classic_passed(page, start_url)

        # ВАЖНО: современная фаза 2 у Яндекса бывает разной:
        #   а) Текстовая — есть видимый <input type=text> для ввода ответа.
        #   б) Координатная (или click-task) — нет видимого input, всё через клики.
        # Определяем по наличию видимого text-input в форме.
        has_visible_input = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('form input[type="text"], form input:not([type])');
            for (const el of inputs) {
                if (el.offsetWidth > 0 && el.offsetHeight > 0) return true;
            }
            return false;
        }""")

        # Дамп DOM на эскалированной странице — ценно для диагностики неизвестных вариантов
        try:
            await page.screenshot(path="data/phase2_debug.png", full_page=True)
            from pathlib import Path as _P
            _P("data/phase2_debug.html").write_text(await page.content(), encoding="utf-8")
            logger.info("yandex classic: phase2 dump → data/phase2_debug.{png,html}")
        except Exception as _e:
            logger.debug("phase2 dump failed: %s", _e)

        screenshot_bytes = await image_el.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode("ascii")

        if not has_visible_input:
            # Координатная задача (Yandex AdvancedCaptcha — silhouette/click-objects).
            # Retry: после неверных кликов Яндекс показывает НОВУЮ картинку.
            # Делаем до 3 попыток (>3 = расход денег без шансов).
            for attempt in range(1, 4):
                ok = await self._solve_yandex_classic_phase2_attempt(page, start_url, attempt)
                if ok:
                    return True
                # Подождать пока Яндекс отрендерит новую картинку
                await asyncio.sleep(2)
                still_image = await page.query_selector(_YANDEX_CLASSIC_IMAGE)
                if not still_image:
                    logger.warning("yandex classic: no new image after attempt %d, giving up", attempt)
                    break
                logger.info("yandex classic: new image appeared, retry attempt %d", attempt + 1)
            return False

        # Иначе — текстовая капча (старое поведение)
        async with httpx.AsyncClient(timeout=30) as hc:
            text = await self._client.solve_text_image(
                image_b64,
                language=2,        # ru
                regsense=1,        # capitals matter for Cyrillic
                client=hc,
            )

        text = (text or "").strip()
        if not text:
            raise TwoCaptchaError("yandex classic: 2Captcha returned empty text")
        logger.info("yandex classic: OCR text = %r", text[:30])

        # Ищем именно ВИДИМЫЙ input — Яндекс рендерит несколько input'ов
        # (скрытые сервисные), наш через query_selector брал первый скрытый.
        input_loc = page.locator(_YANDEX_CLASSIC_INPUT).filter(visible=True).first
        try:
            await input_loc.wait_for(state="visible", timeout=8000)
        except Exception as e:
            # Debug: что вообще есть на странице из текстовых полей
            try:
                dbg = await page.evaluate("""() => Array.from(document.querySelectorAll('input')).map(el => ({
                    type: el.type, name: el.name, id: el.id, cls: el.className.slice(0, 80),
                    visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                }))""")
                logger.warning("yandex classic: visible input not found. Inputs on page: %s", dbg)
                await page.screenshot(path="/tmp/cs_phase2_failed.png", full_page=True)
            except Exception:
                pass
            raise TwoCaptchaError(f"yandex classic: visible input not found: {e}")
        await input_loc.click()
        await _human_delay(0.3, 0.7)
        # Печать с задержкой между символами — анти-бот Яндекса смотрит на ритм.
        await input_loc.type(text, delay=random.randint(70, 140))
        await _human_delay(0.4, 0.9)

        submit_loc = page.locator(_YANDEX_CLASSIC_SUBMIT).filter(visible=True).first
        try:
            await submit_loc.wait_for(state="visible", timeout=5000)
        except Exception as e:
            raise TwoCaptchaError(f"yandex classic: visible submit not found: {e}")
        await submit_loc.click()

        # Wait for navigation / success markers.
        for _ in range(20):  # up to ~10s
            await asyncio.sleep(0.5)
            if await _yandex_classic_passed(page, start_url):
                logger.info("yandex classic: passed after OCR submit")
                return True

        logger.warning("yandex classic: still on captcha page after submit")
        return False


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


async def _human_click(page: Page, selector: str) -> bool:
    """Mouse-trajectory click on the page-level element (not iframe). Returns False if not found."""
    el = await page.query_selector(selector)
    if el is None:
        return False
    try:
        box = await el.bounding_box()
        if not box:
            return False
        target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
        target_y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
        start_x = target_x + random.uniform(-300, 300)
        start_y = target_y + random.uniform(-200, 200)
        await page.mouse.move(start_x, start_y, steps=1)
        await _human_delay(0.2, 0.6)
        chunks = random.randint(6, 12)
        for i in range(1, chunks + 1):
            t = i / chunks
            eased = 1 - (1 - t) ** 3   # ease-out cubic
            x = start_x + (target_x - start_x) * eased + random.uniform(-2, 2)
            y = start_y + (target_y - start_y) * eased + random.uniform(-2, 2)
            await page.mouse.move(x, y, steps=1)
            await asyncio.sleep(random.uniform(0.02, 0.08))
        await _human_delay(0.3, 0.8)
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()
        return True
    except Exception as e:
        logger.debug("human_click failed for %s: %s", selector, e)
        return False


async def _yandex_classic_passed(page: Page, start_url: str) -> bool:
    """Строгая проверка реального прохождения капчи.

    Прошлые «мягкие» сигналы давали false-positive:
      - cookie `spravka` ставится Яндексом как session-id ЕЩЁ ДО решения
      - виджет может исчезнуть на 1-2 сек пока Яндекс рендерит НОВУЮ капчу
      - URL может слегка измениться (mt=timestamp) даже без прохождения

    Единственный 100% надёжный сигнал: URL ушёл с любого `*captcha*` и заголовок
    не «Вы не робот?» (это title капча-страниц Яндекса).
    """
    try:
        cur = page.url.lower()
        if "captcha" in cur:
            return False  # любой URL с captcha = ещё на капче
        # URL без captcha — проверим title для дополнительной уверенности
        title = (await page.title()).lower()
        if "не робот" in title or "captcha" in title or "подтвердите" in title:
            return False
        return True
    except Exception:
        return False
