from __future__ import annotations

"""
Human-like browser interaction: mouse movement, typing, scrolling.
Uses Bezier curves for mouse paths and gaussian delays for typing.

mouse_config from profile DB adjusts behavior per-profile:
  { "speed": 1.0, "jitter": 1.0, "click_delay": 1.0, "type_speed": 1.0 }
  Values are multipliers: 1.0 = default, 0.5 = faster, 2.0 = slower.
"""

import asyncio
import contextvars
import random
import logging

logger = logging.getLogger(__name__)

_mcfg_var: contextvars.ContextVar[dict] = contextvars.ContextVar('_mcfg', default={})


def set_mouse_config(cfg: dict | None):
    _mcfg_var.set(cfg if isinstance(cfg, dict) else {})


def _speed() -> float:
    return max(0.2, float(_mcfg_var.get().get('speed', 1.0)))


def _jitter() -> float:
    return max(0.1, float(_mcfg_var.get().get('jitter', 1.0)))


def _click_delay() -> float:
    return max(0.1, float(_mcfg_var.get().get('click_delay', 1.0)))


def _type_speed() -> float:
    return max(0.2, float(_mcfg_var.get().get('type_speed', 1.0)))


def _bezier_points(start: tuple, end: tuple, n_control: int = 2) -> list[tuple]:
    jit = _jitter()
    spread = 50 * jit
    controls = []
    for _ in range(n_control):
        cx = start[0] + (end[0] - start[0]) * random.uniform(0.15, 0.85) + random.uniform(-spread, spread)
        cy = start[1] + (end[1] - start[1]) * random.uniform(0.15, 0.85) + random.uniform(-spread, spread)
        controls.append((cx, cy))

    all_pts = [start] + controls + [end]
    n = len(all_pts) - 1
    steps = random.randint(12, 28)
    result = [start]

    for i in range(1, steps + 1):
        t = i / steps
        temp = list(all_pts)
        for _ in range(n):
            temp = [
                (temp[j][0] * (1 - t) + temp[j + 1][0] * t,
                 temp[j][1] * (1 - t) + temp[j + 1][1] * t)
                for j in range(len(temp) - 1)
            ]
        result.append(temp[0])

    return result


async def move_mouse(page, to_x: float, to_y: float):
    try:
        pos = await page.evaluate('({ x: window.__mouseX || 0, y: window.__mouseY || 0 })')
        from_x, from_y = pos.get('x', 0), pos.get('y', 0)
    except Exception:
        from_x, from_y = random.randint(100, 500), random.randint(100, 400)

    spd = _speed()
    for px, py in _bezier_points((from_x, from_y), (to_x, to_y)):
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.004, 0.022) * spd)


async def click(page, selector: str | None = None, x: float | None = None, y: float | None = None) -> bool:
    try:
        if selector:
            el = await page.wait_for_selector(selector, timeout=5000)
            box = await el.bounding_box()
            if not box:
                return False
            tx = box['x'] + box['width'] * random.uniform(0.15, 0.85)
            ty = box['y'] + box['height'] * random.uniform(0.2, 0.8)
        elif x is not None and y is not None:
            tx, ty = x, y
        else:
            return False

        await move_mouse(page, tx, ty)
        cd = _click_delay()
        await asyncio.sleep(random.uniform(0.04, 0.14) * cd)
        await page.mouse.click(tx, ty)
        return True
    except Exception as e:
        logger.debug(f"Click failed: {e}")
        return False


async def click_element(page, element) -> bool:
    try:
        box = await element.bounding_box()
        if not box:
            return False
        tx = box['x'] + box['width'] * random.uniform(0.15, 0.85)
        ty = box['y'] + box['height'] * random.uniform(0.2, 0.8)
        await move_mouse(page, tx, ty)
        cd = _click_delay()
        await asyncio.sleep(random.uniform(0.04, 0.14) * cd)
        await page.mouse.click(tx, ty)
        return True
    except Exception as e:
        logger.debug(f"click_element failed: {e}")
        return False


async def type_text(page, selector: str, text: str, clear_first: bool = True):
    if clear_first:
        await page.click(selector, click_count=3)
        await asyncio.sleep(random.uniform(0.05, 0.15))

    ts = _type_speed()
    for char in text:
        await page.type(selector, char, delay=0)
        delay = max(0.03, min(0.35, random.gauss(0.12, 0.04) * ts))
        await asyncio.sleep(delay)


async def type_text_keyboard(page, text: str):
    """Type text using raw keyboard events — bypasses any DOM overlays.
    The target element must already be focused (e.g. via JS focus()).
    """
    ts = _type_speed()
    for char in text:
        await page.keyboard.type(char)
        delay = max(0.03, min(0.35, random.gauss(0.12, 0.04) * ts))
        await asyncio.sleep(delay)


async def scroll(page, direction: str = 'down', amount: int | None = None):
    if amount is None:
        amount = random.randint(200, 600)

    delta = amount if direction == 'down' else -amount
    steps = random.randint(3, 7)
    step_size = delta / steps
    spd = _speed()

    for _ in range(steps):
        await page.mouse.wheel(0, step_size + random.uniform(-15, 15))
        await asyncio.sleep(random.uniform(0.02, 0.07) * spd)

    await asyncio.sleep(random.uniform(0.2, 0.6) * spd)


async def pause(min_s: float = 0.5, max_s: float = 2.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def idle_mouse(page, duration: float = 2.0):
    jit = _jitter()
    spread = 25 * jit
    deadline = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < deadline:
        try:
            pos = await page.evaluate('({ x: window.__mouseX || 300, y: window.__mouseY || 300 })')
            nx = max(10, min(1900, pos['x'] + random.uniform(-spread, spread)))
            ny = max(10, min(1000, pos['y'] + random.uniform(-spread, spread)))
            await page.mouse.move(nx, ny)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.3, 0.9) * _speed())
