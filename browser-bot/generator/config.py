"""
Application configuration.
Environment variables override defaults.
Loads .env file automatically if present.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# --- Database ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
)

# Sync URL for migrations / raw SQL (same DB, different driver)
DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    "",
)

# --- Proxy (3proxy defaults, override via env or CLI) ---
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT_FIRST = int(os.getenv("PROXY_PORT_FIRST", "0"))
PROXY_PORT_LAST = int(os.getenv("PROXY_PORT_LAST", "0"))
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

# --- Proxy file (asocks format: ip:port:login:pass:refresh_link) ---
PROXY_FILE = os.getenv("PROXY_FILE", "proxies.txt")

# --- Profile limits ---
MAX_PROFILES = int(os.getenv("MAX_PROFILES", "1500"))

# --- Warmup scheduler ---
WARMUP_INTERVAL_HOURS = int(os.getenv("WARMUP_INTERVAL_HOURS", "8"))
WARMUP_BATCH_SIZE = int(os.getenv("WARMUP_BATCH_SIZE", "20"))
WARMUP_WORKERS = int(os.getenv("WARMUP_WORKERS", "3"))

# --- Server ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
