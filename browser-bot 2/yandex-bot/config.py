import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

# Load root .env first (shared DB, proxies), then local .env (bot-specific)
load_dotenv(ROOT_DIR / '.env')
load_dotenv(BASE_DIR / '.env', override=True)

# --- Database (shared with acc-generator) ---
# Accepts DATABASE_URL from root .env; strips +asyncpg suffix for asyncpg
_raw_url = os.getenv('DATABASE_URL', 'postgresql://admin:pass@localhost:5432/acc_generator')
DATABASE_URL = _raw_url.replace('postgresql+asyncpg://', 'postgresql://')

# --- Proxy (asocks) ---
PROXY_FILE = os.getenv('PROXY_FILE', 'ips.txt')
PROXY_USERNAME = os.getenv('PROXY_USERNAME', '')
PROXY_PASSWORD = os.getenv('PROXY_PASSWORD', '')
USE_LOCAL_PROXY = True

# --- Browser ---
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
SLOW_MO = int(os.getenv('SLOW_MO', '0'))

# --- Workers ---
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))
TASK_TIMEOUT = int(os.getenv('TASK_TIMEOUT', '300'))

# --- Warmup ---
WARMUP_ENABLED = os.getenv('WARMUP_ENABLED', 'false').lower() == 'true'
WARMUP_SITES_FILE = os.getenv('WARMUP_SITES_FILE', str(BASE_DIR / 'warmup_sites.txt'))
WARMUP_MIN_SITES = int(os.getenv('WARMUP_MIN_SITES', '2'))
WARMUP_MAX_SITES = int(os.getenv('WARMUP_MAX_SITES', '5'))
WARMUP_MIN_TIME = int(os.getenv('WARMUP_MIN_TIME', '15'))
WARMUP_MAX_TIME = int(os.getenv('WARMUP_MAX_TIME', '45'))

# --- Yandex Scenario ---
YANDEX_MAX_SERP_PAGES = int(os.getenv('YANDEX_MAX_SERP_PAGES', '10'))
MIN_TIME_ON_SITE = int(os.getenv('MIN_TIME_ON_SITE', '30'))
MAX_TIME_ON_SITE = int(os.getenv('MAX_TIME_ON_SITE', '120'))
MIN_PAGES_ON_SITE = int(os.getenv('MIN_PAGES_ON_SITE', '2'))
MAX_PAGES_ON_SITE = int(os.getenv('MAX_PAGES_ON_SITE', '5'))

# --- Tasks ---
TASKS_FILE = os.getenv('TASKS_FILE', str(BASE_DIR / 'tasks.json'))

# --- API server ---
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8082'))
API_SECRET = os.getenv('API_SECRET', '')

# --- Captcha solving (CapMonster Cloud) ---
CAPMONSTER_API_KEY = os.getenv('CAPMONSTER_API_KEY', '')

# --- Logging ---
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', str(BASE_DIR / 'yandex_bot.log'))
