"""
Mobile (Android) browser fingerprint generator.
Produces realistic, internally-consistent profiles for Russian region.

Supports two modes:
  source="builtin"   — built-in randomizer (default)
  source="external"  — load pre-collected fingerprints from JSON file

Switch via generate_profiles(count, source="builtin") or
       generate_profiles(count, source="external", external_path="fps.json")
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Data pools — DESKTOP specs (Windows & macOS)
# Real market configurations (Resolution + RAM + CPU Cores + GPU)
# ---------------------------------------------------------------------------

DEVICES = [
    # === WINDOWS: Офисные и бюджетные ноутбуки (1366x768 и 1920x1080, встройки) ===
    {"os": "Windows", "os_version": "10.0", "ram": 8, "cores": 4,
     "gpu": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (Intel)",
     "viewport": {"width": 1366, "height": 768, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 8, "cores": 4,
     "gpu": "ANGLE (Intel, Intel(R) HD Graphics 520 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (Intel)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.25}}, # Масштаб 125% (типично для 15.6" FHD)
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 8,
     "gpu": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (Intel)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.25}},
    {"os": "Windows", "os_version": "10.0", "ram": 8, "cores": 6,
     "gpu": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (AMD)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},

    # === WINDOWS: Популярные домашние и игровые ПК (FHD 1920x1080) ===
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 12,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 12,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 16,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 8,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 16, "cores": 12,
     "gpu": "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (AMD)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 8, "cores": 8,
     "gpu": "ANGLE (AMD, Radeon RX 580 Series Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (AMD)",
     "viewport": {"width": 1920, "height": 1080, "dpr": 1.0}},

    # === WINDOWS: Мощные рабочие и игровые станции (2K и 4K) ===
    {"os": "Windows", "os_version": "10.0", "ram": 32, "cores": 16,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 2560, "height": 1440, "dpr": 1.0}},
    {"os": "Windows", "os_version": "10.0", "ram": 32, "cores": 24,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 2560, "height": 1440, "dpr": 1.25}},
    {"os": "Windows", "os_version": "10.0", "ram": 32, "cores": 24,
     "gpu": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (NVIDIA)",
     "viewport": {"width": 3840, "height": 2160, "dpr": 1.5}}, # 4K монитор
    {"os": "Windows", "os_version": "10.0", "ram": 32, "cores": 16,
     "gpu": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_11_0, D3D11)", "gpu_vendor": "Google Inc. (AMD)",
     "viewport": {"width": 2560, "height": 1440, "dpr": 1.0}},

    # === macOS: Современные Apple Silicon (M1/M2/M3) ===
    {"os": "macOS", "os_version": "10_15_7", "ram": 8, "cores": 8,
     "gpu": "ANGLE (Apple, Apple M1, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Apple)",
     "viewport": {"width": 1440, "height": 900, "dpr": 2.0}}, # Классический MacBook Air M1
    {"os": "macOS", "os_version": "10_15_7", "ram": 16, "cores": 8,
     "gpu": "ANGLE (Apple, Apple M2, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Apple)",
     "viewport": {"width": 1470, "height": 956, "dpr": 2.0}}, # MacBook Air M2 13.6"
    {"os": "macOS", "os_version": "10_15_7", "ram": 16, "cores": 10,
     "gpu": "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Apple)",
     "viewport": {"width": 1512, "height": 982, "dpr": 2.0}}, # MacBook Pro 14"
    {"os": "macOS", "os_version": "10_15_7", "ram": 16, "cores": 12,
     "gpu": "ANGLE (Apple, Apple M3 Pro, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Apple)",
     "viewport": {"width": 1512, "height": 982, "dpr": 2.0}},
    {"os": "macOS", "os_version": "10_15_7", "ram": 32, "cores": 10,
     "gpu": "ANGLE (Apple, Apple M1 Max, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Apple)",
     "viewport": {"width": 1728, "height": 1117, "dpr": 2.0}}, # MacBook Pro 16"

    # === macOS: Старые модели на Intel ===
    {"os": "macOS", "os_version": "10_15_7", "ram": 8, "cores": 4,
     "gpu": "ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics 640, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Intel Inc.)",
     "viewport": {"width": 1440, "height": 900, "dpr": 2.0}}, # MacBook Pro 13" (2017)
    {"os": "macOS", "os_version": "10_15_7", "ram": 16, "cores": 8,
     "gpu": "ANGLE (Intel Inc., Intel(R) UHD Graphics 630, OpenGL 4.1)", "gpu_vendor": "Google Inc. (Intel Inc.)",
     "viewport": {"width": 1440, "height": 900, "dpr": 2.0}}, # MacBook Pro 13" (2019)
    {"os": "macOS", "os_version": "10_15_7", "ram": 16, "cores": 8,
     "gpu": "ANGLE (AMD, AMD Radeon Pro 5300M OpenGL Engine, OpenGL 4.1)", "gpu_vendor": "Google Inc. (AMD)",
     "viewport": {"width": 1536, "height": 960, "dpr": 2.0}}, # MacBook Pro 16" (2019)
]

# Chrome versions — fetched from Google API, cached 24h, fallback to hardcoded
from generator.chrome_versions import get_chrome_versions
CHROME_VERSIONS = get_chrome_versions()

# Weighted by population: Moscow ~20%, SPb ~7%, rest spread across major cities
RUSSIAN_REGIONS = [
    {"city": "Москва",            "tz": "Europe/Moscow",       "lat": 55.7558, "lon": 37.6173, "weight": 20},
    {"city": "Санкт-Петербург",   "tz": "Europe/Moscow",       "lat": 59.9343, "lon": 30.3351, "weight": 7},
    {"city": "Новосибирск",       "tz": "Asia/Novosibirsk",    "lat": 55.0084, "lon": 82.9357, "weight": 4},
    {"city": "Екатеринбург",      "tz": "Asia/Yekaterinburg",  "lat": 56.8389, "lon": 60.6057, "weight": 4},
    {"city": "Казань",            "tz": "Europe/Moscow",       "lat": 55.7887, "lon": 49.1221, "weight": 4},
    {"city": "Нижний Новгород",   "tz": "Europe/Moscow",       "lat": 56.2965, "lon": 43.9361, "weight": 3},
    {"city": "Челябинск",         "tz": "Asia/Yekaterinburg",  "lat": 55.1644, "lon": 61.4368, "weight": 3},
    {"city": "Самара",            "tz": "Europe/Samara",       "lat": 53.1959, "lon": 50.1002, "weight": 3},
    {"city": "Омск",              "tz": "Asia/Omsk",           "lat": 54.9885, "lon": 73.3242, "weight": 3},
    {"city": "Ростов-на-Дону",    "tz": "Europe/Moscow",       "lat": 47.2357, "lon": 39.7015, "weight": 3},
    {"city": "Уфа",               "tz": "Asia/Yekaterinburg",  "lat": 54.7388, "lon": 55.9721, "weight": 3},
    {"city": "Красноярск",        "tz": "Asia/Krasnoyarsk",    "lat": 56.0153, "lon": 92.8932, "weight": 3},
    {"city": "Воронеж",           "tz": "Europe/Moscow",       "lat": 51.6720, "lon": 39.1843, "weight": 3},
    {"city": "Пермь",             "tz": "Asia/Yekaterinburg",  "lat": 58.0105, "lon": 56.2502, "weight": 3},
    {"city": "Волгоград",         "tz": "Europe/Volgograd",    "lat": 48.7080, "lon": 44.5133, "weight": 3},
    {"city": "Краснодар",         "tz": "Europe/Moscow",       "lat": 45.0355, "lon": 38.9753, "weight": 4},
    {"city": "Тюмень",            "tz": "Asia/Yekaterinburg",  "lat": 57.1522, "lon": 65.5272, "weight": 2},
    {"city": "Иркутск",           "tz": "Asia/Irkutsk",        "lat": 52.2870, "lon": 104.3050, "weight": 2},
    {"city": "Владивосток",       "tz": "Asia/Vladivostok",    "lat": 43.1155, "lon": 131.8855, "weight": 2},
    {"city": "Хабаровск",         "tz": "Asia/Vladivostok",    "lat": 48.4827, "lon": 135.0835, "weight": 2},
    {"city": "Саратов",           "tz": "Europe/Saratov",      "lat": 51.5336, "lon": 46.0344, "weight": 2},
    {"city": "Тольятти",          "tz": "Europe/Samara",       "lat": 53.5078, "lon": 49.4205, "weight": 2},
    {"city": "Барнаул",           "tz": "Asia/Barnaul",        "lat": 53.3548, "lon": 83.7698, "weight": 2},
]

DESKTOP_FONTS = [
    "Arial", "Verdana", "Times New Roman", "Courier New", "Consolas",
    "Tahoma", "Trebuchet MS", "Georgia", "Impact", "Comic Sans MS",
    "Segoe UI", "San Francisco", "Helvetica Neue", "Ubuntu"
]

# Language combos real Android users in Russia might have
LANGUAGE_SETS = [
    ["ru-RU", "ru", "en-US", "en"],
    ["ru-RU", "ru", "en-US", "en"],  # most common — double weight
    ["ru-RU", "ru"],
    ["ru-RU", "ru", "en-GB", "en"],
    ["ru", "en-US", "en"],
    ["ru-RU", "ru", "uk-UA", "en-US", "en"],
    ["ru-RU", "ru", "tr-TR", "en-US", "en"],
]

# Battery level distribution — mostly charged (people use phones when charged)
BATTERY_RANGES = [
    (0.15, 0.30, 0.08),   # low battery — rare
    (0.30, 0.55, 0.22),   # medium
    (0.55, 0.80, 0.35),   # healthy
    (0.80, 1.00, 0.35),   # well charged
]


def _pick_region() -> dict:
    weights = [r["weight"] for r in RUSSIAN_REGIONS]
    return random.choices(RUSSIAN_REGIONS, weights=weights, k=1)[0]


def _pick_battery() -> dict:
    """Generate realistic battery state for DESKTOPS and LAPTOPS."""
    # 85% шанс, что это стационарный ПК или ноутбук на зарядке
    if random.random() < 0.85:
        return {
            "charging": True,
            "level": 1.0,
            "chargingTime": 0,
            "dischargingTime": None,
        }
    # 15% шанс, что это ноутбук, работающий от батареи
    else:
        return {
            "charging": False,
            "level": round(random.uniform(0.15, 0.95), 2),
            "chargingTime": 0,
            "dischargingTime": random.randint(3600, 28800),
        }


def _screen_avail_offset(viewport: dict) -> dict:
    """Add realistic availWidth/availHeight (status bar, nav bar offsets)."""
    status_bar = random.choice([24, 25, 26, 28, 30, 32])  # dp
    nav_bar = random.choice([0, 0, 0, 48, 48])  # many phones use gesture nav (0)
    return {
        "availWidth": viewport["width"],
        "availHeight": viewport["height"] - status_bar - nav_bar,
        "availTop": status_bar,
        "availLeft": 0,
    }


def generate_fingerprint() -> dict:
    """Generate one complete DESKTOP profile with consistent fingerprint data."""
    device = random.choice(DEVICES)
    chrome = random.choice(CHROME_VERSIONS)
    viewport = dict(device["viewport"])
    region = _pick_region()

    lat_jitter = random.uniform(-0.05, 0.05)
    lon_jitter = random.uniform(-0.05, 0.05)

    # Десктопные User-Agent и Platform
    if device["os"] == "Windows":
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
        nav_platform = "Win32"
    else:
        ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X {device['os_version']}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
        nav_platform = "MacIntel"

    canvas_seed = random.randint(1, 2**16)
    audio_noise = round(random.uniform(0.00001, 0.001), 7)
    num_fonts = random.randint(8, len(DESKTOP_FONTS))
    fonts = random.sample(DESKTOP_FONTS, num_fonts)
    languages = random.choice(LANGUAGE_SETS)
    
    # Имитация панели задач (Taskbar) для десктопа
    taskbar_height = 40 if device["os"] == "Windows" else 25
    screen_avail = {
        "availWidth": viewport["width"],
        "availHeight": viewport["height"] - taskbar_height,
        "availTop": taskbar_height if device["os"] == "macOS" else 0,
        "availLeft": 0,
    }

    fingerprints = {
        "navigator": {
            "userAgent": ua,
            "platform": nav_platform,
            "hardwareConcurrency": device["cores"],
            "deviceMemory": device["ram"],
            "maxTouchPoints": 0, # НА ДЕСКТОПЕ НЕТ ТАЧСКРИНА
            "doNotTrack": random.choice([None, None, "1"]),
            "language": languages[0],
            "languages": languages,
        },
        "screen": {
            "width": viewport["width"],
            "height": viewport["height"],
            "colorDepth": 24,
            "pixelDepth": 24,
            **screen_avail,
        },
        "webgl": {
            "vendor": device["gpu_vendor"],
            "renderer": device["gpu"],
        },
        "audio": {
            "noise": audio_noise,
        },
        "canvas_seed": canvas_seed,
        "fonts": fonts,
        "timezone": {
            "id": region["tz"],
        },
        "geolocation": {
            "latitude": round(region["lat"] + lat_jitter, 4),
            "longitude": round(region["lon"] + lon_jitter, 4),
        },
        "battery": _pick_battery(), # Ноутбуки тоже имеют батарею
    }

    mouse_config = {
        "speed": round(random.uniform(0.7, 1.4), 2),
        "jitter": round(random.uniform(0.6, 1.5), 2),
        "click_delay": round(random.uniform(0.7, 1.3), 2),
        "type_speed": round(random.uniform(0.8, 1.3), 2),
    }

    return {
        "pid": str(uuid.uuid4()),
        "party": "builtin",
        "ismobiledevice": False, # ТЕПЕРЬ МЫ ДЕСКТОП
        "platform": device["os"],
        "platform_version": device["os_version"],
        "browser": "Chrome",
        "browser_version": chrome,
        "device_model": "Desktop PC",
        "device_name": f"{device['os']} PC",
        "device_chipset": device.get("chipset", "Intel/AMD"),
        "fingerprints": fingerprints,
        "cookies": [],
        "localstorage": {},
        "proxy": None,
        "geo": {
            "city": region["city"],
            "latitude": round(region["lat"] + lat_jitter, 4),
            "longitude": round(region["lon"] + lon_jitter, 4),
            "timezone": region["tz"],
        },
        "mouse_config": mouse_config,
        "viewport": viewport,
        "warm": False,
    }


# ---------------------------------------------------------------------------
# External fingerprint loader
# ---------------------------------------------------------------------------

def _load_external(path: str, count: int) -> list[dict]:
    """
    Load fingerprints from an external JSON file.

    Expected format: a JSON array of objects. Each object should have at least:
      - fingerprints (dict with navigator, screen, webgl, etc.)
      - viewport (dict with width, height, dpr)

    Missing fields are filled with defaults so the rest of the pipeline works.
    """
    fp_path = Path(path)
    if not fp_path.exists():
        raise FileNotFoundError(f"External fingerprints file not found: {path}")

    with open(fp_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    if not isinstance(raw_list, list) or len(raw_list) == 0:
        raise ValueError(f"External file must contain a non-empty JSON array")

    profiles = []
    for i in range(count):
        # cycle through the file if count > len(raw_list)
        raw = dict(raw_list[i % len(raw_list)])

        # ensure required fields exist
        raw.setdefault("pid", str(uuid.uuid4()))
        raw.setdefault("party", "external")
        raw.setdefault("ismobiledevice", True)
        raw.setdefault("platform", "Android")
        raw.setdefault("cookies", [])
        raw.setdefault("localstorage", {})
        raw.setdefault("proxy", None)
        raw.setdefault("warm", False)
        raw.setdefault("fingerprints", {})
        raw.setdefault("viewport", {"width": 412, "height": 915, "dpr": 2.625})

        # generate mouse config if missing (always needed for human module)
        if "mouse_config" not in raw:
            raw["mouse_config"] = {
                "speed": round(random.uniform(0.7, 1.4), 2),
                "jitter": round(random.uniform(0.6, 1.5), 2),
                "click_delay": round(random.uniform(0.7, 1.3), 2),
                "type_speed": round(random.uniform(0.8, 1.3), 2),
            }

        # fill geo from fingerprints if missing
        if "geo" not in raw:
            fp_geo = raw["fingerprints"].get("geolocation", {})
            fp_tz = raw["fingerprints"].get("timezone", {})
            raw["geo"] = {
                "city": "Unknown",
                "latitude": fp_geo.get("latitude", 55.7558),
                "longitude": fp_geo.get("longitude", 37.6173),
                "timezone": fp_tz.get("id", "Europe/Moscow"),
            }

        profiles.append(raw)

    return profiles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_profiles(
    count: int,
    source: str = "builtin",
    external_path: str | None = None,
) -> list[dict]:
    """
    Generate `count` unique mobile profiles.

    Args:
        count: number of profiles to generate
        source: "builtin" (default randomizer) or "external" (from JSON file)
        external_path: path to JSON file when source="external"
    """
    if source == "external":
        if not external_path:
            raise ValueError("external_path is required when source='external'")
        return _load_external(external_path, count)

    return [generate_fingerprint() for _ in range(count)]
