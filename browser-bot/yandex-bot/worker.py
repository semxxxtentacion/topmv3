from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse
import sys
import os
from pyvirtualdisplay import Display

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.append(_root_dir)

from config import HEADLESS, SLOW_MO, TASK_TIMEOUT, WARMUP_ENABLED
from stealth import build_stealth_js
from stealth_metrika import apply_stealth
from chrome_versions import get_chrome_versions
import human
import warmup
import scenario

logger = logging.getLogger(__name__)

def _is_mobile(profile: dict) -> bool:
    val = profile.get('ismobiledevice')
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, list):
        return any(str(v).lower().strip() in ('true', 't', '1') for v in val)
    return str(val).lower().strip('{}[] ') in ('true', 't', '1')

def _build_user_agent(profile: dict) -> str:
    fp = profile.get('fingerprints')
    if isinstance(fp, dict):
        for key in ('user_agent', 'userAgent', 'ua'):
            if fp.get(key):
                return str(fp[key])
        nav = fp.get('navigator')
        if isinstance(nav, dict) and nav.get('userAgent'):
            return str(nav['userAgent'])

    browser = str(profile.get('browser', 'Chrome'))
    _versions = get_chrome_versions()
    _default_bv = _versions[0] if _versions else '120.0.0.0'
    bv = str(profile.get('browser_version', _default_bv))
    platform = str(profile.get('platform', 'Windows'))
    pv = str(profile.get('platform_version', '10'))

    if 'Android' in platform or _is_mobile(profile):
        return (f'Mozilla/5.0 (Linux; Android {pv}; K) '
                f'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{bv} Mobile Safari/537.36')
    if 'Windows' in platform:
        return (f'Mozilla/5.0 (Windows NT {pv}; Win64; x64) '
                f'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{bv} Safari/537.36')
    if 'Mac' in platform:
        return (f'Mozilla/5.0 (Macintosh; Intel Mac OS X {pv.replace(".", "_")}) '
                f'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{bv} Safari/537.36')
    return (f'Mozilla/5.0 (X11; Linux x86_64) '
            f'AppleWebKit/537.36 (KHTML, like Gecko) '
            f'Chrome/{bv} Safari/537.36')

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПОДМЕНЫ CLIENT HINTS ---
def _build_client_hints(profile: dict) -> dict:
    platform = str(profile.get('platform', 'Windows'))
    is_mob = _is_mobile(profile)
    
    ch_platform = '"Windows"'
    if 'Android' in platform or is_mob:
        ch_platform = '"Android"'
    elif 'Mac' in platform:
        ch_platform = '"macOS"'
    elif 'Linux' in platform:
        ch_platform = '"Linux"'
        
    _versions = get_chrome_versions()
    _default_bv = _versions[0] if _versions else '120.0.0.0'
    bv = str(profile.get('browser_version', _default_bv))
    major_version = bv.split('.')[0]
    
    return {
        'sec-ch-ua': f'"Not_A Brand";v="8", "Chromium";v="{major_version}", "Google Chrome";v="{major_version}"',
        'sec-ch-ua-mobile': '?1' if is_mob else '?0',
        'sec-ch-ua-platform': ch_platform,
    }
# ----------------------------------------------

MOBILE_VIEWPORTS = [
    {'width': 412, 'height': 915},
    {'width': 393, 'height': 873},
    {'width': 360, 'height': 800},
    {'width': 414, 'height': 896},
    {'width': 390, 'height': 844},
]

def _extract_viewport(profile: dict) -> dict:
    vp = profile.get('viewport')
    if isinstance(vp, dict) and vp.get('width') and vp.get('height'):
        return {'width': int(vp['width']), 'height': int(vp['height'])}

    fp = profile.get('fingerprints') or {}
    if isinstance(fp, dict):
        scr = fp.get('screen', fp)
        if scr:
            w = scr.get('screen_width') or scr.get('screenWidth') or scr.get('width')
            h = scr.get('screen_height') or scr.get('screenHeight') or scr.get('height')
            if w and h:
                return {'width': int(w), 'height': int(h)}

    if _is_mobile(profile) or str(profile.get('platform', '')).lower() == 'android':
        import random
        return random.choice(MOBILE_VIEWPORTS)

    return {'width': 1920, 'height': 1080}

def _extract_timezone(profile: dict) -> str:
    fp = profile.get('fingerprints') or {}
    if isinstance(fp, dict):
        tz = fp.get('timezone')
        if isinstance(tz, dict):
            return tz.get('id') or tz.get('timezone_id') or 'Europe/Moscow'
        if isinstance(tz, str):
            return tz
        for key in ('timezone_id', 'timezoneId', 'tz'):
            if fp.get(key):
                return str(fp[key])
    return 'Europe/Moscow'

def _extract_locale(profile: dict) -> str:
    fp = profile.get('fingerprints') or {}
    if isinstance(fp, dict):
        nav = fp.get('navigator', fp)
        if nav:
            lang = nav.get('language') or nav.get('lang')
            if lang:
                return str(lang)
            langs = nav.get('languages')
            if isinstance(langs, list) and langs:
                return str(langs[0])
    return 'ru-RU'

def _extract_geolocation(profile: dict) -> dict | None:
    geo = profile.get('geo')
    if isinstance(geo, dict):
        lat = geo.get('lat') or geo.get('latitude')
        lon = geo.get('lon') or geo.get('lng') or geo.get('longitude')
        if lat and lon:
            return {'latitude': float(lat), 'longitude': float(lon)}
    fp = profile.get('fingerprints') or {}
    if isinstance(fp, dict):
        g = fp.get('geolocation') or fp.get('geo')
        if isinstance(g, dict):
            lat = g.get('lat') or g.get('latitude')
            lon = g.get('lon') or g.get('lng') or g.get('longitude')
            if lat and lon:
                return {'latitude': float(lat), 'longitude': float(lon)}
    return None

def _build_context_options(profile: dict) -> dict:
    opts: dict = {
        'user_agent': _build_user_agent(profile),
        'viewport': _extract_viewport(profile),
        'locale': _extract_locale(profile),
        'timezone_id': _extract_timezone(profile),
        'extra_http_headers': _build_client_hints(profile) # <-- ПОДКЛЮЧИЛИ ПОДДЕЛКУ ЗАГОЛОВКОВ
    }
    geo = _extract_geolocation(profile)
    if geo:
        opts['geolocation'] = geo
        opts['permissions'] = ['geolocation']
    if _is_mobile(profile) or str(profile.get('platform', '')).lower() == 'android':
        opts['is_mobile'] = True
        opts['has_touch'] = True
        vp = profile.get('viewport')
        if isinstance(vp, dict) and vp.get('dpr'):
            opts['device_scale_factor'] = float(vp['dpr'])
        else:
            opts['device_scale_factor'] = 2.625
    return opts

def _normalize_cookie(c: dict) -> dict | None:
    if not isinstance(c, dict):
        return None
    name = str(c.get('name') or c.get('Name') or '')
    value = str(c.get('value') or c.get('Value') or '')
    if not name.strip():
        return None
    cookie = {
        'name': name,
        'value': value,
        'path': str(c.get('path', '/')),
    }
    domain = c.get('domain') or c.get('Domain')
    url = c.get('url')
    if domain:
        cookie['domain'] = str(domain)
    elif url:
        try:
            parsed = urlparse(url if url.startswith('http') else f'https://{url}')
            if parsed.hostname:
                cookie['domain'] = f'.{parsed.hostname.lstrip(".")}'
        except Exception:
            cookie['domain'] = '.yandex.ru'
    else:
        cookie['domain'] = '.yandex.ru'
    if c.get('expires') and isinstance(c.get('expires'), (int, float)):
        cookie['expires'] = float(c['expires'])
    if c.get('httpOnly') or c.get('HttpOnly'):
        cookie['httpOnly'] = True
    if c.get('secure'):
        cookie['secure'] = True
    if c.get('sameSite') and str(c['sameSite']) in ('Strict', 'Lax', 'None'):
        cookie['sameSite'] = c['sameSite']
    return cookie

def _prepare_cookies(profile: dict) -> list[dict]:
    raw = profile.get('cookies')
    valid = []
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict):
                cookie = _normalize_cookie(c)
                if cookie:
                    valid.append(cookie)
    elif isinstance(raw, dict):
        for url_or_domain, items in raw.items():
            if isinstance(items, list):
                for c in items:
                    if isinstance(c, dict):
                        cookie = _normalize_cookie(c)
                        if cookie:
                            valid.append(cookie)
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        cookie = _normalize_cookie(c)
                        if cookie:
                            valid.append(cookie)
            elif isinstance(parsed, dict):
                for items in parsed.values():
                    if isinstance(items, list):
                        for c in items:
                            if isinstance(c, dict):
                                cookie = _normalize_cookie(c)
                                if cookie:
                                    valid.append(cookie)
        except (json.JSONDecodeError, TypeError):
            pass
    return valid

async def _restore_localstorage(page, profile: dict):
    ls = profile.get('localstorage')
    if not ls:
        return
    if isinstance(ls, dict):
        items = ls
    elif isinstance(ls, list):
        items = {}
        for entry in ls:
            if isinstance(entry, dict) and 'key' in entry and 'value' in entry:
                items[str(entry['key'])] = str(entry['value'])
    else:
        return
    if not items:
        return
    js_items = json.dumps(items, ensure_ascii=False)
    await page.evaluate(f"""(data) => {{
        try {{
            for (const [k, v] of Object.entries(data)) {{
                localStorage.setItem(k, v);
            }}
        }} catch(e) {{}}
    }}""", json.loads(js_items))

def _parse_profile_proxy(profile: dict) -> dict | None:
    raw = profile.get('proxy')
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith('http://') or raw.startswith('socks'):
        parsed = urlparse(raw)
        proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            proxy["username"] = parsed.username
            proxy["password"] = parsed.password or ''
        return proxy
    parts = raw.split(':')
    if len(parts) == 4:
        return {
            "server": f"http://{parts[0]}:{parts[1]}",
            "username": parts[2],
            "password": parts[3],
        }
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    return None

from playwright.async_api import async_playwright

async def execute(profile: dict, proxy_obj, task: dict) -> dict:
    result = {'status': 'error', 'task': task}
    mouse_cfg = profile.get('mouse_config')
    if isinstance(mouse_cfg, dict):
        human.set_mouse_config(mouse_cfg)
    else:
        human.set_mouse_config(None)

    proxy_cfg = None
    strategy = 'no_proxy'
    if proxy_obj is not None and hasattr(proxy_obj, 'direct_proxy'):
        proxy_cfg = proxy_obj.direct_proxy
        strategy = 'direct'
    elif proxy_obj is not None and isinstance(proxy_obj, dict):
        proxy_cfg = proxy_obj
        strategy = 'dict'
    else:
        profile_proxy = _parse_profile_proxy(profile)
        if profile_proxy:
            proxy_cfg = profile_proxy
            strategy = 'profile'

    display = None
    if sys.platform.startswith('linux'):
        try:
            display = Display(visible=0, size=(1920, 1080))
            display.start()
            logger.info("🖥️ Xvfb started")
        except Exception as e:
            logger.error(f"❌ Xvfb error: {e}")

    try:
        async with async_playwright() as pw:
            launch_args = {
                'headless': False,
                'slow_mo': SLOW_MO,
                'args': [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-infobars',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--force-webrtc-ip-handling-policy=disable-non-proxied-udp' # <-- БЛОКИРОВКА УТЕЧКИ IP ПО WEBRTC
                ],
            }
            if proxy_cfg:
                launch_args['proxy'] = proxy_cfg
            
            browser = None
            try:
                try:
                    browser = await pw.chromium.launch(**launch_args)
                except Exception as launch_err:
                    if 'headless_shell' in str(launch_err):
                        launch_args['headless'] = False
                        if '--headless' in launch_args['args']:
                            launch_args['args'].remove('--headless')
                        browser = await pw.chromium.launch(**launch_args)
                    else:
                        raise

                ctx_opts = _build_context_options(profile)
                context = await browser.new_context(**ctx_opts)
                await context.add_init_script(build_stealth_js(profile))

                try:
                    await apply_stealth(context=context)
                except Exception as e:
                    logger.error(f"Stealth metrika error: {e}")

                cookies = _prepare_cookies(profile)
                if cookies:
                    try:
                        await context.add_cookies(cookies)
                    except Exception:
                        pass

                page = await context.new_page()

                if profile.get('localstorage'):
                    try:
                        await page.goto('https://yandex.ru', wait_until='commit', timeout=15000)
                        await _restore_localstorage(page, profile)
                    except Exception as e:
                        logger.debug(f"LocalStorage restore skipped or failed: {e}")

                warmup_count = 0
                if WARMUP_ENABLED:
                    try:
                        warmup_count = await warmup.run_warmup(page)
                    except Exception:
                        pass

                result = await asyncio.wait_for(
                    scenario.run(page, task),
                    timeout=TASK_TIMEOUT,
                )
                result['warmup_sites'] = warmup_count
                result['profile_pid'] = profile.get('pid', '?')

            except asyncio.TimeoutError:
                result = {'status': 'timeout', 'task': task}
            except Exception as e:
                result = {'status': 'error', 'task': task, 'error': str(e)}
                logger.error(f"Worker error: {e}")
            finally:
                if browser:
                    await browser.close()
    finally:
        if display:
            display.stop()

    return result
