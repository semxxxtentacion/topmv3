"""CLI for live testing: `python -m captcha_solver.cli <url>`.

Uses CAPTCHA_API_KEY from .env / environment, opens a browser, solves,
prints JSON. Set HEADLESS=false to watch the solve happen.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from captcha_solver.config import Settings
from captcha_solver.solver import CaptchaSolver, CaptchaType


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="captcha_solver.cli",
        description="Solve a Yandex SmartCaptcha on a live URL and print result.",
    )
    p.add_argument("url", help="Page URL with captcha")
    p.add_argument(
        "--type",
        choices=[t.value for t in CaptchaType if t is not CaptchaType.NONE],
        default=None,
        help="Force captcha type (default: auto-detect)",
    )
    p.add_argument(
        "--api-key",
        default=os.environ.get("CAPTCHA_API_KEY", ""),
        help="2Captcha API key (default: CAPTCHA_API_KEY env)",
    )
    p.add_argument("--proxy", default=os.environ.get("HTTP_PROXY", ""))
    p.add_argument("--headed", action="store_true", help="Show the browser (not headless)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    if not args.api_key:
        print("error: CAPTCHA_API_KEY is empty (pass --api-key or set env)", file=sys.stderr)
        return 2

    settings = Settings(
        captcha_api_key=args.api_key,
        headless=not args.headed,
        http_proxy=args.proxy,
    )
    solver = CaptchaSolver(settings)
    force = CaptchaType(args.type) if args.type else None
    result = await solver.solve(args.url, force_type=force)
    payload = {
        "type": result.type.value,
        "solved": result.solved,
        "token": result.token,
        "coordinates": [{"x": c.x, "y": c.y} for c in result.coordinates],
        "duration_seconds": round(result.duration_seconds, 2),
        "error": result.error,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.solved else 1


def main() -> None:
    args = _parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
