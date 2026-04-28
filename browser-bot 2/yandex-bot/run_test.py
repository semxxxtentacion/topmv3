"""
Smoke test for Yandex PF bot.

Loads a warm profile (with Yandex cookies) from generated_profiles/,
connects through mobile proxy, verifies IP, runs one search scenario.

Usage:
    python run_test.py                     # visible browser
    python run_test.py --headless          # no window
    python run_test.py --keyword "фраза"   # override keyword
"""

import asyncio
import json
import random
import logging
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from playwright.async_api import async_playwright
from stealth import build_stealth_js
from worker import _prepare_cookies, _build_context_options
import human
import scenario

# ── Mobile proxy (Krasnodar) ──────────────────────────────────
PROXY_SERVER = "http://93.190.141.57:443"
PROXY_USER = "3st7bf1yju-corp.mobile.res-country-RU-state-542415-city-542420-hold-query"
PROXY_PASS = "No97KkjsxtIvYGAH"
IP_CHECK_URL = "https://i.pn"

PROXY_GEO = {
    "city": "Краснодар",
    "latitude": 45.0355,
    "longitude": 38.9753,
    "timezone": "Europe/Moscow",
}

TASK_FILE = BASE_DIR / "test_request.json"
PROFILES_DIR = BASE_DIR / "generated_profiles"

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_test")

G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[94m"
X = "\033[0m"


def load_profile() -> dict:
    """Pick a random warm profile with cookies from the latest profiles file."""
    files = sorted(PROFILES_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No profile files in {PROFILES_DIR}")

    with open(files[-1], "r", encoding="utf-8") as f:
        profiles = json.load(f)

    warm = [p for p in profiles if p.get("warm") and len(p.get("cookies", [])) > 5]
    if warm:
        return random.choice(warm)

    profiles.sort(key=lambda p: len(p.get("cookies", [])), reverse=True)
    return profiles[0]


def _patch_geo(profile: dict):
    """Override profile geo/timezone to match the proxy IP location."""
    profile["geo"] = {
        "city": PROXY_GEO["city"],
        "latitude": PROXY_GEO["latitude"],
        "longitude": PROXY_GEO["longitude"],
        "timezone": PROXY_GEO["timezone"],
    }
    fp = profile.get("fingerprints")
    if isinstance(fp, dict):
        fp["timezone"] = {"id": PROXY_GEO["timezone"]}
        fp["geolocation"] = {
            "latitude": PROXY_GEO["latitude"],
            "longitude": PROXY_GEO["longitude"],
        }


async def run(headless: bool = False, keyword_override: str | None = None):
    # ── 1. Warm profile ───────────────────────────────────────
    profile = load_profile()
    _patch_geo(profile)
    cookies_raw = profile.get("cookies", [])

    print(f"\n{B}Profile:{X}  {profile.get('device_name', '?')}")
    print(f"{B}Browser:{X}  Chrome/{profile['browser_version']}")
    print(f"{B}City:{X}     {PROXY_GEO['city']} (matched to proxy IP)")
    print(f"{B}Cookies:{X}  {len(cookies_raw)}")

    # ── 2. Task ───────────────────────────────────────────────
    with open(TASK_FILE, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    keyword = keyword_override or random.choice(task_data["keywords"])
    site = task_data["site"]
    task = {"site": site, "keyword": keyword, "region": ""}

    print(f"\n{B}Site:{X}     {site}")
    print(f"{B}Keyword:{X}  {keyword}\n")

    # ── 3. Launch browser ─────────────────────────────────────
    proxy_cfg = {
        "server": PROXY_SERVER,
        "username": PROXY_USER,
        "password": PROXY_PASS,
    }

    async with async_playwright() as pw:
        logger.info(f"Launching Chromium (headless={headless})...")

        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        try:
            browser = await pw.chromium.launch(
                headless=headless, args=launch_args, proxy=proxy_cfg,
            )
        except Exception as e:
            if "headless_shell" in str(e) and headless:
                launch_args.insert(0, "--headless")
                browser = await pw.chromium.launch(
                    headless=False, args=launch_args, proxy=proxy_cfg,
                )
            else:
                raise

        # ── 4. Context with profile fingerprint ───────────────
        ctx_opts = _build_context_options(profile)
        context = await browser.new_context(**ctx_opts)
        await context.add_init_script(build_stealth_js(profile))

        # ── 5. Restore cookies ────────────────────────────────
        cookies = _prepare_cookies(profile)
        if cookies:
            try:
                await context.add_cookies(cookies)
                logger.info(f"Restored {len(cookies)} cookies")
            except Exception as e:
                logger.warning(f"Cookie restore partial: {e}")

        page = await context.new_page()
        human.set_mouse_config(profile.get("mouse_config"))

        # ── 6. Check proxy IP ─────────────────────────────────
        logger.info(f"Checking proxy IP via {IP_CHECK_URL}...")
        try:
            await page.goto(IP_CHECK_URL, wait_until="domcontentloaded", timeout=30000)
            body = await page.inner_text("body")
            ip_line = body.strip().split("\n")[0].strip()
            print(f"{G}Proxy IP: {ip_line}{X}\n")
        except Exception as e:
            print(f"\n{R}Proxy check FAILED: {e}{X}")
            print(f"{R}Check proxy credentials or try again later.{X}\n")
            await browser.close()
            return None

        # ── 7. Yandex scenario ────────────────────────────────
        logger.info(f"Starting scenario: '{keyword}' → {site}")
        try:
            result = await asyncio.wait_for(
                scenario.run(page, task), timeout=300,
            )
        except asyncio.TimeoutError:
            result = {"status": "timeout", "task": task}
        except Exception as e:
            result = {"status": "error", "task": task, "error": str(e)}
            logger.error(f"Scenario error: {e}", exc_info=True)

        # ── 8. Report ─────────────────────────────────────────
        status = result.get("status", "unknown")
        serp = result.get("serp_page", "?")

        print("\n" + "=" * 60)
        if status == "success":
            print(f"  {G}SUCCESS{X} — found '{site}' on SERP page {serp}")
            print(f"  Keyword:    {keyword}")
            print(f"  Landed URL: {result.get('landed_url', '?')}")
        elif status == "not_found":
            print(f"  {Y}NOT FOUND{X} — '{site}' not in {serp} SERP pages")
            print(f"  Keyword: {keyword}")
        elif status == "captcha":
            print(f"  {R}CAPTCHA{X} — blocked on SERP page {serp}")
        elif status == "timeout":
            print(f"  {R}TIMEOUT{X} — scenario exceeded 300s")
        else:
            print(f"  {R}ERROR{X} — {result.get('error', status)}")
        print("=" * 60 + "\n")

        await browser.close()

    return result


def main():
    parser = argparse.ArgumentParser(description="Yandex PF bot smoke test")
    parser.add_argument("--headless", action="store_true", help="Run without window")
    parser.add_argument("--keyword", type=str, default=None, help="Override keyword")
    args = parser.parse_args()

    asyncio.run(run(headless=args.headless, keyword_override=args.keyword))


if __name__ == "__main__":
    main()
