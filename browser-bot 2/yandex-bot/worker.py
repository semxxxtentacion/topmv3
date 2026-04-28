from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse
import sys
import os
import aiohttp
from pyvirtualdisplay import Display
from playwright.async_api import async_playwright

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
ROTATION_URL = "https://changeip.mobileproxy.space/?proxy_key=d8432adacb8716438427ff7ddfacb28c"

async def rotate_proxy_ip():
    try:
        print(f"🔄 [ROTATION] Запрос на смену IP...", flush=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(ROTATION_URL, timeout=30) as resp:
                txt = await resp.text()
                print(f"📡 [ROTATION] Ответ API: {txt.strip()}", flush=True)
            print(f"⏳ [ROTATION] Ожидание 15с (переподключение модема)...", flush=True)
            await asyncio.sleep(15)
    except Exception as e:
        print(f"❌ [ROTATION] Ошибка: {e}", flush=True)

def _parse_profile_proxy(profile: dict) -> dict | None:
    raw = profile.get('proxy')
    if not raw or not isinstance(raw, str): return None
    raw = raw.strip()
    if raw.startswith('http://') or raw.startswith('socks'):
        parsed = urlparse(raw)
        proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            proxy["username"] = parsed.username
            proxy["password"] = parsed.password or ''
        return proxy
    parts = raw.split(':')
    if len(parts) == 4:
        return {"server": f"http://{parts[0]}:{parts[1]}", "username": parts[2], "password": parts[3]}
    return None

def _is_mobile(profile: dict) -> bool:
    val = profile.get('ismobiledevice')
    if val is None: return False
    if isinstance(val, bool): return val
    if isinstance(val, list): return any(str(v).lower().strip() in ('true', 't', '1') for v in val)
    return str(val).lower().strip('{}[] ') in ('true', 't', '1')

def _build_user_agent(profile: dict) -> str:
    fp = profile.get('fingerprints')
    if isinstance(fp, dict):
        for key in ('user_agent', 'userAgent', 'ua'):
            if fp.get(key): return str(fp[key])
    bv = str(profile.get('browser_version', '120.0.0.0'))
    pv = str(profile.get('platform_version', '10'))
    platform = str(profile.get('platform', 'Windows'))

    if 'Android' in platform or _is_mobile(profile):
        return f'Mozilla/5.0 (Linux; Android {pv}; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{bv} Mobile Safari/537.36'
    return f'Mozilla/5.0 (Windows NT {pv}; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{bv} Safari/537.36'

def _extract_viewport(profile: dict) -> dict:
    vp = profile.get('viewport')
    if isinstance(vp, dict) and vp.get('width') and vp.get('height'):
        return {'width': int(vp['width']), 'height': int(vp['height'])}
    return {'width': 1920, 'height': 1080}

def _build_context_options(profile: dict) -> dict:
    is_mob = _is_mobile(profile)
    bv = str(profile.get('browser_version', '120.0.0.0')).split('.')[0]
    return {
        'user_agent': _build_user_agent(profile),
        'viewport': _extract_viewport(profile),
        'locale': 'ru-RU',
        'timezone_id': 'Europe/Moscow',
        'extra_http_headers': {
            'sec-ch-ua': f'"Not_A Brand";v="8", "Chromium";v="{bv}", "Google Chrome";v="{bv}"',
            'sec-ch-ua-mobile': '?1' if is_mob else '?0',
            'sec-ch-ua-platform': '"Android"' if is_mob else '"Windows"',
        }
    }

async def execute(profile: dict, proxy_obj, task: dict) -> dict:
    await rotate_proxy_ip()

    result = {'status': 'error', 'task': task}
    display = None
    
    if sys.platform.startswith('linux'):
        try:
            display = Display(visible=0, size=(1920, 1080))
            display.start()
        except: pass

    try:
        async with async_playwright() as pw:
            proxy_cfg = proxy_obj if isinstance(proxy_obj, dict) else _parse_profile_proxy(profile)
            
            launch_args = {
                'headless': False,
                'args': [
                    '--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled',
                    '--force-webrtc-ip-handling-policy=disable-non-proxied-udp', '--enforce-webrtc-ip-permission-check',
                    '--disable-gpu', '--use-gl=swiftshader', '--disable-software-rasterizer',
                    '--disable-background-networking', '--disable-default-apps', '--disable-extensions', '--no-first-run'
                ]
            }
            
            browser = await pw.chromium.launch(**launch_args)
            context = await browser.new_context(**_build_context_options(profile), proxy=proxy_cfg)
            await context.add_init_script(build_stealth_js(profile))
            await apply_stealth(context=context)
            page = await context.new_page()

            ip_verified = False
            current_ip = "UNKNOWN"
            
            for check_url in ["https://api.ipify.org", "https://ident.me", "https://ifconfig.me/ip"]:
                try:
                    ip_resp = await page.goto(check_url, timeout=15000)
                    ip_text = (await ip_resp.text()).strip()
                    if "." in ip_text and len(ip_text) <= 15:
                        current_ip = ip_text
                        print(f"🌍 [PLAYWRIGHT] ТЕКУЩИЙ IP В БРАУЗЕРЕ: {current_ip} (источник: {check_url})", flush=True)
                        ip_verified = True
                        break
                except Exception as e:
                    print(f"⚠️ [PLAYWRIGHT] Прокси еще грузится... Тайм-аут от {check_url}", flush=True)
            
            SERVER_IP = "5.129.206.79" 
            
            if not ip_verified:
                print("❌ [АВАРИЯ] Не удалось подтвердить работу прокси! Отменяем задачу.", flush=True)
                await browser.close()
                return {'status': 'error', 'error': 'Proxy verification timeout'}
                
            if current_ip == SERVER_IP:
                print("❌ [ФАТАЛЬНО] БРАУЗЕР СВЕТИТ IP СЕРВЕРА! Экстренная остановка.", flush=True)
                await browser.close()
                return {'status': 'error', 'error': 'Server IP leak detected'}
            
            result = await asyncio.wait_for(scenario.run(page, task), timeout=TASK_TIMEOUT)
            await browser.close()
    except Exception as e:
        result = {'status': 'error', 'error': str(e)}
    finally:
        if display: display.stop()
            
    return result
