"""
Human-like browser interaction helpers.
Adds realistic delays, mouse movements, typing, and scrolling.
"""

from __future__ import annotations

import asyncio
import random

_mouse_config: dict | None = None


def set_mouse_config(config: dict | None):
    global _mouse_config
    _mouse_config = config


async def pause(min_sec: float, max_sec: float):
    """Sleep for a random duration between min and max seconds."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def click(page, selector: str):
    """Click an element with a small random delay and offset."""
    try:
        el = await page.wait_for_selector(selector, timeout=5000)
        if not el:
            return
        box = await el.bounding_box()
        if box:
            # Click with slight random offset from center
            x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            await page.mouse.click(x, y, delay=random.randint(50, 150))
        else:
            await el.click(delay=random.randint(50, 150))
    except Exception:
        try:
            await page.click(selector, delay=random.randint(50, 150))
        except Exception:
            pass


async def type_text(page, selector: str, text: str):
    """Type text character by character with human-like delays."""
    try:
        el = await page.wait_for_selector(selector, timeout=5000)
        if not el:
            return
        for char in text:
            await el.type(char, delay=random.randint(30, 120))
            # Occasional longer pause (thinking)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.2, 0.5))
    except Exception:
        try:
            await page.fill(selector, text)
        except Exception:
            pass


async def scroll(page, direction: str = "down", amount: int = 300):
    """Scroll the page with realistic behavior."""
    delta = amount if direction == "down" else -amount
    # Split into smaller scroll steps
    steps = random.randint(2, 4)
    per_step = delta / steps
    for _ in range(steps):
        await page.mouse.wheel(0, per_step + random.uniform(-20, 20))
        await asyncio.sleep(random.uniform(0.05, 0.15))
